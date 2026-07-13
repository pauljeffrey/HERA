import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic_ai.exceptions import ModelHTTPError

from app.agents.chat_agent import iter_chat_agent, run_chat_agent
from app.models.agents import ChatAgentDeps, Response
from app.models.chat import ChatRequest, ChatResponse
from app.models.search import SearchCriteria
from app.services.audit.audit_log import insert_audit_log_async
from app.services.clinical.mock_data import TRIAL_ID
from app.services.infra.stream_events import sse_payloads

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _chat_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ModelHTTPError):
        if exc.status_code == 429:
            return HTTPException(
                status_code=503,
                detail="The model provider is temporarily rate-limited. Please retry in a minute.",
            )
        if exc.status_code in (401, 403):
            return HTTPException(
                status_code=503,
                detail="Model API authentication failed. Check MODEL_API_KEY on the server.",
            )
        return HTTPException(status_code=502, detail=f"Chat agent failed (HTTP {exc.status_code}).")
    return HTTPException(status_code=502, detail=f"Chat agent failed: {exc}")


async def _audit_chat_turn(body: ChatRequest, payload, conversation_id: str, suggested: str | None) -> None:
    try:
        await insert_audit_log_async(
            patient_id=suggested or "SYSTEM",
            encounter_id="CHAT",
            trial_id=body.trial_id or TRIAL_ID,
            original_llm_raw_response=body.message,
            pydantic_parsed_payload=payload.model_dump(mode="json"),
        )
    except Exception as exc:
        logger.warning(
            "Chat audit log insert failed patient_id=%s trial_id=%s: %s",
            suggested or "SYSTEM",
            body.trial_id or TRIAL_ID,
            exc,
            exc_info=True,
        )


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    deps = ChatAgentDeps(
        user_id="clinician",
        trial_id=body.trial_id,
        patient_id=body.patient_id,
    )

    try:
        payload, conversation_id = await run_chat_agent(body.message, deps, body.conversation_id)
    except Exception as exc:
        logger.exception("Chat agent failed for message=%r", body.message)
        raise _chat_http_error(exc) from exc

    target_ids = payload.search_payload.target_patient_ids if payload.search_payload else None
    suggested = (target_ids[0] if target_ids else None) or body.patient_id
    await _audit_chat_turn(body, payload, conversation_id, suggested)

    return ChatResponse(
        reply=payload.response,
        conversation_id=conversation_id,
        suggested_patient_id=suggested,
        search_payload=payload.search_payload,
    )


@router.post("/stream")
async def chat_stream(body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    deps = ChatAgentDeps(
        user_id="clinician",
        trial_id=body.trial_id,
        patient_id=body.patient_id,
    )

    async def event_stream():
        try:
            async for event in iter_chat_agent(body.message, deps, body.conversation_id):
                if event.get("type") == "done":
                    search_raw = event.get("search_payload")
                    search_payload = SearchCriteria.model_validate(search_raw) if search_raw else None
                    payload = Response(response=event["reply"], search_payload=search_payload)
                    await _audit_chat_turn(
                        body,
                        payload,
                        event["conversation_id"],
                        event.get("suggested_patient_id"),
                    )
                yield event
        except Exception as exc:
            logger.exception("Chat stream failed for message=%r", body.message)
            http_exc = _chat_http_error(exc)
            yield {"type": "error", "content": http_exc.detail}

    return StreamingResponse(
        sse_payloads(event_stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
