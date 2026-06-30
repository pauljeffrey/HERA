import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import AuditLog
from app.models.schemas import AuditLogEntry, ClinicianOverrideRequest, ClinicianOverrideResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post("/override", response_model=ClinicianOverrideResponse)
async def clinician_override(body: ClinicianOverrideRequest, db: AsyncSession = Depends(get_db)):
    if body.override_status not in ("APPROVED", "OVERRULED"):
        raise HTTPException(status_code=400, detail="override_status must be APPROVED or OVERRULED")
    if body.override_status == "OVERRULED" and len(body.override_reason_text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Override reason must be at least 10 characters")

    log_id = uuid.uuid4()
    entry = AuditLog(
        log_id=str(log_id),
        patient_id=body.patient_id,
        encounter_id=body.encounter_id,
        trial_id=body.trial_id,
        clinician_override_status=body.override_status,
        override_reason_text=body.override_reason_text,
        pydantic_parsed_payload=body.model_dump(),
    )
    db.add(entry)

    return ClinicianOverrideResponse(
        log_id=str(log_id),
        status=body.override_status,
        message="Clinician override recorded in audit ledger.",
    )

@router.get("/logs/{patient_id}", response_model=list[AuditLogEntry])
async def get_audit_logs(patient_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.patient_id == patient_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(50)
    )
    logs = result.scalars().all()
    return [
        AuditLogEntry(
            log_id=str(log.log_id),
            patient_id=log.patient_id,
            encounter_id=log.encounter_id,
            trial_id=log.trial_id,
            clinician_override_status=log.clinician_override_status,
            override_reason_text=log.override_reason_text,
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
        )
        for log in logs
    ]

