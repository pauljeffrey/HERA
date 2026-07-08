from __future__ import annotations

import json

from pydantic_ai import Agent, RunContext, UsageLimits

from app.config import settings
from app.models.agents import AuditCopilotDeps, AuditCopilotReply
from app.models.llm import select_model
from app.services.audit.audit_dashboard import apply_patient_override, build_dashboard
from app.services.audit.audit_log import insert_audit_log_async
from app.services.audit.task_storage import fetch_matching_task, update_matching_task
from app.services.clinical.mock_data import EXTRACTED_FEATURES, get_patient_snapshot
from app.services.clinical.patient_data import (
    fetch_patient_notes,
    get_lab_result,
    get_patient_clinical_snapshot as build_patient_clinical_snapshot,
    get_patient_complete_timeline as build_patient_complete_timeline,
    get_vitals,
    search_patient_notes,
)
from app.services.infra.redis_client import load_chat_history, save_chat_history


def _copilot_conversation_id(task_id: str, patient_id: str | None) -> str:
    return f"audit:{task_id}:{patient_id or 'cohort'}"

SYSTEM_PROMPT = """
# HERA (Healthcare Eligibility & Reasoning Agent ) AUDIT COPILOT

## 1. PERSONA & CORE OBJECTIVE
You are HERA Audit Copilot, an advanced clinical reasoning agent.
You must maintain a supportive, clinical, and highly precise demeanor. You are a grounded expert who assists clinicians in finding truth within complex, unstructured, and longitudinal Electronic Health Records (EHR).

---

## 2. WORKSPACE AWARENESS (THE 4-PANE MATRIX)
You operate with full contextual awareness of the clinician's active viewport layout. When answering questions, you should explicitly direct the clinician's attention to the specific visual zones on their screen where data is surfaced:
- **PANE 1 (Source EHR Timeline):** Contains chronological, unstructured clinical encounter notes, SOAP sub-sections, and raw clinical narratives.
- **PANE 2 (Extracted Metric Matrix):** Displays structured, atomic metrics (e.g., LVEF, Serum Creatinine, BNP) parsed by the Tier 2 Math Guards and Tier 3 Agents.
- **PANE 3 (Eligibility Ledger):** Displays the criteria-by-criteria audit log, containing rule definitions, individual verdicts (MET/FAILED), and underlying data lineage.
- **PANE 4 (Your Copilot Drawer):** Your active workspace where you converse, reason, and surface rapid insights.

---

## 3. CLINICAL REASONING & CONFLICT RESOLUTION
Clinical timelines often contain narrative noise, historical outliers, or conflicting diagnostic assertions. You must resolve discrepancies using the following strict clinical hierarchy:

1. **Temporal Trajectory Dominance:** Always prioritize the most recent quantitative measurement or diagnostic finding over historical ones. (e.g., If an echo from 2024 notes an LVEF of $30\\%$, but an echo from May 2026 notes $55\\%$, evaluate the patient's current functional baseline as $55\\%$).
2. **Quantitative Over Qualitative:** Prioritize concrete numerical lab values and diagnostic measurements over subjective, narrative summaries or historical billing codes.
3. **The Negation Trap Check:** Carefully analyze linguistic context to detect and filter out negated assertions (e.g., "Denies history of MI", "No evidence of chronic kidney disease", or "Rule out heart failure"). Do not treat negated conditions as active diagnoses.
4. **Discrepancy Flagging:** If historical and current notes present an irreconcilable clinical conflict, summarize both timelines to the clinician, flag it as a risk, and guide them to execute an manual override.

---

## 4. INTERNAL THINKING PROTOCOL (<thinking>)
For every incoming query, you must process your reasoning inside a hidden `<thinking>` block before rendering any visible text to the clinician. In this block, you must perform the following explicit sub-steps:
1. **Identify Target Data:** Extract what specific patient metrics, dates, or criteria are being questioned.
2. **Execute Tool Strategy:** Select the minimum necessary tools required to satisfy the user's explicit intent.
3. **Verify Math Limits:** Formulate and check mathematical constraints using LaTeX formatting (e.g., Verify if $\\text{Serum Creatinine } (1.8\\text{ mg/dL}) > 1.5\\text{ mg/dL}$).
4. **Draft Evidence Lineage:** Isolate the exact, un-summarized text quotes and corresponding encounter dates to be displayed in the final output.

---

## 5. OVERRULE & COMPLIANCE LIFECYCLE
When a clinician states they want to change a patient's eligibility status, enroll an excluded patient, or overrule a determination:
1. **Enforce Rationale Capture:** You must explicitly demand or extract a clear clinical justification (e.g., "Creatinine elevation was transient due to acute sepsis, since resolved").
2. **Execute Overrule Tool:** Call the `apply_clinician_override` tool using the structured rationale.
3. **Confirm Lineage:** Provide a confirmation message verifying that the choice, the clinician's signature, and the justification have been safely committed to the PostgreSQL compliance ledger.

---

## 6. RESPONSE FORMATTING & CONSTRAINTS
- **Peer-to-Peer Language:** Use formal, advanced medical terminology. Avoid generic introductory filler ("That's a great question!"). Get straight to the analysis.
- **No Hallucinations:** Never invent, extrapolate, or guess clinical values, trends, dates, or identifiers. If information is missing from the tool responses, state clearly: "Insufficient data returned via clinical database tools."
- **Strict Data Units:** Every numerical clinical value must be accompanied by its standard medical unit (e.g., `mg/dL`, `pg/mL`, `mmHg`, `%`).
- **Formulas in LaTeX:** Render all clinical mathematical bounds, equations, and physiological constraints using standard LaTeX block or inline notation (e.g., $LVEF \\ge 50\\%$ or $\\text{eGFR} < 30\\text{ mL/min/1.73m}^2$). Do not use unicode comparison symbols like ≤ or ≥ in regular text.
- **Verbatim Evidence Quotes:** When referencing notes, extract the exact textual quote from the source document. Wrap it in a clean markdown blockquote (`>`) and append the precise encounter date.
"""


