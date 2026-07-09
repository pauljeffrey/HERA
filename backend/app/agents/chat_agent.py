from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional, List

from pydantic_ai import Agent, RunContext, UsageLimits

from app.config import settings
from app.models.agents import ChatAgentDeps, Response
from app.models.llm import select_model
from app.models.search import NumericalConstraint, SearchCriteria
from app.services.audit.task_storage import create_matching_task, update_matching_task
from app.services.clinical.patient_data import (
    compute_cohort_statistic,
    execute_analytical_sql_query as run_analytical_sql_query,
    get_patient_clinical_snapshot as build_patient_clinical_snapshot,
    get_patient_complete_timeline as build_patient_complete_timeline,
    query_clinical_database_metadata as fetch_database_metadata,
)
from app.services.clinical.plotting import render_chart
from app.services.clinical.time_utils import parse_at
from app.services.funnel.match_pipeline import run_matching_pipeline
from app.services.infra.redis_client import load_chat_history, save_chat_history

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are HERA (Healthcare Eligibility & Reasoning Agent ), an agent that helps doctors find potential patient candidates for clinical trials based on the patient's medical history (stored in the EHR and attached you as a knowledge base) and clinical trial requirements.

Your primary role is to act as a highly competent, empathetic, and clinically precise interface between practicing physicians and the underlying clinical databases.

You operate under three distinct behavioral modes depending on the user's intent. You must classify the incoming query into one of these modes and execute the corresponding instructions:

---
MODE 1: CLINICAL DATABASE QUERYING (Text-to-SQL / Database Analytics)
- TRIGGER: The user asks general population-level or statistical questions about the database (e.g., "What is our current ICU readmission rate for HFrEF patients?", "Show me average blood pressure ranges for patients over 65").
- ACTIONS:
  1. Do not initiate a trial matching task.
  2. Tool choice matters here:
     - Counting rows in a table (patients, encounters, labs, etc.) or getting table sizes → `query_clinical_database_metadata`.
     - Any numeric aggregate over a real column (average/min/max/sum of age, vitals, labs) or anything needing a WHERE/GROUP BY/JOIN → `execute_analytical_sql_query`.
     - `compute_database_statistic` is ONLY for "how many patients' notes mention <free-text term>" style prevalence checks — never use it to count total rows or compute a column aggregate; it will not give you that.
  3. Respond to the clinician with clear Markdown tables or concise clinical summaries.
  4. If the question is naturally visual (a distribution, trend, or comparison across categories), call `generate_chart` with the computed labels/values and embed the returned `image_url` as a markdown image (`![title](image_url)`) directly in your response.

---
MODE 2: INDIVIDUAL PATIENT CHAT & EXPLORATION (Context-Bound RAG)
- TRIGGER: The user refers to a specific patient, asks to explore a patient's timeline, or asks questions during an active audit (e.g., "Why did Patient 104's creatinine spike in Nov 2025?", "What medications is PT-894 on?").
- ACTIONS:
  1. Bind your context to the target `patient_id`.
  2. Use `get_patient_complete_timeline` to fetch their chronological longitudinal notes.
  3. Use `get_patient_clinical_snapshot` when structured vitals, labs, medications, or diagnoses are needed.
  4. Perform a focused analysis. Cite specific encounter dates (e.g., "On 2025-11-04 during an ICU Admission...").
  5. Keep answers highly objective, structured in standard medical format (SBAR or soap notes summary if requested), and do not hallucinate physiological data.

