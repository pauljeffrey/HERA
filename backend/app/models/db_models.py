import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    encounter_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trial_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    original_llm_raw_response: Mapped[str | None] = mapped_column(Text)
    pydantic_parsed_payload: Mapped[dict | None] = mapped_column(JSON)
    clinician_override_status: Mapped[str | None] = mapped_column(String(32))
    override_reason_text: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientSnapshot(Base):
    __tablename__ = "patient_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    trial_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    timeline_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchJob(Base):
    __tablename__ = "match_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trial_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    result_payload: Mapped[dict | None] = mapped_column(JSON)
    search_space_raw: Mapped[int] = mapped_column(Integer, default=100_000)
    search_space_tier1: Mapped[int] = mapped_column(Integer, default=10_000)
    search_space_tier2: Mapped[int] = mapped_column(Integer, default=1_000)
    execution_latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
