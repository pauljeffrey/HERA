"""Chat endpoint request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.search import SearchCriteria


class ChatRequest(BaseModel):
    message: str
    patient_id: str | None = None
    trial_id: str | None = None
    conversation_id: str | None = Field(
        default=None, description="Resumes a prior conversation's history from Redis. Omit to start a new one."
    )


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str = Field(description="Pass this back on the next request to continue the conversation.")
    suggested_patient_id: str | None = None
    search_payload: SearchCriteria | None = None
