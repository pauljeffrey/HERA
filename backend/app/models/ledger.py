"""Trial matching audit ledger schemas — Tier 3 agent output and dashboard persistence."""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class CriteriaVerdict(str, Enum):
    MET = "MET"
    FAILED = "FAILED"
    BORDERLINE = "BORDERLINE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OverallAuditStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    OVERRULED_BY_CLINICIAN = "OVERRULED_BY_CLINICIAN"


class CriterionLedgerEntry(BaseModel):
    criterion_text: str = Field(description="Exact inclusion/exclusion rule text from the trial protocol.")
    is_inclusion: bool = Field(description="True for inclusion criteria, false for exclusion.")
    verdict: CriteriaVerdict = Field(description="Per-criterion determination.")
    evidence_quote: str = Field(
        description="Verbatim quote from the patient timeline supporting this verdict — no paraphrasing.",
    )
    encounter_date_cited: str = Field(
        description="Encounter date (ISO or clinical date string) tied to the evidence quote.",
    )
    reasoning: str = Field(
        default="",
        description="Concise clinical rationale connecting evidence to the verdict.",
    )


class PatientTrialAudit(BaseModel):
    patient_id: str
    trial_id: str
    encounter_id: str | None = Field(
        default=None, description="Encounter most relevant to the overall verdict, when applicable."
    )
    overall_status: OverallAuditStatus = Field(
        description="ELIGIBLE, EXCLUDED, or REQUIRES_HUMAN_REVIEW after evaluating all criteria.",
    )
    chain_of_thought_summary: str = Field(
        description="Step-by-step temporal and negation-aware reasoning for the macro eligibility decision.",
    )
    criteria_ledger: List[CriterionLedgerEntry] = Field(
        default_factory=list,
        description="One entry per trial criterion with verdict, evidence quote, and cited encounter date.",
    )


class TrialMatchAuditLedger(BaseModel):
    task_id: str
    trial_id: str
    patients: List[PatientTrialAudit] = Field(default_factory=list)
    search_space_raw: int = 100_000
    search_space_after_fts: int = 10_000
    search_space_after_vs: int = 1_000
    execution_latency_ms: int = 0
    token_cost_usd: float = 0.0
