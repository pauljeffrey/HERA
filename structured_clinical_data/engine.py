"""Synthetic patient trajectory generation via OpenAI Batch API."""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from structured_clinical_data.conditions import CLINICAL_CONDITION
from structured_clinical_data.schemas import PatientTrajectory

load_dotenv()

OUTPUT_DIR = Path(os.getenv("DATASET_OUTPUT_DIR", Path(__file__).resolve().parent / "output"))
TERMINAL_BATCH_STATUSES = {"completed", "failed", "expired", "cancelled"}

SPECIALTY_RATIOS = {
    "cardiovascular_care": 0.50,
    "cancer_care": 0.35,
    "icu_critical_care": 0.15,
}

SPECIALTY_LABELS = {
    "cardiovascular_care": "Cardiovascular",
    "cancer_care": "Oncology",
    "icu_critical_care": "ICU/Critical Care",
}

SYSTEM_PROMPT = """You are an expert clinical informatics engine and synthetic medical data architect. Your task is to generate high-fidelity, clinically accurate, longitudinal synthetic patient data records.

### CRITICAL CORE INSTRUCTION:
Each patient profile must represent a realistic clinical trajectory consisting of a LIST of chronologically ordered encounters (minimum 2, maximum 4). This timeline must simulate their clinical evolution over time, tracking:
1. First Presentation / Baseline Admission (e.g., initial workup, diagnostic criteria met).
2. Subsequent Follow-ups / Daily Progress Notes (e.g., medication adjustments, response to treatments, worsening or improving vitals/labs).
3. Final Evaluation / Discharge State.

### CLINICAL REALISM RULES:
- Physiological Coherence: Labs, vitals, medications, and clinical notes must match the patient's age, sex, and diagnosis.
- Chronological Logic: For example, if a patient is prescribed an ACE-inhibitor in Encounter 1, Encounter 2 should reflect a potential drop in blood pressure or an altered potassium/creatinine level. If a procedure (like a PCI) is performed in Encounter 2, Encounter 3 must list it under "Procedures: Prior PCI".
- Diversity: Do not repeat patient archetypes. Generate a broad spectrum of presentations within the designated medical specialty.

### EXPECTED SPECIALTY DIRECTIVE:
You will receive a target [SPECIALTY] and [CLINICAL SCENARIO BRIEF] for each batch. Tailor the entire trajectory to reflect that domain accurately.

### OUTPUT FORMAT:
You must output exclusively valid JSON conforming strictly to the JSON schema provided. Do not include markdown wrappers (like ```json), conversational text, or explanations."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    target_count: int
    output_dir: Path
    poll_interval: int = 30

    @classmethod
    def load(cls, *, count: int | None = None, output_dir: Path | None = None, model: str | None = None, poll_interval: int = 30):
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("MODEL_API_KEY")
        if not api_key:
            raise ValueError("Set OPENAI_API_KEY or MODEL_API_KEY in the environment.")
        return cls(
            api_key=api_key,
            model=model or os.getenv("MODEL_NAME", "gpt-4o-mini"),
            target_count=count or int(os.getenv("DATASET_TARGET_COUNT", "5000")),
            output_dir=output_dir or OUTPUT_DIR,
            poll_interval=poll_interval,
        )


@dataclass(frozen=True)
class Task:
    index: int
    specialty_key: str
    specialty_label: str
    scenario_brief: str

    @property
    def custom_id(self) -> str:
        return f"task-{self.index:06d}"


def plan_tasks(total: int, seed: int = 42) -> list[Task]:
    """Build a shuffled task list that hits the target specialty ratios exactly."""
    raw = {key: total * ratio for key, ratio in SPECIALTY_RATIOS.items()}
    counts = {key: int(value) for key, value in raw.items()}
    for key, _ in sorted(raw.items(), key=lambda item: item[1] - counts[item[0]], reverse=True):
        if sum(counts.values()) >= total:
            break
        counts[key] += 1

    rng = random.Random(seed)
    tasks: list[Task] = []
    index = 0
    for specialty_key, count in counts.items():
        for _ in range(count):
            index += 1
            tasks.append(
                Task(
                    index=index,
                    specialty_key=specialty_key,
                    specialty_label=SPECIALTY_LABELS[specialty_key],
                    scenario_brief=rng.choice(CLINICAL_CONDITION[specialty_key]),
                )
            )
    rng.shuffle(tasks)
    return tasks


def specialty_counts(tasks: list[Task]) -> dict[str, int]:
    counts = {key: 0 for key in SPECIALTY_RATIOS}
    for task in tasks:
        counts[task.specialty_key] += 1
    return counts


def _user_prompt(task: Task) -> str:
    return (
        f"SPECIALTY: {task.specialty_label}\n"
        f"CLINICAL SCENARIO BRIEF: {task.scenario_brief}\n\n"
        f"Generate exactly 1 patient trajectory. Assign patient_id as 'PT-{task.index:06d}'.\n"
        "Ensure the timeline has 2-4 chronologically coherent encounters with "
        "physiologically consistent labs, vitals, and medications."
        f"seed: {random.seed()}"
    )


def _strict_schema() -> dict:
    schema = PatientTrajectory.model_json_schema()

    def walk(node: dict) -> None:
        if node.get("type") == "object" and "additionalProperties" not in node:
            node["additionalProperties"] = False
        for key in ("properties", "$defs"):
            for child in node.get(key, {}).values():
                walk(child)
        if "items" in node:
            walk(node["items"])

    walk(schema)
    return {
        "type": "json_schema",
        "json_schema": {"name": "patient_trajectory", "strict": True, "schema": schema},
    }


def write_batch_input(tasks: list[Task], model: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    response_format = _strict_schema()

    with path.open("w", encoding="utf-8") as f:
        for task in tasks:
            line = {
                "custom_id": task.custom_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _user_prompt(task)},
                    ],
                    "response_format": response_format,
                    "temperature": 0.9,
                },
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def submit_batch(client: OpenAI, input_path: Path, description: str):
    with input_path.open("rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")
    return client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": description},
    )


def wait_for_batch(client: OpenAI, batch_id: str, poll_interval: int):
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status in TERMINAL_BATCH_STATUSES:
            return batch
        time.sleep(poll_interval)


def save_manifest(batch, path: Path, *, input_jsonl: Path, task_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "status": batch.status,
                "input_file_id": batch.input_file_id,
                "output_file_id": batch.output_file_id,
                "error_file_id": batch.error_file_id,
                "input_jsonl": str(input_jsonl),
                "task_count": task_count,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def download_batch_files(client: OpenAI, batch, output_dir: Path) -> tuple[Path | None, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = error_path = None

    if batch.output_file_id:
        output_path = output_dir / f"{batch.id}_output.jsonl"
        output_path.write_bytes(client.files.content(batch.output_file_id).read())
    if batch.error_file_id:
        error_path = output_dir / f"{batch.id}_errors.jsonl"
        error_path.write_bytes(client.files.content(batch.error_file_id).read())

    return output_path, error_path


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


def parse_results(output_path: Path, tasks_by_id: dict[str, Task]) -> tuple[list[dict], list[dict]]:
    records, failures = [], []

    with output_path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            if not raw.strip():
                continue

            result = json.loads(raw)
            custom_id = result.get("custom_id")
            task = tasks_by_id.get(custom_id)
            content = _response_content(result)

            if not content:
                failures.append(
                    {
                        "custom_id": custom_id,
                        "line": line_no,
                        "error": result.get("error") or "Missing or invalid response body",
                        "specialty": task.specialty_label if task else None,
                    }
                )
                continue

            try:
                record = PatientTrajectory.model_validate_json(content).model_dump(mode="json")
                if task:
                    record["_meta"] = {
                        "custom_id": custom_id,
                        "specialty_key": task.specialty_key,
                        "specialty_label": task.specialty_label,
                        "scenario_brief": task.scenario_brief,
                    }
                records.append(record)
            except (ValidationError, json.JSONDecodeError) as exc:
                failures.append(
                    {
                        "custom_id": custom_id,
                        "line": line_no,
                        "error": str(exc),
                        "specialty": task.specialty_label if task else None,
                    }
                )

    return records, failures


def write_dataset(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"count": len(records), "patients": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_manifest(output_dir: Path, batch_id: str) -> Path | None:
    for path in output_dir.rglob("*_manifest.json"):
        if json.loads(path.read_text(encoding="utf-8")).get("batch_id") == batch_id:
            return path
    return None


def load_tasks(run_dir: Path) -> list[Task]:
    tasks_path = run_dir / "tasks.json"
    if not tasks_path.exists():
        raise FileNotFoundError(f"Missing {tasks_path}")
    return [Task(**item) for item in json.loads(tasks_path.read_text(encoding="utf-8"))]


def save_tasks(tasks: list[Task], run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasks.json").write_text(
        json.dumps([asdict(task) for task in tasks], indent=2),
        encoding="utf-8",
    )
