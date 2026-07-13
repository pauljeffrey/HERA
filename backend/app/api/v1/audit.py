from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic_ai.exceptions import ModelHTTPError

from app.agents.audit_analysis_agent import iter_audit_analysis_agent, run_audit_analysis_agent
from app.models.audit import (
    AuditCopilotRequest,
    AuditCopilotResponse,
    AuditDashboardResponse,
    AuditLogEntry,
    ClinicianOverrideRequest,
    ClinicianOverrideResponse,
)
from app.services.audit.audit_dashboard import apply_patient_override, build_dashboard
from app.services.audit.audit_log import fetch_audit_logs, insert_audit_log_async
from app.services.audit.task_storage import fetch_matching_task, update_matching_task
from app.services.infra.stream_events import sse_payloads

router = APIRouter(prefix="/audit", tags=["audit"])


def _copilot_http_error(exc: Exception) -> HTTPException:
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
        return HTTPException(status_code=502, detail=f"Audit copilot failed (HTTP {exc.status_code}).")
    return HTTPException(status_code=502, detail=f"Audit copilot failed: {exc}")


def _validate_override(body: ClinicianOverrideRequest) -> None:
    if body.override_status not in ("APPROVED", "OVERRULED"):
        raise HTTPException(status_code=400, detail="override_status must be APPROVED or OVERRULED")
    if body.override_status == "OVERRULED" and len(body.override_reason_text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Override reason must be at least 10 characters")


@router.get("/tasks/{task_id}", response_model=AuditDashboardResponse)
async def get_audit_dashboard(task_id: str):
    task = await fetch_matching_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return AuditDashboardResponse.model_validate(build_dashboard(task))


@router.post("/tasks/{task_id}/copilot", response_model=AuditCopilotResponse)
async def audit_copilot(task_id: str, body: AuditCopilotRequest):
    try:
        reply = await run_audit_analysis_agent(
            task_id=task_id,
            message=body.message,
            patient_id=body.patient_id,
            user_id=body.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _copilot_http_error(exc) from exc

    return AuditCopilotResponse(
        reply=reply.reply_markdown,
        scope=reply.scope_label,
        suggested_chips=reply.suggested_chips,
        override_applied=reply.override_applied,
        updated_patient_id=reply.updated_patient_id,
        updated_overall_status=reply.updated_overall_status,
    )


@router.post("/tasks/{task_id}/copilot/stream")
async def audit_copilot_stream(task_id: str, body: AuditCopilotRequest):
    async def event_stream():
        try:
            async for event in iter_audit_analysis_agent(
                task_id=task_id,
                message=body.message,
                patient_id=body.patient_id,
                user_id=body.user_id,
            ):
                yield event
        except Exception as exc:
            http_exc = _copilot_http_error(exc)
            yield {"type": "error", "content": http_exc.detail}

    return StreamingResponse(
        sse_payloads(event_stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/tasks/{task_id}/override", response_model=ClinicianOverrideResponse)
async def override_from_dashboard(task_id: str, body: ClinicianOverrideRequest):
    _validate_override(body)
    task = await fetch_matching_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    summary = apply_patient_override(
        task,
        patient_id=body.patient_id,
        override_status=body.override_status,
        reason=body.override_reason_text,
    )
    await update_matching_task(task_id, result_summary=summary)

    log_id = await insert_audit_log_async(
        patient_id=body.patient_id,
        encounter_id=body.encounter_id,
        trial_id=body.trial_id,
        clinician_override_status=body.override_status,
        override_reason_text=body.override_reason_text,
        pydantic_parsed_payload=body.model_dump(),
    )
    return ClinicianOverrideResponse(
        log_id=log_id,
        status=body.override_status,
        message="Clinician override recorded in audit ledger.",
    )


@router.post("/override", response_model=ClinicianOverrideResponse)
async def clinician_override(body: ClinicianOverrideRequest):
    _validate_override(body)
    log_id = await insert_audit_log_async(
        patient_id=body.patient_id,
        encounter_id=body.encounter_id,
        trial_id=body.trial_id,
        clinician_override_status=body.override_status,
        override_reason_text=body.override_reason_text,
        pydantic_parsed_payload=body.model_dump(),
    )

    return ClinicianOverrideResponse(
        log_id=log_id,
        status=body.override_status,
        message="Clinician override recorded in audit ledger.",
    )


@router.get("/logs/{patient_id}", response_model=list[AuditLogEntry])
async def get_audit_logs(patient_id: str):
    logs = await fetch_audit_logs(patient_id)
    return [
        AuditLogEntry(
            log_id=str(log["log_id"]),
            patient_id=log["patient_id"],
            encounter_id=log["encounter_id"],
            trial_id=log["trial_id"],
            clinician_override_status=log.get("clinician_override_status"),
            override_reason_text=log.get("override_reason_text"),
            timestamp=log.get("timestamp") or "",
        )
        for log in logs
    ]
