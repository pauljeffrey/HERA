"""SQLAlchemy ORM models (DATABASE_MODE=local)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(32), nullable=False)
    inclusion_exclusion_criteria: Mapped[str | None] = mapped_column(Text)
    specialty_key: Mapped[str | None] = mapped_column(String(64), index=True)
    specialty_label: Mapped[str | None] = mapped_column(String(128))
    scenario_brief: Mapped[str | None] = mapped_column(Text)
    source_custom_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounters: Mapped[list["Encounter"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"), index=True)
    encounter_id: Mapped[str] = mapped_column(String(64), nullable=False)
    encounter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    encounter_type: Mapped[str | None] = mapped_column(String(128))
    days_since_baseline: Mapped[int] = mapped_column(Integer, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bp: Mapped[str | None] = mapped_column(String(32))
    pulse: Mapped[int | None] = mapped_column(Integer)
    resp_rate: Mapped[int | None] = mapped_column(Integer)
    temperature: Mapped[float | None] = mapped_column(Float)
    spo2: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    patient: Mapped["Patient"] = relationship(back_populates="encounters")
    medications: Mapped[list["EncounterMedication"]] = relationship(back_populates="encounter", cascade="all, delete-orphan")
    investigations: Mapped[list["EncounterInvestigation"]] = relationship(back_populates="encounter", cascade="all, delete-orphan")
    lab_panels: Mapped[list["LabPanel"]] = relationship(back_populates="encounter", cascade="all, delete-orphan")
    diagnoses: Mapped[list["EncounterDiagnosis"]] = relationship(back_populates="encounter", cascade="all, delete-orphan")
    tags: Mapped[list["EncounterTag"]] = relationship(back_populates="encounter", cascade="all, delete-orphan")
    progress_note: Mapped["ClinicalProgressNote | None"] = relationship(back_populates="encounter", uselist=False)


class EncounterMedication(Base):
    __tablename__ = "encounter_medications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    medication: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="medications")


class EncounterInvestigation(Base):
    __tablename__ = "encounter_investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    investigation: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="investigations")


class LabPanel(Base):
    __tablename__ = "lab_panels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    panel_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="lab_panels")
    results: Mapped[list["LabResult"]] = relationship(back_populates="lab_panel", cascade="all, delete-orphan")


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lab_panel_id: Mapped[str] = mapped_column(ForeignKey("lab_panels.id", ondelete="CASCADE"), index=True)
    test_name: Mapped[str] = mapped_column(String(256), nullable=False)
    test_value: Mapped[str] = mapped_column(String(256), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab_panel: Mapped["LabPanel"] = relationship(back_populates="results")


class EncounterDiagnosis(Base):
    __tablename__ = "encounter_diagnoses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="diagnoses")


class EncounterTag(Base):
    __tablename__ = "encounter_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="tags")


class ClinicalProgressNote(Base):
    __tablename__ = "clinical_progress_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"), index=True)
    encounter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    encounter_type: Mapped[str | None] = mapped_column(String(128))
    specialty_key: Mapped[str | None] = mapped_column(String(64))
    specialty_label: Mapped[str | None] = mapped_column(String(128))
    scenario_brief: Mapped[str | None] = mapped_column(Text)
    soap_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="progress_note")


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


class TrialMatchingTask(Base):
    __tablename__ = "trial_matching_tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    trial_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)
    result_summary: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
