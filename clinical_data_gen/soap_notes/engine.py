"""Convert structured patient trajectories into unstructured SOAP progress notes."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, OpenAI

from hera_io.datasets import batch_response_content, load_json_list, write_json_dataset
from hera_io.env import default_output_dir, load_openai_settings
from hera_io.patient_ids import load_canonical_notes
from structured_clinical_data.conditions import CLINICAL_CONDITION
from structured_clinical_data.engine import (
    TERMINAL_BATCH_STATUSES,
    download_batch_files,
    save_manifest,
    submit_batch,
    wait_for_batch,
)

load_dotenv()

OUTPUT_DIR = default_output_dir("SOAP_OUTPUT_DIR", Path(__file__).resolve().parent / "output")
CANONICAL_NOTES = "soap_progress_notes.json"
DEFAULT_MAX_ENQUEUED_TOKENS = int(os.getenv("BATCH_MAX_ENQUEUED_TOKENS", "1800000"))
RUN_STATE_FILE = "run_state.json"

SOAP_TRANSLATION_SYSTEM_PROMPT = """You are an advanced medical transcriptionist and clinical informatics agent. Your task is to transform a structured JSON object representing a specific patient encounter into an unstructured, professional clinical progress note written using the strict SOAP format.

### FORMAT COMPONENT RULES:

1. SUBJECTIVE (S):
   - Open with a standard professional clinical statement: "The patient is a [AGE]-year-old [SEX] presenting with..."
   - Synthesize a realistic history of present illness (HPI) based on the "diagnosis", "tags", and encounter type.
   - Describe patient symptoms, adherence/tolerance to their listed medications, and complaints in native clinical jargon. Do not use conversational patient text unless noting an exact quote.
   - Integrate historic context if "previous_timeline_history" contains data (e.g., "Status post procedure X on day Y...").

2. OBJECTIVE (O):
   - Document vitals completely and formally (e.g., "Vitals: BP 132/78 mmHg, HR 84 bpm, RR 18/min, T 37.1 C, SpO2 96% on room air").
   - Transcribe the labs panels into a standard laboratory report layout. Group by panel (e.g., "Renal Panel: Creatinine: 1.4 mg/dL, eGFR: 45...").
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
    return load_json_list(path, "patients")


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


def _chat_completion_kwargs(model: str, messages: list[dict]) -> dict:
    kwargs = {"model": model, "messages": messages}
    # GPT-5 models only accept the default temperature (1).
    if not model.startswith("gpt-5"):
        kwargs["temperature"] = 0.2
    return kwargs


