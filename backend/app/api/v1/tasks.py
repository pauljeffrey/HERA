from fastapi import APIRouter, HTTPException

from app.models.trials import MatchingTaskStatusResponse
from app.services.audit.task_storage import fetch_matching_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=MatchingTaskStatusResponse)
async def get_task_status(task_id: str):
    task = await fetch_matching_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return MatchingTaskStatusResponse(
        task_id=task["task_id"],
        user_id=task["user_id"],
        trial_id=task["trial_id"],
        status=task["status"],
        progress_percentage=int(task.get("progress_percentage") or 0),
        result_summary=task.get("result_summary") or {},
        created_at=task.get("created_at"),
    )
