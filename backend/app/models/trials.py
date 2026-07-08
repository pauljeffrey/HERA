"""Trial matching task status model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MatchingTaskStatusResponse(BaseModel):
    task_id: str
    user_id: str
    trial_id: str
    status: str
    progress_percentage: int
    result_summary: dict = Field(default_factory=dict)
    created_at: str | None = None
