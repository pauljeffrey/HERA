"""audit_logs persistence."""

from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.db.supabase_client import get_supabase_client


async def insert_audit_log_async(**kwargs: Any) -> str:
    settings = get_settings()
    log_id = str(uuid.uuid4())
    payload = {"log_id": log_id, **kwargs}

    if settings.database_mode == "supabase":
        get_supabase_client().table("audit_logs").insert(payload).execute()
        return log_id

    from app.db.database import AsyncSessionLocal
    from app.db.models import AuditLog

    async with AsyncSessionLocal() as session:
        session.add(AuditLog(**payload))
        await session.commit()
    return log_id


async def fetch_audit_logs(patient_id: str, *, limit: int = 50) -> list[dict]:
    settings = get_settings()
    if settings.database_mode == "supabase":
        result = (
            get_supabase_client()
            .table("audit_logs")
            .select("*")
            .eq("patient_id", patient_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.db.models import AuditLog

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.patient_id == patient_id)
                .order_by(AuditLog.timestamp.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "log_id": str(r.log_id),
                "patient_id": r.patient_id,
                "encounter_id": r.encounter_id,
                "trial_id": r.trial_id,
                "clinician_override_status": r.clinician_override_status,
                "override_reason_text": r.override_reason_text,
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            }
            for r in rows
        ]