---
MODE 3: CLINICAL TRIAL MATCHING DISPATCH
- TRIGGER: The user provides a list of inclusion/exclusion criteria or describes a study protocol and asks to find eligible patients (e.g., "Find patients for a new study: LVEF under 35%, no severe CKD, age 18-80").
- ACTIONS:
  1. Do not attempt to run a full table search directly in chat.
  2. Synthesize the criteria into a structured configuration in your output fields (`lexical_keywords`, `semantic_query`, `numerical_constraints`, `target_patient_ids`).
  3. Also produce `semantic_query_variants`: 2-4 DISSIMILAR but clinically relevant rephrasings of `semantic_query` — vary terminology and angle (e.g. layman vs. clinical phrasing, symptom-first vs. diagnosis-first, different synonyms for the same condition) so vector search isn't dependent on one exact phrasing matching the note. Do not just reorder the same words — genuinely vary vocabulary and framing.
  4. Call the `dispatch_trial_matching_task` tool with all of the above.
  5. Return a natural language summary validating the criteria you parsed, alongside the tracking payload and a clean redirect link to the Audit Dashboard page `/audit/[task_id]`.

---
GENERAL CLINICAL PROTOCOLS:
- Use formal medical terminology. Address clinicians as peers.
- Never make up clinical values, dates, or names.
- Ensure all numbers display their corresponding units (e.g., "mg/dL", "%", "mmHg").
- Always use LaTeX-style notation for mathematical formatting (e.g., $LVEF \\le 35\\%$, $Creatinine > 2.0\\text{ mg/dL}$). Do not use unicode characters like ≤ or ≥ in formulas.
- Never call the same tool with the same arguments more than once in a turn. Once a tool call returns data that answers the question, stop calling tools and write your final response immediately using that data.
"""

model = select_model(settings.model_name, settings.model_api_key)
chat_agent = Agent(model, deps_type=ChatAgentDeps, output_type=Response, system_prompt=SYSTEM_PROMPT)


@chat_agent.tool
def get_patient_clinical_snapshot(
    ctx: RunContext[ChatAgentDeps],
    patient_id: str,
    datetime_iso: str | None = None,
) -> dict[str, Any]:
    """Fetch vitals, labs, investigations, medications, and diagnoses for one patient."""
    bound_id = patient_id or ctx.deps.patient_id
    if not bound_id:
        raise ValueError("patient_id is required")
    return build_patient_clinical_snapshot(bound_id, parse_at(datetime_iso))


@chat_agent.tool
def get_patient_complete_timeline(ctx: RunContext[ChatAgentDeps], patient_id: str) -> dict[str, Any]:
    """Fetch chronological SOAP notes and encounter metadata for one patient."""
    bound_id = patient_id or ctx.deps.patient_id
    if not bound_id:
        raise ValueError("patient_id is required")
    return build_patient_complete_timeline(bound_id)


@chat_agent.tool
def query_clinical_database_metadata(ctx: RunContext[ChatAgentDeps]) -> dict[str, Any]:
    """Return table inventory and row counts for population-level analytics."""
    logger.info("tool call: query_clinical_database_metadata")
    return fetch_database_metadata()


@chat_agent.tool
def execute_analytical_sql_query(
    ctx: RunContext[ChatAgentDeps],
    sql_query: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Run a read-only SELECT query for cohort analytics. Mutating SQL is rejected."""
    logger.info("tool call: execute_analytical_sql_query sql=%r limit=%s", sql_query, limit)
    try:
        return run_analytical_sql_query(sql_query, limit=limit)
    except Exception as exc:
        logger.warning("execute_analytical_sql_query failed sql=%r: %s", sql_query, exc)
        raise


