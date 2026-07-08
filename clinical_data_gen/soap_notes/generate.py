"""CLI to batch-convert structured trajectories into SOAP progress notes."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openai import OpenAI

from soap_notes.engine import (
    build_run_state,
    chunk_tasks_for_state,
    find_resumable_run,
    load_patients,
    load_run_state,
    load_tasks,
    plan_soap_tasks,
    process_run,
    save_run_state,
    save_tasks,
    settings,
    write_batch_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert structured profiles to SOAP notes via OpenAI Batch.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to patient_trajectories.json from structured_clinical_data.",
    )
    parser.add_argument("--output-dir", type=Path, help="Output root directory.")
    parser.add_argument("--model", help="OpenAI model (default: MODEL_NAME from .env).")
    parser.add_argument(
        "--max-enqueued-tokens",
        type=int,
        help="Max input tokens per batch chunk (default: BATCH_MAX_ENQUEUED_TOKENS or 1,800,000).",
    )
    parser.add_argument("--run-dir", type=Path, help="Resume a specific chunked run directory.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the latest incomplete run for this input file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build chunk batch inputs only.")
    parser.add_argument("--submit", action="store_true", help="Upload and create batch job(s).")
    parser.add_argument("--wait", action="store_true", help="Poll until each submitted chunk finishes.")
    parser.add_argument("--poll-interval", type=int, default=30)
    args = parser.parse_args()

    cfg = settings(
        model=args.model,
        poll_interval=args.poll_interval,
        max_enqueued_tokens=args.max_enqueued_tokens,
    )
    output_root = args.output_dir or cfg["output_dir"]
    client = OpenAI(api_key=cfg["api_key"])

    run_dir = args.run_dir
    if args.resume and not run_dir:
        run_dir = find_resumable_run(output_root, args.input)
        if not run_dir:
            print("No resumable run found for this input.", file=sys.stderr)
            return 1
        print(f"Resuming run: {run_dir}")

    if run_dir:
        run_dir = run_dir.resolve()
        state = load_run_state(run_dir)
        tasks = load_tasks(run_dir)
        patients = load_patients(Path(state["input_path"]))
        model = cfg["model"] if args.model else state["model"]
    else:
        patients = load_patients(args.input)
        patients_by_id = {patient["patient_id"]: patient for patient in patients}
        tasks = plan_soap_tasks(patients)
        model = cfg["model"]
        max_tokens = cfg["max_enqueued_tokens"]

        run_dir = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir.mkdir(parents=True, exist_ok=True)
        batches_dir = run_dir / "batches"
        batches_dir.mkdir(parents=True, exist_ok=True)

        state = build_run_state(
            input_path=args.input,
            model=model,
            max_enqueued_tokens=max_tokens,
            tasks=tasks,
            patients_by_id=patients_by_id,
        )
        save_tasks(tasks, run_dir)
        save_run_state(run_dir, state)

        chunk_groups = chunk_tasks_for_state(tasks, state)
        print(
            f"Planned {len(tasks)} SOAP notes from {len(patients)} patients "
            f"in {len(chunk_groups)} chunk(s) (~{max_tokens:,} token limit per chunk)."
        )
        for chunk, chunk_task_list in zip(state["chunks"], chunk_groups):
            print(
                f"  chunk {chunk['index']}: {len(chunk_task_list)} tasks, "
                f"~{chunk['estimated_tokens']:,} tokens"
            )
            input_path = run_dir / chunk["input_jsonl"]
            write_batch_input(chunk_task_list, patients_by_id, model, input_path)

        if args.dry_run or not args.submit:
            print("Dry run complete." if args.dry_run else "Pass --submit to enqueue chunk batches.")
            print(f"Run directory: {run_dir}")
            return 0

    patients_by_id = {patient["patient_id"]: patient for patient in patients}

    if args.dry_run:
        chunk_groups = chunk_tasks_for_state(tasks, state)
        for chunk, chunk_task_list in zip(state["chunks"], chunk_groups):
            if chunk["status"] == "completed":
                continue
            write_batch_input(
                chunk_task_list,
                patients_by_id,
                model,
                run_dir / chunk["input_jsonl"],
            )
        print(f"Dry run complete. Run directory: {run_dir}")
        return 0

    if not args.submit:
        pending = sum(1 for chunk in state["chunks"] if chunk["status"] != "completed")
        print(f"{pending} chunk(s) pending in {run_dir}. Pass --submit to continue.")
        return 0

    return process_run(
        client,
        run_dir=run_dir,
        state=state,
        tasks=tasks,
        patients_by_id=patients_by_id,
        model=model,
        poll_interval=cfg["poll_interval"],
        submit=True,
        wait=args.wait,
    )


if __name__ == "__main__":
    raise SystemExit(main())
