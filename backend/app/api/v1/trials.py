from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.db_models import AuditLog, MatchJob
from app.models.schemas import JobStatusResponse, TrialMatchRequest, TrialMatchResponse
from app.services.mock_data import MOCK_AUDIT_PAYLOAD
from app.workers.funnel_worker import run_funnel_pipeline

router = APIRouter(prefix="/trials", tags=["trials"])
settings = get_settings()


@router.post("/match", response_model=TrialMatchResponse)
async def match_trials(
    body: TrialMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingest trial matching request into async task queue."""
    if settings.mock_mode:
        job_id, payload = await run_funnel_pipeline(body.trial_id, body.patient_ids)
        job = MatchJob(
            job_id=job_id,
            trial_id=body.trial_id,
            status="completed",
            progress_pct=100.0,
            result_payload=payload.model_dump(),
            search_space_raw=payload.search_space_raw,
            search_space_tier1=payload.search_space_after_tier1,
            search_space_tier2=payload.search_space_after_tier2,
            execution_latency_ms=payload.execution_latency_ms,
            token_cost_usd=payload.token_cost_usd,
        )
        db.add(job)
        return TrialMatchResponse(
            job_id=job_id,
            status="completed",
            message="3-tier funnel pipeline completed (mock mode).",
        )

    try:
        from app.workers.arq_app import get_arq_pool

        pool = await get_arq_pool()
        job = await pool.enqueue_job(
            "run_funnel_pipeline_ctx",
            body.trial_id,
            body.patient_ids,
        )
        match_job = MatchJob(job_id=job.job_id, trial_id=body.trial_id, status="queued")
        db.add(match_job)
        return TrialMatchResponse(
            job_id=job.job_id,
            status="queued",
            message="Job enqueued to Redis/ARQ worker.",
        )
    except Exception as exc:
        job_id, payload = await run_funnel_pipeline(body.trial_id, body.patient_ids)
        return TrialMatchResponse(
            job_id=job_id,
            status="completed",
            message=f"Inline fallback (Redis unavailable): {exc}",
        )


@router.get("/match/{job_id}", response_model=JobStatusResponse)
async def get_match_status(job_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    result = await db.execute(select(MatchJob).where(MatchJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if job and job.result_payload:
        from app.models.schemas import HERA_AuditPayload

        return JobStatusResponse(
            job_id=job_id,
            status=job.status,
            progress_pct=job.progress_pct,
            result=HERA_AuditPayload.model_validate(job.result_payload),
        )
    if settings.mock_mode:
        return JobStatusResponse(
            job_id=job_id,
            status="completed",
            progress_pct=100.0,
            result=MOCK_AUDIT_PAYLOAD,
        )

    raise HTTPException(status_code=404, detail="Job not found")

