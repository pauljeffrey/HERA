"""Criteria prompt endpoint models."""

from __future__ import annotations

from pydantic import BaseModel


class CriteriaPromptItem(BaseModel):
    text: str
    patient_count: int


class CriteriaPromptsResponse(BaseModel):
    source: str
    count: int
    prompts: list[CriteriaPromptItem]


class RandomCriterionResponse(BaseModel):
    source: str
    count: int
    criterion: CriteriaPromptItem | None = None
