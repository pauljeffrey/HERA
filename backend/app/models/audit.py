"""Audit dashboard / copilot / override endpoint models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.patients import ExtractedFeature, PatientEncounterNote


class CriterionAuditItem(BaseModel):
    criterion_text: str
    is_inclusion: bool
    verdict: str
    evidence_quote: str | None = None
    encounter_date_cited: str | None = None
    reasoning: str = ""


class AuditDashboardPatient(BaseModel):
    patient_id: str
    trial_id: str
    overall_status: str
    chain_of_thought_summary: str
    criteria_ledger: list[CriterionAuditItem] = Field(default_factory=list)
    encounters: list[PatientEncounterNote] = Field(default_factory=list)
    extracted_features: list[ExtractedFeature] = Field(default_factory=list)
    override_status: str | None = None


class AuditDashboardResponse(BaseModel):
    task_id: str
    trial_id: str
    status: str
    progress_percentage: int = 0
    cohort_size: int = 0
    patient_ids_preview: list[str] = Field(default_factory=list)
    top_diagnoses: list[str] = Field(default_factory=list)
    search_metrics: dict = Field(default_factory=dict)
    patients: list[AuditDashboardPatient] = Field(default_factory=list)


class AuditCopilotRequest(BaseModel):
    message: str
    patient_id: str | None = None
    user_id: str = "clinician"


class AuditCopilotResponse(BaseModel):
    reply: str
    scope: str
    suggested_chips: list[str] = Field(default_factory=list)
    override_applied: bool = False
    updated_patient_id: str | None = None
    updated_overall_status: str | None = None


class ClinicianOverrideRequest(BaseModel):
    patient_id: str
    trial_id: str
    encounter_id: str
    override_status: str = Field(description="APPROVED or OVERRULED")
    override_reason_text: str


class ClinicianOverrideResponse(BaseModel):
    log_id: str
    status: str
    message: str


class AuditLogEntry(BaseModel):
    log_id: str
    patient_id: str
    encounter_id: str
    trial_id: str
    clinician_override_status: str | None = None
    override_reason_text: str | None = None
    timestamp: str
