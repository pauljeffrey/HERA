"""Dependency and reply types for the pydantic_ai agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.search import SearchCriteria


class Response(BaseModel):
    """Chat agent's structured output."""

    response: str = Field(description="Response to the user")
    search_payload: SearchCriteria | None = None


class AgentDeps(BaseModel):
    """Base deps shared across agents."""

    user_id: str = "clinician"


class ChatAgentDeps(AgentDeps):
    trial_id: str | None = None
    patient_id: str | None = None
    dispatched_task_ids: list[str] = Field(default_factory=list)


class AnalysisAgentDeps(AgentDeps):
    """Deps for the Tier 3 analysis agent — carries a per-batch session
    scratchpad (notes already fetched, encounters already reviewed) so
    repeat tool calls within one evaluate_patients() run don't re-hit the DB.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    trial_id: str = ""
    patient_id: str = ""
    trial_criteria: list[dict[str, Any]] = Field(default_factory=list)
    constraint_context: dict[str, Any] = Field(default_factory=dict)
    notes_index: Any = None
    reviewed_encounter_ids: set[str] = Field(default_factory=set)


class AuditCopilotDeps(AgentDeps):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str = ""
    task: dict[str, Any] = Field(default_factory=dict)
    patient_id: str | None = None
    override_applied: bool = False
    updated_patient_id: str | None = None
    updated_overall_status: str | None = None


class AuditCopilotReply(BaseModel):
    reply_markdown: str = Field(description="Markdown response for the copilot panel.")
    scope_label: str = Field(description="Context tag such as @Patient_1042 or @Entire_Cohort.")
    suggested_chips: list[str] = Field(default_factory=list, max_length=4)
    override_applied: bool = False
    updated_patient_id: str | None = None
    updated_overall_status: str | None = None
