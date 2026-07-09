"""Agent 2 — deep eligibility evaluation with structured tool access."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.capabilities import Thinking
from pydantic_ai.exceptions import UsageLimitExceeded
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.models.agents import AnalysisAgentDeps
from app.models.ledger import OverallAuditStatus, PatientTrialAudit
from app.models.llm import select_model, select_vllm_model
from app.services.clinical.notes_index import NotesIndex
from app.services.clinical.patient_data import (
    fetch_patient_notes_bulk,
    get_investigation_result,
    get_lab_result,
    get_patient_diagnoses,
    get_patient_medications,
    get_vitals,
    search_patient_notes,
    validate_constraint,
)
from app.services.clinical.time_utils import parse_at
from app.services.funnel.funnel_orchestrator import PatientTimeline
from app.services.infra.redis_client import save_agent_trace

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are HERA Agent 2, a clinical trial eligibility analyst.
You are HERA's clinical trial eligibility analyst, the Background Compliance Auditor. Your sole task is to perform a rigorous, deterministic, and traceable evaluation of a single patient's longitudinal EHR timeline against a list of clinical trial criteria.

You must output a highly structured JSON response matching the provided protocol schema.

### EXECUTION PROTOCOLS:

1. TEMPORAL TRAJECTORY RESOLUTION:
   - Medical records are written over time. You must evaluate the patient's state as an evolving timeline.
   - Prioritize the most recent encounter records over historical data points.
   - For example: If a patient had an LVEF of 25% two years ago, but their most recent echocardiogram from last week reports 50%, you must evaluate their current state as 50% (and reject them if the trial requires an LVEF <= 35%).
   - You must cite the exact `encounter_date_cited` for every verdict you log.

2. NEGATION DETECTION (The Negation Trap):
   - You must read medical assertions critically. Distinguish between active diagnoses and negated statements.
   - For example: "No history of myocardial infarction", "Patient denies chest pain", "Rule out acute coronary syndrome" do NOT represent active cardiovascular conditions.
   - If a condition is negated or noted as ruled out, mark the corresponding criterion verdict accordingly.

3. STRICT EVIDENCE RETRIEVAL:
   - You must extract a verbatim `evidence_quote` from the patient's timeline for every single criterion you evaluate.
   - Do not summarize, paraphrase, or rewrite the quote. Copy it exactly as it appears in the raw text block, including spelling errors or shorthand.
   - This quote is displayed directly on the clinician's Audit Dashboard to establish data lineage and traceability.

4. OVERALL STATUS LOGIC:
   - `ELIGIBLE`: The patient meets all inclusion criteria and triggers zero exclusion criteria.
   - `EXCLUDED`: The patient explicitly triggers at least one exclusion criterion or fails an inclusion criterion.
   - `REQUIRES_HUMAN_REVIEW`: The patient is missing critical labs required to make a determination, or has conflicting diagnostic assertions in their recent notes that require clinical eyes.

4a. NUMERIC CONSTRAINT VALIDATION (this is your responsibility, not upstream's):
   - The upstream search funnel does not filter patients by numeric constraints — it only narrows by keyword/semantic relevance, so you will see patients whose notes may state a constraint qualitatively ("creatinine elevated", "eGFR severely reduced") or with a spelled-out comparison ("LVEF greater than 35%") rather than a clean symbol/digit pair.
   - You must interpret these yourself: read the actual value or qualitative description in context, and decide MET/FAILED/BORDERLINE/UNKNOWN based on clinical judgment — do not mark a criterion UNKNOWN just because the note didn't use a mathematical symbol.
   - Use `query_patient_record` with `query_type="validate"` for a precise numeric check once you've identified the value; use your own reasoning for qualitative statements.

5. CRITERIA LEDGER:
   - Populate `criteria_ledger` with one entry per trial criterion supplied in deps.
   - Each entry must include `criterion_text`, `is_inclusion`, `verdict`, `evidence_quote`, `encounter_date_cited`, and concise `reasoning`.

6. CLINICAL DATA ACCESS:
   - The prompt already includes the patient's `complete_timeline` — every encounter, chronologically, not just the latest one. A criterion mentioned only in an older note is still visible; read the whole thing before concluding a criterion is unmet.
   - Use `query_patient_record` with a `query_type` keyword:
     - `vitals` — BP, pulse, SpO2, etc.
     - `labs` — lab panels (optional `test_name`, `datetime_iso`)
     - `investigations` — imaging/procedures (optional `investigation`, `datetime_iso`)
     - `medications` — active medication list
     - `diagnoses` — problem list / diagnoses
     - `notes` — full-text search in SOAP notes (requires `search_query`)
     - `validate` — run numeric constraint check (requires `python_code`)
   - Use `find_text_span(start_text, end_text)` to locate the exact verbatim span for an `evidence_quote` — this is how you confirm you are quoting precisely, not paraphrasing.
   - Use `mark_encounter_reviewed`/`list_reviewed_encounters` to track which encounters you've already read this run, so you don't re-derive the same finding twice.
   - Never call the same tool with the same arguments more than once. You have a limited number of tool calls per patient — once you have enough evidence for a criterion, move to the next one; don't re-verify the same fact repeatedly.
   - You have a hard cap on tool calls per patient. Budget it: with N criteria, aim for roughly one tool call per criterion, not per possible tool. As soon as every criterion has a verdict (even UNKNOWN, if the record genuinely lacks the data), stop calling tools and emit your final structured audit immediately — do not keep investigating a criterion you've already reached a verdict on.
"""

