"""trial_matching_tasks persistence."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db.supabase_client import get_supabase_client
from app.services.infra.redis_client import get_task_state, set_task_state


async def create_matching_task(
    task_id: str,
    user_id: str,
    trial_id: str,
    status: str = "processing",
    progress_percentage: int = 10,
    result_summary: dict | None = None,
) -> None:
    row = {
        "task_id": task_id,
        "user_id": user_id,
        "trial_id": trial_id,
        "status": status,
        "progress_percentage": progress_percentage,
        "result_summary": result_summary or {},
    }
    await set_task_state(task_id, **{k: v for k, v in row.items() if k != "task_id"})

    settings = get_settings()
    if settings.database_mode == "supabase":
        get_supabase_client().table("trial_matching_tasks").insert(row).execute()
        return

    from app.db.database import AsyncSessionLocal
    from app.db.models import TrialMatchingTask

    async with AsyncSessionLocal() as session:
        session.add(TrialMatchingTask(**row))
        await session.commit()


async def update_matching_task(task_id: str, **fields: Any) -> None:
    await set_task_state(task_id, **fields)

    settings = get_settings()
    if settings.database_mode == "supabase":
        get_supabase_client().table("trial_matching_tasks").update(fields).eq("task_id", task_id).execute()
        return

    from sqlalchemy import update

    from app.db.database import AsyncSessionLocal
    from app.db.models import TrialMatchingTask

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(TrialMatchingTask).where(TrialMatchingTask.task_id == task_id).values(**fields)
        )
        await session.commit()


async def fetch_matching_task(task_id: str) -> dict | None:
    cached = await get_task_state(task_id)
    if cached:
        return cached

    settings = get_settings()
    if settings.database_mode == "supabase":
        result = (
            get_supabase_client()
            .table("trial_matching_tasks")
            .select("*")
            .eq("task_id", task_id)
            .limit(1)
            .execute()
        )
        task = result.data[0] if result.data else None
        if task:
            await set_task_state(task_id, **{k: v for k, v in task.items() if k != "task_id"})
        return task

    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.db.models import TrialMatchingTask

    async with AsyncSessionLocal() as session:
        task = (
            await session.execute(select(TrialMatchingTask).where(TrialMatchingTask.task_id == task_id))
        ).scalar_one_or_none()
        if not task:
            return None
        row = {
            "task_id": task.task_id,
            "user_id": task.user_id,
            "trial_id": task.trial_id,
            "status": task.status,
            "progress_percentage": task.progress_percentage,
            "result_summary": task.result_summary,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        await set_task_state(task_id, **{k: v for k, v in row.items() if k != "task_id"})
        return row