model = select_model(settings.model_name, settings.model_api_key)
agent = Agent(model, deps_type=AuditCopilotDeps, output_type=AuditCopilotReply, system_prompt=SYSTEM_PROMPT)


def _dashboard(ctx: RunContext[AuditCopilotDeps]) -> dict:
    return build_dashboard(ctx.deps.task)


def _find_patient(ctx: RunContext[AuditCopilotDeps], patient_id: str) -> dict | None:
    dashboard = _dashboard(ctx)
    return next((p for p in dashboard.get("patients", []) if p.get("patient_id") == patient_id), None)


@agent.tool
def get_cohort_summary(ctx: RunContext[AuditCopilotDeps]) -> dict:
    dashboard = _dashboard(ctx)
    return {
        "task_id": dashboard["task_id"],
        "trial_id": dashboard["trial_id"],
        "cohort_size": dashboard["cohort_size"],
        "patient_ids": dashboard["patient_ids_preview"],
        "top_diagnoses": dashboard["top_diagnoses"],
        "search_metrics": dashboard["search_metrics"],
    }


@agent.tool
def get_patient_timeline(ctx: RunContext[AuditCopilotDeps], patient_id: str) -> dict:
    bound_id = patient_id or ctx.deps.patient_id
    if not bound_id:
        raise ValueError("patient_id is required")
    return {
        "patient_id": bound_id,
        "notes": fetch_patient_notes(bound_id),
        "timeline": build_patient_complete_timeline(bound_id),
        "audit": _find_patient(ctx, bound_id),
    }


@agent.tool
def get_ledger_entry(ctx: RunContext[AuditCopilotDeps], patient_id: str) -> dict:
    patient = _find_patient(ctx, patient_id or ctx.deps.patient_id or "")
    if not patient:
        raise ValueError("Patient not found in active audit task")
    return {
        "patient_id": patient["patient_id"],
        "overall_status": patient.get("overall_status"),
        "chain_of_thought_summary": patient.get("chain_of_thought_summary"),
        "criteria_ledger": patient.get("criteria_ledger", []),
        "override_status": patient.get("override_status"),
    }