def _select_tier3_model():
    """`HERA_TIER3_ENGINE=modal` points this same agent at a self-hosted
    vLLM server (deployed via `workers/modal_app.py`) through an
    OpenAI-compatible endpoint instead of the default cloud model — no
    separate evaluation code path needed."""
    if settings.tier3_engine == "modal":
        if not settings.modal_vllm_base_url:
            raise RuntimeError("HERA_TIER3_ENGINE=modal requires MODAL_VLLM_BASE_URL to be set")
        return select_vllm_model(
            settings.modal_vllm_model,
            base_url=settings.modal_vllm_base_url,
            api_key=settings.modal_vllm_api_key,
        )
    return select_model(settings.model_name, settings.model_api_key)


model = _select_tier3_model()
agent = Agent(
    model,
    deps_type=AnalysisAgentDeps,
    output_type=PatientTrialAudit,
    system_prompt=SYSTEM_PROMPT,
    capabilities=[Thinking(effort="high")],
)


@agent.tool
def query_patient_record(
    ctx: RunContext[AnalysisAgentDeps],
    query_type: Literal["vitals", "labs", "investigations", "medications", "diagnoses", "notes", "validate"],
    patient_id: str | None = None,
    test_name: str | None = None,
    investigation: str | None = None,
    datetime_iso: str | None = None,
    search_query: str | None = None,
    limit: int = 8,
    python_code: str | None = None,
) -> dict:
    """Single DB access tool — `query_type` selects vitals, labs, investigations, medications, diagnoses, notes, or validate."""
    pid = (patient_id or ctx.deps.patient_id or "").strip()
    if not pid:
        raise ValueError("patient_id is required")

    kind = query_type.strip().lower()
    at = parse_at(datetime_iso)

    if kind == "vitals":
        return get_vitals(pid, at)
    if kind == "labs":
        return get_lab_result(pid, at, test_name=test_name)
    if kind == "investigations":
        return get_investigation_result(pid, at, investigation=investigation)
    if kind == "medications":
        return get_patient_medications(pid)
    if kind == "diagnoses":
        return get_patient_diagnoses(pid)
    if kind == "notes":
        if not search_query:
            raise ValueError("search_query is required for query_type=notes")
        return search_patient_notes(pid, search_query, limit=limit)
    if kind == "validate":
        if not python_code:
            raise ValueError("python_code is required for query_type=validate")
        context = {**ctx.deps.constraint_context, "trial_criteria": ctx.deps.trial_criteria}
        return {"result": validate_constraint(python_code, context)}

    raise ValueError(
        f"Unknown query_type {query_type!r}. "
        "Use vitals, labs, investigations, medications, diagnoses, notes, or validate."
    )


@agent.tool
def get_full_patient_timeline(ctx: RunContext[AnalysisAgentDeps], patient_id: str | None = None) -> dict:
    """Complete chronological note text for one patient — not truncated, so a
    criterion mentioned only in an older encounter is still visible."""
    pid = (patient_id or ctx.deps.patient_id or "").strip()
    if not pid:
        raise ValueError("patient_id is required")
    index: NotesIndex | None = ctx.deps.notes_index
    if index is None:
        return {"patient_id": pid, "timeline": ""}
    return {"patient_id": pid, "timeline": index.full_text(pid)}


@agent.tool
def find_text_span(
    ctx: RunContext[AnalysisAgentDeps],
    start_text: str,
    end_text: str = "",
    patient_id: str | None = None,
) -> dict:
    """Find the exact span of text starting at `start_text` (through
    `end_text`, if given) in the patient's notes — for citing verbatim
    evidence with transparency about exactly where it came from."""
    pid = (patient_id or ctx.deps.patient_id or "").strip()
    if not pid:
        raise ValueError("patient_id is required")
    index: NotesIndex | None = ctx.deps.notes_index
    if index is None:
        return {"found": False}
    match = index.find_between(pid, start_text, end_text)
    return {"found": match is not None, **(match or {})}


