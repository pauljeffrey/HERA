"""One-shot local pipeline smoke test (funnel + optional Tier 3)."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.models.search import NumericalConstraint, NumericalOperator, SearchCriteria
from app.services.funnel.funnel_orchestrator import run_fts_vector_filter
from app.services.funnel.match_pipeline import run_matching_pipeline


def build_criteria() -> SearchCriteria:
    return SearchCriteria(
        response=(
            "Heart failure trial: LVEF ≤35%, age 18–80, serum creatinine >1.5 mg/dL; "
            "exclude severe kidney disease."
        ),
        lexical_keywords=[
            "heart failure",
            "HFrEF",
            "reduced ejection fraction",
            "LVEF",
            "ejection fraction",
            "creatinine",
            "kidney",
            "renal",
        ],
        semantic_query=(
            "Adult heart failure patient with reduced left ventricular ejection fraction "
            "at or below 35 percent and elevated serum creatinine above 1.5 mg/dL"
        ),
        semantic_query_variants=[
            "HFrEF with LVEF under 35% and renal impairment creatinine elevated",
            "systolic heart failure low EF 35 percent increased creatinine",
        ],
        numerical_constraints=[
            NumericalConstraint(
                parameter_name="LVEF",
                triggers=["lvef", "ejection fraction", "ef"],
                operator=NumericalOperator.LTE,
                target_value=35.0,
                unit_regex=r"%|percent",
            ),
            NumericalConstraint(
                parameter_name="Serum Creatinine",
                triggers=["creatinine", "scr"],
                operator=NumericalOperator.GT,
                target_value=1.5,
                unit_regex=r"mg/dL|mg/dl",
            ),
        ],
        n_candidates=5,
    )


async def main() -> None:
    payload = build_criteria()
    print("=== Funnel (FTS + VS + merge + rank + cap) ===")
    timelines, metrics = await run_fts_vector_filter(payload)
    print(
        json.dumps(
            {
                "search_space_raw": metrics.search_space_raw,
                "search_space_after_fts": metrics.search_space_after_fts,
                "search_space_after_vs": metrics.search_space_after_vs,
                "patients_to_tier3": len(timelines),
                "patient_ids": [t.patient_id for t in timelines],
            },
            indent=2,
        )
    )

    if "--funnel-only" in sys.argv:
        return

    task_id = str(uuid.uuid4())
    trial_id = "TRIAL-SMOKE-TEST"
    print(f"\n=== Full pipeline task_id={task_id} ===")
    await run_matching_pipeline(task_id, "smoke-test", trial_id, payload)
    from app.services.audit.task_storage import fetch_matching_task

    task = await fetch_matching_task(task_id)
    print(json.dumps(task, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
