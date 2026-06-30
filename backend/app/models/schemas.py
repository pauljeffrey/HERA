from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CriteriaVerdict(str, Enum):
    MET = "MET"
    FAILED = "FAILED"
    BORDERLINE = "BORDERLINE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PipelineTier(str, Enum):
    TIER_1_BM25 = "Tier 1 - BM25"
    TIER_2_REGEX = "Tier 2 - Regex"
    TIER_2_VECTOR = "Tier 2 - Vector"
    TIER_3_LLM = "Tier 3 - LLM Agent"


class CertaintyStatus(str, Enum):
    CONFIRMED = "Confirmed"
    NEGATIVE = "Negative / Under Evaluation"
    SPECULATIVE = "Speculative"
    RULED_OUT = "Ruled Out"


class IndividualCriterionEvaluation(BaseModel):
    criterion_text: str = Field(description="The exact text string of the inclusion/exclusion rule from the trial.")
    is_inclusion: bool = Field(description="True if inclusion criterion, False if exclusion.")
    verdict: CriteriaVerdict
    evidence_quote: Optional[str] = Field(
        default=None,
        description="Verbatim quote from the patient's SOAP note supporting this verdict.",
    )
    confidence_score: float = Field(description="Mathematical confidence score (0.0 to 1.0).")


class EligiblePatient(BaseModel):
    patient_id: str
    trial_id: str
    overall_eligible: bool = Field(description="Final binary routing decision.")
    justification: str = Field(description="Step-by-step clinical reasoning for the macro decision.")
    criteria_ledger: List[IndividualCriterionEvaluation] = Field(
        description="Granular breakdown evaluating every rule systematically."
    )


class HERA_AuditPayload(BaseModel):
    selected_patients: List[EligiblePatient]
    execution_latency_ms: int = Field(description="Time elapsed to process this patient record.")
    token_cost_usd: float = Field(description="Calculated financial cost of API transactions.")
    search_space_raw: int = Field(default=100_000, description="Initial candidate pool size.")
    search_space_after_tier1: int = Field(default=10_000)
    search_space_after_tier2: int = Field(default=1_000)
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
    encounters: List[PatientEncounterNote]
    extracted_features: List[ExtractedFeature]
    audit_payload: HERA_AuditPayload


class TrialMatchRequest(BaseModel):
    trial_id: str
    patient_ids: Optional[List[str]] = None


class TrialMatchResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: float
    result: Optional[HERA_AuditPayload] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    patient_id: Optional[str] = None
    trial_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    suggested_patient_id: Optional[str] = None


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
    clinician_override_status: Optional[str] = None
    override_reason_text: Optional[str] = None
    timestamp: str