@agent.tool
def mark_encounter_reviewed(ctx: RunContext[AnalysisAgentDeps], encounter_id: str) -> dict:
    """Log an encounter as already reviewed this evaluation run, to avoid
    re-reading it via other tools."""
    ctx.deps.reviewed_encounter_ids.add(encounter_id)
    return {"reviewed_encounter_ids": sorted(ctx.deps.reviewed_encounter_ids)}


@agent.tool
def unmark_encounter_reviewed(ctx: RunContext[AnalysisAgentDeps], encounter_id: str) -> dict:
    """Remove an encounter from the reviewed log (e.g. it needs a second look)."""
    ctx.deps.reviewed_encounter_ids.discard(encounter_id)
    return {"reviewed_encounter_ids": sorted(ctx.deps.reviewed_encounter_ids)}


@agent.tool
def list_reviewed_encounters(ctx: RunContext[AnalysisAgentDeps]) -> dict:
    """List encounters already reviewed this evaluation run."""
    return {"reviewed_encounter_ids": sorted(ctx.deps.reviewed_encounter_ids)}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    # Retrying a run that already exhausted its request budget just burns
    # the same budget again for the same outcome — let it fail once instead
    # of 3x the LLM calls for nothing.
    retry=retry_if_not_exception_type(UsageLimitExceeded),
)
async def evaluate_patient(
    patient_id: str,
    trial_id: str,
    notes_index: NotesIndex,
    *,
    trial_criteria: list[dict] | None = None,
    trial_criteria_text: str = "",
) -> PatientTrialAudit:
    deps = AnalysisAgentDeps(
        trial_id=trial_id,
        patient_id=patient_id,
        trial_criteria=trial_criteria or [],
        constraint_context={"patient_id": patient_id, "trial_id": trial_id},
        notes_index=notes_index,
    )
    prompt = {
        "trial_id": trial_id,
        "patient_id": patient_id,
        "trial_criteria": deps.trial_criteria,
        "trial_criteria_summary": trial_criteria_text,
        "complete_timeline": notes_index.full_text(patient_id),
    }
    logger.debug("Tier 3: evaluating patient_id=%s trial_id=%s", patient_id, trial_id)
    result = await agent.run(json.dumps(prompt, default=str), deps=deps, usage_limits=UsageLimits(request_limit=15))
    await save_agent_trace(f"{trial_id}:{patient_id}", result.all_messages())
    audit = result.output
    audit.patient_id = patient_id
    audit.trial_id = trial_id
    logger.info(
        "Tier 3: patient_id=%s trial_id=%s verdict=%s criteria_checked=%s",
        patient_id,
        trial_id,
        audit.overall_status,
        len(audit.criteria_ledger),
    )
    return audit


async def evaluate_patients(
    timelines: list[PatientTimeline],
    trial_id: str,
    *,
    trial_criteria: list[dict] | None = None,
    trial_criteria_text: str = "",
) -> list[PatientTrialAudit]:
    """Evaluate a batch of patients, sharing one bulk note fetch across the
    whole batch instead of one DB round-trip per patient."""
    patient_ids = [t.patient_id for t in timelines]
    logger.info("Tier 3: bulk-fetching notes for %s patients (trial_id=%s)", len(patient_ids), trial_id)
    notes_by_patient = fetch_patient_notes_bulk(patient_ids)
    notes_index = NotesIndex.build(notes_by_patient)

    tasks = [
        evaluate_patient(
            patient_id,
            trial_id,
            notes_index,
            trial_criteria=trial_criteria,
            trial_criteria_text=trial_criteria_text,
        )
        for patient_id in patient_ids
    ]
    # One patient's evaluation failing (e.g. hitting its per-patient
    # UsageLimitExceeded after retries) must not discard every other
    # patient's completed audit — gather with return_exceptions and degrade
    # just that one patient to REQUIRES_HUMAN_REVIEW instead of failing the
    # whole batch.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    audits: list[PatientTrialAudit] = []
    for patient_id, result in zip(patient_ids, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("Tier 3: evaluation failed for patient_id=%s: %s", patient_id, result)
            audits.append(
                PatientTrialAudit(
                    patient_id=patient_id,
                    trial_id=trial_id,
                    overall_status=OverallAuditStatus.REQUIRES_HUMAN_REVIEW,
                    chain_of_thought_summary=f"Automated evaluation failed ({result}); needs manual review.",
                    criteria_ledger=[],
                )
            )
        else:
            audits.append(result)
    return audits
