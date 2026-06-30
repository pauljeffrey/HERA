"""Convert structured patient trajectories into unstructured SOAP progress notes."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from structured_clinical_data.conditions import CLINICAL_CONDITION
from structured_clinical_data.engine import (
    download_batch_files,
    find_manifest,
    save_manifest,
    submit_batch,
    wait_for_batch,
)

load_dotenv()

OUTPUT_DIR = Path(os.getenv("SOAP_OUTPUT_DIR", Path(__file__).resolve().parent / "output"))

SOAP_TRANSLATION_SYSTEM_PROMPT = """You are an advanced medical transcriptionist and clinical informatics agent. Your task is to transform a structured JSON object representing a specific patient encounter into an unstructured, professional clinical progress note written using the strict SOAP format.

### FORMAT COMPONENT RULES:

1. SUBJECTIVE (S):
   - Open with a standard professional clinical statement: "The patient is a [AGE]-year-old [SEX] presenting with..."
   - Synthesize a realistic history of present illness (HPI) based on the "diagnosis", "tags", and encounter type.
   - Describe patient symptoms, adherence/tolerance to their listed medications, and complaints in native clinical jargon. Do not use conversational patient text unless noting an exact quote.
   - Integrate historic context if "previous_timeline_history" contains data (e.g., "Status post procedure X on day Y...").

2. OBJECTIVE (O):
   - Document vitals completely and formally (e.g., "Vitals: BP 132/78 mmHg, HR 84 bpm, RR 18/min, T 37.1 C, SpO2 96% on room air").
   - Transcribe the labs dictionary into a standard laboratory report layout. Group by panels (e.g., "Renal Panel: Creatinine: 1.4 mg/dL, eGFR: 45...").
   - Summarize physical examination observations that naturally align with the diagnoses (e.g., write "bilateral 2+ pitting edema" for decompensated heart failure).

3. ASSESSMENT (A):
   - Formulate a formal medical assessment block listing the active diagnoses.
   - State clinical reasoning clearly. Incorporate the eligibility_context subtly to show the clinical reasoning that makes this patient a candidate or non-candidate for trials (without explicitly stating "this is for a trial").

4. PLAN (P):
   - Outline a clear, ordered therapeutic action plan.
   - Detail the continued, discontinued, or titrated dosing of active medications.
   - Note any ordered procedures, follow-up timelines, or specific clinical trial screening directives.

### CRITICAL TRANSCRIPTION DIRECTIVES:
- NO RAW JSON STYLE: Do not print any markdown keys, raw dictionaries, or curly braces. The note must look completely organic, like it was written directly into an EHR text window by a practicing attending physician.
- DO NOT hallucinate clinical data points (such as radically different labs or medication names) that are completely absent from the source JSON payload."""


@dataclass(frozen=True)
class SoapTask:
    patient_id: str
    encounter_index: int
    encounter_id: str
    encounter_type: str
    specialty_key: str | None
    specialty_label: str | None
    scenario_brief: str | None

    @property
    def custom_id(self) -> str:
        return f"{self.patient_id}-enc-{self.encounter_index}"


def load_patients(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "patients" in payload:
        return payload["patients"]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unrecognized patient dataset format in {path}")


def _specialty_conditions(specialty_key: str | None) -> list[str]:
    if not specialty_key:
        return []
    return CLINICAL_CONDITION.get(specialty_key, [])


def build_soap_payload(patient_profile: dict, target_encounter_idx: int) -> dict:
    timeline = patient_profile["timeline"]
    current_encounter = timeline[target_encounter_idx]
    meta = patient_profile.get("_meta") or {}
    specialty_key = meta.get("specialty_key")

    return {
        "patient_metadata": {
            "name": patient_profile["name"],
            "age": patient_profile["age"],
            "sex": patient_profile["sex"],
            "patient_id": patient_profile["patient_id"],
            "eligibility_context": patient_profile["inclusion_exclusion_criteria"],
        },
        "clinical_condition_context": {
            "specialty_key": specialty_key,
            "specialty_label": meta.get("specialty_label"),
            "assigned_scenario_brief": meta.get("scenario_brief"),
            "related_condition_matrix": _specialty_conditions(specialty_key)[:12],
        },
        "current_encounter_data": current_encounter,
        "previous_timeline_history": timeline[:target_encounter_idx],
    }


def soap_messages(patient_profile: dict, target_encounter_idx: int) -> list[dict]:
    payload = build_soap_payload(patient_profile, target_encounter_idx)
    return [
        {"role": "system", "content": SOAP_TRANSLATION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
    ]


def convert_structured_to_soap(
    patient_profile: dict,
    target_encounter_idx: int,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> str:
    """Convert one structured encounter into an unstructured SOAP note (sync API)."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("MODEL_API_KEY")
    if not api_key:
        raise ValueError("Set OPENAI_API_KEY or MODEL_API_KEY in the environment.")

    client = client or OpenAI(api_key=api_key)
    model = model or os.getenv("MODEL_NAME", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        messages=soap_messages(patient_profile, target_encounter_idx),
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"Empty SOAP response for {patient_profile['patient_id']} encounter {target_encounter_idx}")
    return content


