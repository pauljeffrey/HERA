"""Patient chart room / demo showcase models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.ledger import CriteriaVerdict


class PipelineTier(str, Enum):
    FULL_TEXT_SEARCH = "Full-Text Search (FTS)"
    REGEX = "Regex Extraction"
    VECTOR_SEARCH = "Vector Search (VS)"
    AGENTIC_SEARCH = "Agentic Search"


class CertaintyStatus(str, Enum):
    CONFIRMED = "Confirmed"
    NEGATIVE = "Negative / Under Evaluation"
    SPECULATIVE = "Speculative"
    RULED_OUT = "Ruled Out"


class IndividualCriterionEvaluation(BaseModel):
    criterion_text: str = Field(description="The exact text string of the inclusion/exclusion rule from the trial.")
    is_inclusion: bool = Field(description="True if inclusion criterion, False if exclusion.")
    verdict: CriteriaVerdict
    evidence_quote: str | None = Field(
        default=None,
        description="Verbatim quote from the patient's SOAP note supporting this verdict.",
    )
    confidence_score: float = Field(description="Mathematical confidence score (0.0 to 1.0).")


class EligiblePatient(BaseModel):
    patient_id: str
    trial_id: str
    overall_eligible: bool = Field(description="Final binary routing decision.")
    justification: str = Field(description="Step-by-step clinical reasoning for the macro decision.")
    criteria_ledger: list[IndividualCriterionEvaluation] = Field(
        description="Granular breakdown evaluating every rule systematically."
    )


class PatientAuditPayload(BaseModel):
    """Demo audit payload backing the Patient Chart Room (services.clinical.mock_data)."""

    selected_patients: list[EligiblePatient]
    execution_latency_ms: int = Field(description="Time elapsed to process this patient record.")
    token_cost_usd: float = Field(description="Calculated financial cost of API transactions.")
    search_space_raw: int = Field(default=100_000, description="Initial candidate pool size.")
    search_space_after_fts: int = Field(default=10_000)
    search_space_after_vs: int = Field(default=1_000)
    search_space_final: int = Field(default=1)


class ExtractedFeature(BaseModel):
    field_name: str
    raw_text: str
    normalized_value: str
    pipeline_tier: PipelineTier
    confidence_score: float
    encounter_index: int
    source_span_start: int = Field(description="Character offset in SOAP note for highlighting.")
    source_span_end: int
    certainty: CertaintyStatus = CertaintyStatus.CONFIRMED
    negated: bool = False


class PatientEncounterNote(BaseModel):
    encounter_id: str
    encounter_index: int
    encounter_type: str
    soap_note: str
    days_since_baseline: int = 0


class PatientSnapshotResponse(BaseModel):
    patient_id: str
    trial_id: str
    snapshot_id: str
    encounters: list[PatientEncounterNote]
    extracted_features: list[ExtractedFeature]
    audit_payload: PatientAuditPayload


class PatientBiodata(BaseModel):
    patient_id: str
    name: str
    age: int
    sex: str
    specialty_label: str | None = None
    encounter_count: int = 0


class RandomPatientResponse(BaseModel):
    total_patients: int = 0
    patient: PatientBiodata | None = None


class LabResultRow(BaseModel):
    panel: str | None = None
    test_name: str
    test_value: str


class PatientEncounterRecord(BaseModel):
    encounter_id: str
    encounter_index: int
    encounter_type: str = ""
    occurred_at: str | None = None
    soap_excerpt: str = ""
    labs: list[LabResultRow] = Field(default_factory=list)
    investigations: list[str] = Field(default_factory=list)


class PatientClinicalRecord(BaseModel):
    biodata: PatientBiodata
    encounters: list[PatientEncounterRecord] = Field(default_factory=list)
