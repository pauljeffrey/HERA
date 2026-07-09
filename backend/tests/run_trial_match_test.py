"""Run matching pipeline end-to-end with agent-style criteria."""

from __future__ import annotations

import asyncio
import json
import uuid

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.models.search import NumericalConstraint, NumericalOperator, SearchCriteria
from app.services.funnel.match_pipeline import run_matching_pipeline


async def main() -> None:
    task_id = str(uuid.uuid4())
    trial_id = "TRIAL-TEST-HF"
    payload = SearchCriteria(
        response=(
            "Heart failure trial: age 18-80, LVEF <= 35%, serum creatinine < 2.0 mg/dL, "
            "HFrEF on GDMT."
        ),
        lexical_keywords=[
            "HFrEF",
            "LVEF",
            "GDMT",
            "Guideline-directed medical therapy",
            "Serum Creatinine",
            "Heart Failure",
        ],
        semantic_query=(
            "Patients with Heart Failure with reduced Ejection Fraction (HFrEF) "
            "who are currently managed on Guideline-Directed Medical Therapy (GDMT)."
        ),
        semantic_query_variants=[
            "chronic systolic heart failure depressed left ventricular ejection fraction",
            "HFrEF cardiomyopathy on beta blocker ACE inhibitor MRA therapy",
            "reduced EF heart failure patient on standard GDMT regimen",
        ],
        numerical_constraints=[
            NumericalConstraint(
                parameter_name="LVEF",
                triggers=["LVEF", "Left Ventricular Ejection Fraction", "EF", "ejection fraction"],
                operator=NumericalOperator.LTE,
                target_value=35.0,
                unit_regex=r"%|percent",
            ),
            NumericalConstraint(
                parameter_name="Serum Creatinine",
                triggers=["creatinine", "Cr", "serum creatinine"],
                operator=NumericalOperator.LT,
                target_value=2.0,
                unit_regex=r"mg/dL|mg/dl",
            ),
        ],
        n_candidates=5,
    )

    await run_matching_pipeline(task_id, "clinician", trial_id, payload)

    from app.services.audit.task_storage import fetch_matching_task

    task = await fetch_matching_task(task_id)
    print(json.dumps(task, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
