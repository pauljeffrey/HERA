from fastapi import APIRouter, HTTPException

from app.models.trials import MatchingTaskStatusResponse
from app.services.audit.task_storage import fetch_matching_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=MatchingTaskStatusResponse)
async def get_task_status(task_id: str):
    task = await fetch_matching_task(task_id)
    if not task or not task.get("task_id"):
        raise HTTPException(status_code=404, detail="Task not found")
    return MatchingTaskStatusResponse(
        task_id=task["task_id"],
        user_id=task.get("user_id") or "clinician",
        trial_id=task.get("trial_id") or "UNKNOWN",
        status=task.get("status") or "processing",
        progress_percentage=int(task.get("progress_percentage") or 0),
        result_summary=task.get("result_summary") or {},
        created_at=task.get("created_at"),
    )
