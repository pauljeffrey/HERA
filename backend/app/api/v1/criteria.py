from fastapi import APIRouter, Query

from app.models.criteria import CriteriaPromptsResponse, RandomCriterionResponse
from app.services.clinical.criteria import get_criteria_prompts, get_random_criterion

router = APIRouter(prefix="/criteria", tags=["criteria"])


@router.get("/prompts", response_model=CriteriaPromptsResponse)
async def list_criteria_prompts(limit: int = Query(default=20, ge=1, le=50)):
    payload = await get_criteria_prompts(limit=limit)
    return CriteriaPromptsResponse.model_validate(payload)


@router.get("/random", response_model=RandomCriterionResponse)
async def random_criterion():
    payload = get_random_criterion()
    return RandomCriterionResponse.model_validate(payload)