def convert_structured_to_soap(
    patient_profile: dict,
    target_encounter_idx: int,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> str:
    """Convert one structured encounter into an unstructured SOAP note (sync API)."""
    openai = load_openai_settings(model=model)
    client = client or OpenAI(api_key=openai.api_key)

    response = client.chat.completions.create(
        **_chat_completion_kwargs(openai.model, soap_messages(patient_profile, target_encounter_idx))
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"Empty SOAP response for {patient_profile['patient_id']} encounter {target_encounter_idx}")
    return content


def canonical_notes_path(output_root: Path) -> Path:
    return output_root / CANONICAL_NOTES


def completed_soap_task_ids(notes: list[dict]) -> set[str]:
    ids: set[str] = set()
    for note in notes:
        patient_id = note.get("patient_id")
        if not patient_id or not (note.get("soap_note") or "").strip():
            continue
        ids.add(f"{patient_id}-enc-{int(note['encounter_index'])}")
    return ids


def filter_pending_soap_tasks(tasks: list[SoapTask], completed_ids: set[str]) -> list[SoapTask]:
    if not completed_ids:
        return tasks
    return [task for task in tasks if task.custom_id not in completed_ids]


def merge_notes_into_canonical(output_root: Path, notes: list[dict]) -> Path:
    canonical = canonical_notes_path(output_root)
    existing = load_canonical_notes(canonical)
    by_key = {
        (note["patient_id"], int(note["encounter_index"])): note
        for note in existing
        if note.get("patient_id") is not None
    }
    for note in notes:
        key = (note["patient_id"], int(note["encounter_index"]))
        by_key[key] = note
    merged = sorted(by_key.values(), key=lambda row: (row["patient_id"], int(row["encounter_index"])))
    write_dataset(merged, canonical)
    return canonical


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


def build_batch_line(task: SoapTask, patients_by_id: dict[str, dict], model: str) -> dict:
    patient = patients_by_id[task.patient_id]
    return {
        "custom_id": task.custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": _chat_completion_kwargs(model, soap_messages(patient, task.encounter_index)),
    }


def estimate_batch_line_tokens(line: dict) -> int:
    return max(1, len(json.dumps(line, ensure_ascii=False)) // 4)


def chunk_tasks(
    tasks: list[SoapTask],
    patients_by_id: dict[str, dict],
    model: str,
    max_enqueued_tokens: int,
) -> list[list[SoapTask]]:
    chunks: list[list[SoapTask]] = []
    current: list[SoapTask] = []
    current_tokens = 0

    for task in tasks:
        tokens = estimate_batch_line_tokens(build_batch_line(task, patients_by_id, model))
        if current and current_tokens + tokens > max_enqueued_tokens:
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append(task)
        current_tokens += tokens

    if current:
        chunks.append(current)
    return chunks


def _estimate_chunk_tokens(chunk: list[SoapTask], patients_by_id: dict[str, dict], model: str) -> int:
    return sum(
        estimate_batch_line_tokens(build_batch_line(task, patients_by_id, model))
        for task in chunk
    )


def init_run_state(
    *,
    input_path: Path,
    model: str,
    max_enqueued_tokens: int,
    tasks: list[SoapTask],
    chunks: list[list[SoapTask]],
) -> dict:
    task_offset = 0
    chunk_states = []
    for index, chunk in enumerate(chunks):
        chunk_states.append(
            {
                "index": index,
                "status": "pending",
                "task_start": task_offset,
                "task_count": len(chunk),
                "estimated_tokens": 0,
                "input_jsonl": f"batches/chunk_{index:03d}.jsonl",
                "batch_id": None,
                "batch_status": None,
                "notes_path": None,
                "failures_path": None,
            }
        )
        task_offset += len(chunk)

    return {
        "version": 1,
        "input_path": str(input_path.resolve()),
        "model": model,
        "max_enqueued_tokens": max_enqueued_tokens,
        "total_tasks": len(tasks),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunks": chunk_states,
    }


def build_run_state(
    *,
    input_path: Path,
    model: str,
    max_enqueued_tokens: int,
    tasks: list[SoapTask],
    patients_by_id: dict[str, dict],
) -> dict:
    chunks = chunk_tasks(tasks, patients_by_id, model, max_enqueued_tokens)
    state = init_run_state(
        input_path=input_path,
        model=model,
        max_enqueued_tokens=max_enqueued_tokens,
        tasks=tasks,
        chunks=chunks,
    )
    for index, chunk in enumerate(chunks):
        state["chunks"][index]["estimated_tokens"] = _estimate_chunk_tokens(
            chunk, patients_by_id, model
        )
    return state


def save_run_state(run_dir: Path, state: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / RUN_STATE_FILE).write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_run_state(run_dir: Path) -> dict:
    path = run_dir / RUN_STATE_FILE
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_resumable_run(output_root: Path, input_path: Path) -> Path | None:
    resolved_input = input_path.resolve()
    candidates: list[tuple[str, Path]] = []

    for state_path in output_root.glob(f"*/{RUN_STATE_FILE}"):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if Path(state.get("input_path", "")).resolve() != resolved_input:
            continue
        chunks = state.get("chunks") or []
        if any(chunk.get("status") != "completed" for chunk in chunks):
            candidates.append((state.get("created_at", ""), state_path.parent))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def chunk_tasks_for_state(tasks: list[SoapTask], state: dict) -> list[list[SoapTask]]:
    grouped: list[list[SoapTask]] = []
    for chunk in state["chunks"]:
        start = chunk["task_start"]
        count = chunk["task_count"]
        grouped.append(tasks[start : start + count])
    return grouped


def write_batch_input(tasks: list[SoapTask], patients_by_id: dict[str, dict], model: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(build_batch_line(task, patients_by_id, model), ensure_ascii=False) + "\n")


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


def parse_batch_results(output_path: Path, tasks_by_id: dict[str, SoapTask]) -> tuple[list[dict], list[dict]]:
    notes, failures = [], []

    with output_path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            if not raw.strip():
                continue

            result = json.loads(raw)
            custom_id = result.get("custom_id")
            task = tasks_by_id.get(custom_id)
            content = batch_response_content(result)

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
    write_json_dataset(notes, path, wrapper_key="notes")


def refresh_chunk_batch_status(client: OpenAI, chunk: dict) -> None:
    batch_id = chunk.get("batch_id")
    if not batch_id:
        return

    batch = client.batches.retrieve(batch_id)
    chunk["batch_status"] = batch.status
    if batch.status in {"validating", "in_progress", "finalizing"}:
        chunk["status"] = "in_progress"
    elif batch.status == "completed":
        if chunk.get("status") != "completed":
            chunk["status"] = "submitted"
    elif batch.status in {"failed", "expired", "cancelled"}:
        chunk["status"] = "failed"


def collect_chunk_results(
    client: OpenAI,
    *,
    run_dir: Path,
    chunk: dict,
    chunk_tasks: list[SoapTask],
    tasks_by_id: dict[str, SoapTask],
    poll_interval: int,
    wait: bool,
) -> str:
    batch_id = chunk.get("batch_id")
    if not batch_id:
        return "missing_batch"

    try:
        batch = client.batches.retrieve(batch_id)
        if batch.status not in TERMINAL_BATCH_STATUSES:
            if not wait:
                chunk["status"] = "in_progress"
                chunk["batch_status"] = batch.status
                return "in_progress"
            print(f"Waiting for chunk {chunk['index']} batch {batch_id}...")
            batch = wait_for_batch(client, batch_id, poll_interval)

        chunk["batch_status"] = batch.status
        batches_dir = run_dir / "batches"
        manifest_path = batches_dir / f"chunk_{chunk['index']:03d}_{batch_id}_manifest.json"
        save_manifest(
            batch,
            manifest_path,
            input_jsonl=run_dir / chunk["input_jsonl"],
            task_count=chunk["task_count"],
        )

        if batch.status != "completed":
            chunk["status"] = "failed"
            return "failed"

        output_path, error_path = download_batch_files(client, batch, batches_dir)
    except APIConnectionError as exc:
        chunk["status"] = "submitted"
        print(f"Connection error on chunk {chunk['index']}: {exc}", flush=True)
        return "connection_error"

    if not output_path:
        chunk["status"] = "failed"
        if error_path:
            print(f"Chunk {chunk['index']} completed with no output — see {error_path}", flush=True)
        return "failed"

    notes, failures = parse_batch_results(output_path, tasks_by_id)
    datasets_dir = run_dir / "datasets"
    notes_path = datasets_dir / f"chunk_{chunk['index']:03d}_notes.json"
    write_dataset(notes, notes_path)
    chunk["notes_path"] = str(notes_path.relative_to(run_dir)).replace("\\", "/")

    if failures:
        failures_path = datasets_dir / f"chunk_{chunk['index']:03d}_failures.json"
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        failures_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
        chunk["failures_path"] = str(failures_path.relative_to(run_dir)).replace("\\", "/")

    chunk["status"] = "completed"
    print(
        f"Chunk {chunk['index']} complete: {len(notes)} notes"
        + (f", {len(failures)} failures" if failures else "")
    )
    if error_path:
        print(f"OpenAI error file: {error_path}")
    return "completed"


def submit_chunk(
    client: OpenAI,
    *,
    run_dir: Path,
    chunk: dict,
    chunk_task_list: list[SoapTask],
    patients_by_id: dict[str, dict],
    model: str,
) -> None:
    input_path = run_dir / chunk["input_jsonl"]
    write_batch_input(chunk_task_list, patients_by_id, model, input_path)
    description = f"HERA SOAP notes chunk {chunk['index']} ({len(chunk_task_list)} encounters)"
    batch = submit_batch(client, input_path, description)
    chunk["batch_id"] = batch.id
    chunk["batch_status"] = batch.status
    chunk["status"] = "submitted"
    manifest_path = run_dir / "batches" / f"chunk_{chunk['index']:03d}_{batch.id}_manifest.json"
    save_manifest(batch, manifest_path, input_jsonl=input_path, task_count=len(chunk_task_list))
    print(
        f"Submitted chunk {chunk['index']}/{chunk.get('chunk_total', '?')}: "
        f"{batch.id} ({len(chunk_task_list)} tasks, ~{chunk['estimated_tokens']:,} tokens)"
    )


def merge_completed_notes(run_dir: Path, state: dict) -> tuple[list[dict], list[dict]]:
    notes: list[dict] = []
    failures: list[dict] = []
    for chunk in state["chunks"]:
        notes_path = chunk.get("notes_path")
        if notes_path and chunk.get("status") == "completed":
            payload = json.loads((run_dir / notes_path).read_text(encoding="utf-8"))
            notes.extend(payload.get("notes", []))
        failures_path = chunk.get("failures_path")
        if failures_path:
            failures.extend(json.loads((run_dir / failures_path).read_text(encoding="utf-8")))
    return notes, failures


def all_chunks_completed(state: dict) -> bool:
    return all(chunk.get("status") == "completed" for chunk in state["chunks"])


def process_run(
    client: OpenAI,
    *,
    run_dir: Path,
    state: dict,
    tasks: list[SoapTask],
    patients_by_id: dict[str, dict],
    model: str,
    poll_interval: int,
    submit: bool,
    wait: bool,
) -> int:
    grouped = chunk_tasks_for_state(tasks, state)
    tasks_by_id = {task.custom_id: task for task in tasks}
    chunk_total = len(state["chunks"])

    for chunk, chunk_task_list in zip(state["chunks"], grouped):
        chunk["chunk_total"] = chunk_total
        refresh_chunk_batch_status(client, chunk)

        if chunk["status"] == "completed":
            continue

        if chunk["status"] in {"submitted", "in_progress", "failed"} and chunk.get("batch_id"):
            if chunk["status"] == "failed":
                print(f"Chunk {chunk['index']} batch failed ({chunk.get('batch_status')}); retrying.")
                chunk["status"] = "pending"
                chunk["batch_id"] = None
                chunk["batch_status"] = None
            else:
                result = collect_chunk_results(
                    client,
                    run_dir=run_dir,
                    chunk=chunk,
                    chunk_tasks=chunk_task_list,
                    tasks_by_id=tasks_by_id,
                    poll_interval=poll_interval,
                    wait=wait,
                )
                save_run_state(run_dir, state)
                if result == "in_progress":
                    print(
                        f"Chunk {chunk['index']} still running. Resume with:\n"
                        f"  python clinical_data_gen/soap_notes/generate.py --input \"{state['input_path']}\" "
                        f"--run-dir \"{run_dir}\" --wait"
                    )
                    return 0
                if result == "connection_error":
                    print(
                        f"Chunk {chunk['index']} not fully downloaded. Resume with:\n"
                        f"  python clinical_data_gen/soap_notes/generate.py --input \"{state['input_path']}\" "
                        f"--run-dir \"{run_dir}\" --submit --wait"
                    )
                    return 1
                if result == "failed":
                    chunk["status"] = "pending"
                    chunk["batch_id"] = None
                    chunk["batch_status"] = None
                    save_run_state(run_dir, state)
                    if not submit:
                        return 1
                elif result == "completed":
                    save_run_state(run_dir, state)
                    continue

        if not submit:
            continue

        if chunk["status"] != "pending":
            continue

        try:
            submit_chunk(
                client,
                run_dir=run_dir,
                chunk=chunk,
                chunk_task_list=chunk_task_list,
                patients_by_id=patients_by_id,
                model=model,
            )
        except Exception as exc:
            save_run_state(run_dir, state)
            print(f"Failed to submit chunk {chunk['index']}: {exc}", flush=True)
            print(
                f"Resume after in-flight batches finish with:\n"
                f"  python clinical_data_gen/soap_notes/generate.py --input \"{state['input_path']}\" "
                f"--run-dir \"{run_dir}\" --submit --wait"
            )
            return 1

        save_run_state(run_dir, state)
        if not wait:
            print(
                f"Resume with:\n"
                f"  python clinical_data_gen/soap_notes/generate.py --input \"{state['input_path']}\" "
                f"--run-dir \"{run_dir}\" --submit --wait"
            )
            return 0

        result = collect_chunk_results(
            client,
            run_dir=run_dir,
            chunk=chunk,
            chunk_tasks=chunk_task_list,
            tasks_by_id=tasks_by_id,
            poll_interval=poll_interval,
            wait=True,
        )
        save_run_state(run_dir, state)
        if result == "connection_error":
            print(
                f"Chunk {chunk['index']} not fully downloaded. Resume with:\n"
                f"  python clinical_data_gen/soap_notes/generate.py --input \"{state['input_path']}\" "
                f"--run-dir \"{run_dir}\" --submit --wait"
            )
            return 1
        if result != "completed":
            return 1

    if all_chunks_completed(state):
        notes, failures = merge_completed_notes(run_dir, state)
        dataset_path = run_dir / "datasets" / "soap_progress_notes.json"
        write_dataset(notes, dataset_path)
        canonical = merge_notes_into_canonical(OUTPUT_DIR, notes)
        print(f"Merged {len(notes)} SOAP notes into {dataset_path}")
        print(f"Updated canonical notes: {canonical}")
        if failures:
            failure_path = run_dir / "datasets" / "parse_failures.json"
            failure_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
            print(f"Merged {len(failures)} parse failures into {failure_path}")
        return 0 if not failures else 2

    pending = sum(1 for chunk in state["chunks"] if chunk["status"] != "completed")
    print(f"{pending} chunk(s) remaining. Re-run with --submit --wait to continue.")
    return 0


def settings(*, model: str | None = None, poll_interval: int = 30, max_enqueued_tokens: int | None = None):
    openai = load_openai_settings(model=model)
    return {
        "api_key": openai.api_key,
        "model": openai.model,
        "poll_interval": poll_interval,
        "output_dir": OUTPUT_DIR,
        "max_enqueued_tokens": max_enqueued_tokens or DEFAULT_MAX_ENQUEUED_TOKENS,
    }