def plan_soap_tasks(patients: list[dict]) -> list[SoapTask]:
    tasks: list[SoapTask] = []
    for patient in patients:
        meta = patient.get("_meta") or {}
        for idx, encounter in enumerate(patient["timeline"]):
            tasks.append(
                SoapTask(
                    patient_id=patient["patient_id"],
                    encounter_index=idx,
                    encounter_id=encounter["id"],
                    encounter_type=encounter["type"],
                    specialty_key=meta.get("specialty_key"),
                    specialty_label=meta.get("specialty_label"),
                    scenario_brief=meta.get("scenario_brief"),
                )
            )
    return tasks


def write_batch_input(tasks: list[SoapTask], patients_by_id: dict[str, dict], model: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for task in tasks:
            patient = patients_by_id[task.patient_id]
            line = {
                "custom_id": task.custom_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": soap_messages(patient, task.encounter_index),
                    "temperature": 0.2,
                },
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def save_tasks(tasks: list[SoapTask], run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "soap_tasks.json").write_text(
        json.dumps([asdict(task) for task in tasks], indent=2),
        encoding="utf-8",
    )


def load_tasks(run_dir: Path) -> list[SoapTask]:
    path = run_dir / "soap_tasks.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return [SoapTask(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _response_content(line: dict) -> str | None:
    if line.get("error"):
        return None
    response = line.get("response") or {}
    if response.get("status_code") != 200:
        return None
    choices = (response.get("body") or {}).get("choices") or []
    if not choices:
        return None
    return (choices[0].get("message") or {}).get("content")


def parse_batch_results(output_path: Path, tasks_by_id: dict[str, SoapTask]) -> tuple[list[dict], list[dict]]:
    notes, failures = [], []

    with output_path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            if not raw.strip():
                continue

            result = json.loads(raw)
            custom_id = result.get("custom_id")
            task = tasks_by_id.get(custom_id)
            content = _response_content(result)

            if not content or not task:
                failures.append(
                    {
                        "custom_id": custom_id,
                        "line": line_no,
                        "error": result.get("error") or "Missing or invalid response body",
                    }
                )
                continue

            notes.append(
                {
                    "patient_id": task.patient_id,
                    "encounter_id": task.encounter_id,
                    "encounter_index": task.encounter_index,
                    "encounter_type": task.encounter_type,
                    "specialty_key": task.specialty_key,
                    "specialty_label": task.specialty_label,
                    "scenario_brief": task.scenario_brief,
                    "soap_note": content.strip(),
                }
            )

    return notes, failures


def write_dataset(notes: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"count": len(notes), "notes": notes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def settings(*, model: str | None = None, poll_interval: int = 30):
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("MODEL_API_KEY")
    if not api_key:
        raise ValueError("Set OPENAI_API_KEY or MODEL_API_KEY in the environment.")
    return {
        "api_key": api_key,
        "model": model or os.getenv("MODEL_NAME", "gpt-4o-mini"),
        "poll_interval": poll_interval,
        "output_dir": OUTPUT_DIR,
    }
