"""Background trial matching pipeline — Tier 1/2/3 orchestration."""

from __future__ import annotations

import logging
import time

from app.models.ledger import TrialMatchAuditLedger
from app.models.search import SearchCriteria
from app.services.audit.ledger_utils import top_diagnoses
from app.services.audit.audit_log import insert_audit_log_async
from app.services.audit.task_storage import update_matching_task
from app.services.funnel.funnel_orchestrator import run_fts_vector_filter
from app.agents.analysis_agent import evaluate_patients
from app.config import settings

logger = logging.getLogger(__name__)


async def run_matching_pipeline(
    task_id: str,
    user_id: str,
    trial_id: str,
    search_payload: SearchCriteria,
) -> None:
    started = time.perf_counter()
    logger.info("Task %s: starting matching pipeline for trial_id=%s user_id=%s", task_id, trial_id, user_id)
    try:
        await update_matching_task(task_id, status="processing", progress_percentage=20)

        timelines, metrics = await run_fts_vector_filter(search_payload)
        logger.info(
            "Task %s: funnel complete — raw=%s after_fts=%s after_vs=%s patients_to_evaluate=%s",
            task_id,
            metrics.search_space_raw,
            metrics.search_space_after_fts,
            metrics.search_space_after_vs,
            len(timelines),
        )
        await update_matching_task(task_id, progress_percentage=60)

        logger.info(
            "Task %s: dispatching Tier 3 (engine=%s) for %s patients",
            task_id,
            settings.tier3_engine,
            len(timelines),
        )
        patient_audits = await evaluate_patients(timelines, trial_id, trial_criteria_text=search_payload.response)
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info("Task %s: Tier 3 evaluation complete in %sms, %s audits", task_id, latency_ms, len(patient_audits))

        ledger = TrialMatchAuditLedger(
            task_id=task_id,
            trial_id=trial_id,
            patients=patient_audits,
            search_space_raw=metrics.search_space_raw,
            search_space_after_fts=metrics.search_space_after_fts,
            search_space_after_vs=metrics.search_space_after_vs,
            execution_latency_ms=latency_ms,
            token_cost_usd=round(len(patient_audits) * 0.002, 4),
        )
        summary = ledger.model_dump()
        summary["cohort_size"] = len(patient_audits)
        n_candidates = (search_payload.n_candidates or settings.n_final_candidates)
        summary["patient_ids_preview"] = [audit.patient_id for audit in patient_audits[:n_candidates]]
        summary["top_diagnoses"] = top_diagnoses(patient_audits)

        for audit in patient_audits:
            await insert_audit_log_async(
                patient_id=audit.patient_id,
                encounter_id=audit.encounter_id or "TIER3",
                trial_id=trial_id,
                pydantic_parsed_payload=audit.model_dump(),
            )

        await update_matching_task(
            task_id,
            status="completed",
            progress_percentage=100,
            result_summary=summary,
        )
        logger.info("Task %s completed with %s patient audits", task_id, len(patient_audits))
    except Exception:
        logger.exception("Task %s failed", task_id)
        await update_matching_task(
            task_id,
            status="failed",
            progress_percentage=100,
            result_summary={"error": "An unexpected error occurred while running the matching pipeline. Please try again..."},
        )
