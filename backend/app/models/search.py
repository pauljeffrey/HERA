"""Search criteria shared by the chat dispatcher, funnel, and math guard.

This is the one payload type that flows end-to-end: the chat agent builds it,
`funnel_orchestrator` and `math_guard` consume it unchanged. Previously this
concept was split across `models/agent.py::SearchPayload` and
`models/search_payload.py::AgentOneSearchPayload` with different field names,
which had drifted out of sync with several call sites.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NumericalOperator(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    RANGE = "RANGE"


class NumericalConstraint(BaseModel):
    parameter_name: str = Field(description="Clinical metric name, e.g. LVEF, Serum Creatinine, Platelets")
    triggers: list[str] = Field(
        description="Synonyms, keywords, abbreviations, or regexes to search as anchor text."
    )
    operator: NumericalOperator
    target_value: float = Field(description="Primary numerical threshold")
    secondary_value: float | None = Field(default=None, description="Upper bound if operator is RANGE")
    unit_regex: str | None = Field(default=None, description="Optional regex for unit matching, e.g. '%|percent'")
    window_chars: int = Field(
        default=120,
        description="Character window sliced around the anchor keyword before extracting numbers.",
    )


class SearchCriteria(BaseModel):
    response: str = Field(description="Markdown summary shown to the clinician")
    lexical_keywords: list[str] = Field(
        default_factory=list, description="Keywords and phrases for Tier 1 full-text search (BM25/FTS)."
    )
    semantic_query: str = Field(
        default="", description="Dense clinical summary optimized for Tier 2 embedding similarity search."
    )
    semantic_query_variants: list[str] = Field(
        default_factory=list,
        description=(
            "2-4 additional dissimilar-but-relevant rephrasings of `semantic_query` "
            "(different clinical terminology/angles on the same criteria). Vector "
            "search runs all of them and merges results, widening recall instead of "
            "depending on one phrasing matching the note's wording."
        ),
    )
    numerical_constraints: list[NumericalConstraint] = Field(
        default_factory=list,
        description="Explicit numerical criteria to enforce via the windowed math guard.",
    )
    target_patient_ids: list[str] | None = Field(
        default=None, description="Optional specific cohort filter if requested by the user."
    )
    n_candidates: int | None = Field(
        default=None, description="Number of final candidates to return based on user's request.."
    )