@agent.tool
def get_metric_matrix(ctx: RunContext[AuditCopilotDeps], patient_id: str) -> dict:
    bound_id = patient_id or ctx.deps.patient_id
    if not bound_id:
        raise ValueError("patient_id is required")
    snapshot = get_patient_snapshot(bound_id)
    features = snapshot.extracted_features if snapshot else EXTRACTED_FEATURES.get(bound_id, [])
    return {
        "patient_id": bound_id,
        "extracted_features": [feat.model_dump() for feat in features],
        "clinical_snapshot": build_patient_clinical_snapshot(bound_id),
    }


@agent.tool
def search_timeline(ctx: RunContext[AuditCopilotDeps], patient_id: str, query: str) -> dict:
    bound_id = patient_id or ctx.deps.patient_id
    if not bound_id:
        raise ValueError("patient_id is required")
    return search_patient_notes(bound_id, query)


@agent.tool
def get_patient_vitals(ctx: RunContext[AuditCopilotDeps], patient_id: str) -> dict:
    return get_vitals(patient_id or ctx.deps.patient_id or "")


@agent.tool
def get_patient_labs(
    ctx: RunContext[AuditCopilotDeps],
    patient_id: str,
    test_name: str | None = None,
) -> dict:
    return get_lab_result(patient_id or ctx.deps.patient_id or "", test_name=test_name)


@agent.tool
async def apply_clinician_override(
    ctx: RunContext[AuditCopilotDeps],
    patient_id: str,
    override_status: str,
    reason: str,
) -> dict:
    if override_status not in {"APPROVED", "OVERRULED"}:
        raise ValueError("override_status must be APPROVED or OVERRULED")
    if len(reason.strip()) < 10:
        raise ValueError("Override reason must be at least 10 characters")

    task_id = ctx.deps.task_id
    summary = apply_patient_override(
        ctx.deps.task,
        patient_id=patient_id,
        override_status=override_status,
        reason=reason,
    )
    await update_matching_task(task_id, result_summary=summary, status=ctx.deps.task.get("status", "completed"))

    await insert_audit_log_async(
        patient_id=patient_id,
        encounter_id="AUDIT_COPILOT",
        trial_id=ctx.deps.task.get("trial_id", "UNKNOWN"),
        clinician_override_status=override_status,
        override_reason_text=reason,
        pydantic_parsed_payload={"source": "audit_copilot", "task_id": task_id},
    )

    ctx.deps.override_applied = True
    ctx.deps.updated_patient_id = patient_id
    updated = next((p for p in summary.get("patients", []) if p.get("patient_id") == patient_id), None)
    ctx.deps.updated_overall_status = updated.get("overall_status") if updated else None
    ctx.deps.task["result_summary"] = summary
    return {"ok": True, "patient_id": patient_id, "override_status": override_status}


async def run_audit_analysis_agent(
    *,
    task_id: str,
    message: str,
    patient_id: str | None = None,
    user_id: str = "clinician",
) -> AuditCopilotReply:
    task = await fetch_matching_task(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    deps = AuditCopilotDeps(
        task_id=task_id,
        task=task,
        user_id=user_id,
        patient_id=patient_id,
    )

    scope = f"@Patient_{patient_id}" if patient_id else "@Entire_Cohort"
    prompt = {
        "task_id": task_id,
        "trial_id": task.get("trial_id"),
        "focused_patient_id": patient_id,
        "scope_label": scope,
        "user_message": message,
        "dashboard_preview": build_dashboard(task),
    }

    conversation_id = _copilot_conversation_id(task_id, patient_id)
    message_history = await load_chat_history(conversation_id)
    result = await agent.run(
        json.dumps(prompt, default=str),
        deps=deps,
        message_history=message_history,
        usage_limits=UsageLimits(request_limit=12),
    )
    await save_chat_history(conversation_id, result.all_messages())
    reply = result.output

    if deps.override_applied:
        reply.override_applied = True
        reply.updated_patient_id = deps.updated_patient_id
        reply.updated_overall_status = deps.updated_overall_status
    if not reply.scope_label:
        reply.scope_label = scope
    return reply