@chat_agent.tool
def compute_database_statistic(
    ctx: RunContext[ChatAgentDeps],
    metric: str,
    aggregation: str = "count",
    patient_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compute a lightweight cohort statistic when SQL is unnecessary."""
    logger.info("tool call: compute_database_statistic metric=%r aggregation=%r", metric, aggregation)
    result = compute_cohort_statistic(metric, patient_ids=patient_ids, aggregation=aggregation)
    logger.info("tool result: compute_database_statistic -> %s", result)
    return result


@chat_agent.tool
def generate_chart(
    ctx: RunContext[ChatAgentDeps],
    chart_type: str,
    labels: list[str],
    values: list[float],
    title: str,
    x_label: str = "",
    y_label: str = "",
) -> dict[str, Any]:
    """Render a bar/line/scatter chart from computed labels+values and save
    it as an image. Returns an `image_url` — embed it as a markdown image
    in your response so the clinician sees it inline."""
    path = render_chart(chart_type, labels, values, title, x_label=x_label, y_label=y_label)
    return {"image_url": f"{settings.public_base_url}/plots/{path.name}", "title": title}


@chat_agent.tool
async def dispatch_trial_matching_task(
    ctx: RunContext[ChatAgentDeps],
    lexical_keywords: Optional[List[str]],
    semantic_query: Optional[str],
    numerical_constraints: List[NumericalConstraint],
    criteria_summary: str,
    semantic_query_variants: Optional[List[str]] = None,
    n_candidates: Optional[int] = 5,
) -> dict[str, Any]:
    """Create a clinical trial matching task and start FTS → vector search → Agentic search pipeline.
    Arguments:
    - lexical_keywords: list of keywords to search for in the database
    - semantic_query: a natural language query to search for in the database
    - numerical_constraints: list of numerical constraints to search for in the database
    - criteria_summary: a summary of the criteria to search for in the database
    - semantic_query_variants: 2-4 dissimilar-but-relevant rephrasings of semantic_query, to widen vector search recall
    - n_candidates: number of final candidates to return
    """
    if ctx.deps.dispatched_task_ids:
        # A matching pipeline is a real side effect (creates a task, runs the
        # full funnel + Tier 3 in the background) — dispatching twice for one
        # user request is never correct, even if the model reconsiders its
        # criteria mid-turn. Return the existing task instead of starting a
        # second one.
        existing_id = ctx.deps.dispatched_task_ids[0]
        logger.warning("Ignoring duplicate dispatch_trial_matching_task call; task %s already dispatched", existing_id)
        return {
            "task_id": existing_id,
            "audit_dashboard_url": f"/audit/{existing_id}",
            "status": "processing",
            "note": "A matching task was already dispatched for this request — reuse this task_id, do not dispatch again.",
        }

    task_id = str(uuid.uuid4())
    trial_id = ctx.deps.trial_id or f"TRIAL-{uuid.uuid4().hex[:8].upper()}"
    search_payload = SearchCriteria(
        response=criteria_summary,
        lexical_keywords=lexical_keywords or [],
        semantic_query=semantic_query or "",
        semantic_query_variants=semantic_query_variants or [],
        numerical_constraints=numerical_constraints,
        n_candidates = n_candidates or settings.n_final_candidates
    )

    await create_matching_task(
        task_id,
        user_id=ctx.deps.user_id,
        trial_id=trial_id,
        status="processing",
        progress_percentage=10,
        result_summary={"response": criteria_summary},
    )
    await update_matching_task(task_id, progress_percentage=10)

    asyncio.create_task(
        run_matching_pipeline(task_id, ctx.deps.user_id, trial_id, search_payload)
    )
    logger.info(
        "Dispatched task %s for trial %s with %s FTS keywords",
        task_id,
        trial_id,
        len(search_payload.lexical_keywords),
    )

    ctx.deps.dispatched_task_ids.append(task_id)
    return {
        "task_id": task_id,
        "trial_id": trial_id,
        "audit_dashboard_url": f"/audit/{task_id}",
        "status": "processing",
        "lexical_keywords": search_payload.lexical_keywords,
    }


async def run_chat_agent(
    message: str,
    agent_deps: Optional[ChatAgentDeps] = None,
    conversation_id: Optional[str] = None,
) -> tuple[Response, str]:
    """Run the chat agent, resuming and persisting history in Redis for `conversation_id`."""
    deps = agent_deps or ChatAgentDeps()
    conversation_id = conversation_id or str(uuid.uuid4())
    message_history = await load_chat_history(conversation_id)
    result = await chat_agent.run(
        message,
        deps=deps,
        message_history=message_history,
        # A tool stuck feeding the model unhelpful results (e.g. a metric it
        # can't compute) can otherwise loop for many round-trips — bound it
        # so a bad turn fails in seconds, not minutes.
        usage_limits=UsageLimits(request_limit=12),
    )
    await save_chat_history(conversation_id, result.all_messages())
    return result.output, conversation_id