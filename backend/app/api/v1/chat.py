from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import AuditLog
from app.models.schemas import ChatRequest, ChatResponse
from app.services.mock_data import DEMO_PATIENTS, TRIAL_ID, TRIAL_NAME

router = APIRouter(prefix="/chat", tags=["chat"])


CHAT_RESPONSES = {
    "default": (
        "I'm HERA, your Healthcare Eligibility & Reasoning Agent. I can help you:\n\n"
        "• **Screen patients** against trial criteria (try: *match PT-000001 to TRIAL-HF-2026-001*)\n"
        "• **Explain eligibility verdicts** with full audit trail transparency\n"
        "• **Review extracted clinical features** from SOAP notes\n\n"
        f"Demo patients: {', '.join(DEMO_PATIENTS)}"
    ),
    "match": (
        f"I've initiated the 3-tier funnel pipeline for **{TRIAL_NAME}**.\n\n"
        "Pipeline stages:\n"
        "1. **Tier 1 (BM25)** — Lexical filter reduced 100k → 10k candidates\n"
        "2. **Tier 2 (Vector + Regex)** — Range guards narrowed to 1k\n"
        "3. **Tier 3 (HERA Agent)** — Structured eligibility evaluation\n\n"
        "Enter **PT-000001** in the center pane to view the full audit trail."
    ),
    "creatinine": (
        "For **PT-000001**, creatinine peaked at **2.1 mg/dL** on ICU Day 2 (Encounter 2), "
        "exceeding the trial inclusion threshold of <2.0 mg/dL. This triggered a **BORDERLINE** "
        "verdict requiring human review.\n\n"
        "At discharge (Encounter 3), creatinine improved to **1.8 mg/dL** — "
        "a clinician override may be warranted with repeat lab documentation."
    ),
    "lvef": (
        "**PT-000001** meets the LVEF inclusion criterion:\n"
        "• Encounter 1: LVEF **25%** (Tier 2 Regex, confidence 0.96)\n"
        "• Encounter 2: LVEF **28%**\n"
        "• Encounter 3: LVEF **30%**\n\n"
        "All values satisfy LVEF ≤35% requirement."
    ),
}


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    msg = body.message.lower()
    suggested: str | None = None

    if any(k in msg for k in ("match", "screen", "trial", "eligible")):
        reply = CHAT_RESPONSES["match"]
        suggested = "PT-000001"
    elif "creatinine" in msg or "renal" in msg or "kidney" in msg:
        reply = CHAT_RESPONSES["creatinine"]
        suggested = "PT-000001"
    elif "lvef" in msg or "ejection" in msg or "ef" in msg:
        reply = CHAT_RESPONSES["lvef"]
        suggested = "PT-000001"
    elif any(pid.lower() in msg for pid in DEMO_PATIENTS):
        for pid in DEMO_PATIENTS:
            if pid.lower() in msg:
                suggested = pid
                break
        reply = f"Loading patient **{suggested}**. View their SOAP notes and eligibility ledger in the center and right panes."
    else:
        reply = CHAT_RESPONSES["default"]

    log = AuditLog(
        patient_id=body.patient_id or suggested or "SYSTEM",
        encounter_id="CHAT",
        trial_id=body.trial_id or TRIAL_ID,
        original_llm_raw_response=body.message,
        pydantic_parsed_payload={"reply": reply},
    )
    db.add(log)

    return ChatResponse(reply=reply, suggested_patient_id=suggested or body.patient_id)
