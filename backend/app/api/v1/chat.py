import logging

from fastapi import APIRouter, HTTPException

from app.agents.chat_agent import run_chat_agent
from app.models.agents import ChatAgentDeps
from app.models.chat import ChatRequest, ChatResponse
from app.services.audit.audit_log import insert_audit_log_async
from app.services.clinical.mock_data import TRIAL_ID

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat agent failed for message=%r", body.message)
        raise HTTPException(status_code=502, detail=f"Chat agent failed: {exc}") from exc

    target_ids = payload.search_payload.target_patient_ids if payload.search_payload else None
    suggested = (target_ids[0] if target_ids else None) or body.patient_id

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

    return ChatResponse(
        reply=payload.response,
        conversation_id=conversation_id,
        suggested_patient_id=suggested,
        search_payload=payload.search_payload,
    )
