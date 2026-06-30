"""CLI to batch-convert structured trajectories into SOAP progress notes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openai import OpenAI

from soap_notes.engine import (
    download_batch_files,
    find_manifest,
    load_patients,
    load_tasks,
    parse_batch_results,
    plan_soap_tasks,
    save_manifest,
    save_tasks,
    settings,
    submit_batch,
    wait_for_batch,
    write_batch_input,
    write_dataset,
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
    parser.add_argument("--model", help="OpenAI model (default: gpt-4o-mini).")
    parser.add_argument("--dry-run", action="store_true", help="Build batch input only.")
    parser.add_argument("--submit", action="store_true", help="Upload and create a batch job.")
    parser.add_argument("--wait", action="store_true", help="Poll until the batch finishes.")
    parser.add_argument("--batch-id", help="Collect results from an existing batch.")
    parser.add_argument("--poll-interval", type=int, default=30)
    args = parser.parse_args()

    cfg = settings(model=args.model, poll_interval=args.poll_interval)
    output_root = args.output_dir or cfg["output_dir"]
    client = OpenAI(api_key=cfg["api_key"])

    if args.batch_id:
        manifest_path = find_manifest(output_root, args.batch_id)
        if not manifest_path:
            print(f"No manifest found for batch {args.batch_id}.", file=sys.stderr)
            return 1
        run_dir = manifest_path.parent.parent
        tasks = load_tasks(run_dir)
        batch = client.batches.retrieve(args.batch_id)
        if args.wait and batch.status not in {"completed", "failed", "expired", "cancelled"}:
            print("Waiting for batch completion...")
            batch = wait_for_batch(client, args.batch_id, cfg["poll_interval"])
    else:
        patients = load_patients(args.input)
        patients_by_id = {patient["patient_id"]: patient for patient in patients}
        tasks = plan_soap_tasks(patients)

        run_dir = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        batches_dir = run_dir / "batches"
        batches_dir.mkdir(parents=True, exist_ok=True)

        print(f"Planned {len(tasks)} SOAP notes from {len(patients)} patients.")
        input_path = batches_dir / "soap_batch_input.jsonl"
        write_batch_input(tasks, patients_by_id, cfg["model"], input_path)
        save_tasks(tasks, run_dir)
        print(f"Wrote batch input: {input_path}")

        if args.dry_run or not args.submit:
            print("Dry run complete." if args.dry_run else "Pass --submit to enqueue the batch.")
            return 0

        batch = submit_batch(client, input_path, f"HERA SOAP notes ({len(tasks)} encounters)")
        manifest_path = batches_dir / f"{batch.id}_manifest.json"
        save_manifest(batch, manifest_path, input_jsonl=input_path, task_count=len(tasks))
        print(f"Created batch {batch.id} (status: {batch.status})")

        if not args.wait:
            print(f"Track with: python -m soap_notes.generate --input {args.input} --batch-id {batch.id} --wait")
            return 0

        print("Waiting for batch completion...")
        batch = wait_for_batch(client, batch.id, cfg["poll_interval"])
        save_manifest(batch, manifest_path, input_jsonl=input_path, task_count=len(tasks))
        print(f"Batch finished with status: {batch.status}")

    if batch.status != "completed":
        print(f"Batch {batch.id} is not completed (status: {batch.status}).", file=sys.stderr)
        return 1

    batches_dir = run_dir / "batches"
    datasets_dir = run_dir / "datasets"
    output_path, error_path = download_batch_files(client, batch, batches_dir)
    if not output_path:
        print("Batch completed but no output file was produced.", file=sys.stderr)
        return 1

    notes, failures = parse_batch_results(output_path, {task.custom_id: task for task in tasks})
    dataset_path = datasets_dir / "soap_progress_notes.json"
    write_dataset(notes, dataset_path)

    print(f"Saved {len(notes)} SOAP notes to {dataset_path}")
    if failures:
        failure_path = datasets_dir / "parse_failures.json"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
        print(f"Saved {len(failures)} failures to {failure_path}")
    if error_path:
        print(f"OpenAI error file: {error_path}")

    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
