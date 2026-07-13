"""CLI for synthetic patient trajectory generation."""

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

from structured_clinical_data.engine import (
    Settings,
    canonical_dataset_path,
    download_batch_files,
    find_manifest,
    find_resumable_run,
    load_run_state,
    load_tasks,
    merge_into_canonical,
    parse_results,
    plan_tasks,
    resume_start_index,
    save_manifest,
    save_run_state,
    save_tasks,
    specialty_counts,
    submit_batch,
    wait_for_batch,
    write_batch_input,
    write_dataset,
)


def _collect_batch(
    client: OpenAI,
    *,
    run_dir: Path,
    tasks: list,
    batch,
    settings: Settings,
    state: dict | None = None,
) -> int:
    if batch.status != "completed":
        print(f"Batch {batch.id} is not completed (status: {batch.status}).", file=sys.stderr)
        return 1

    batches_dir = run_dir / "batches"
    output_path, error_path = download_batch_files(client, batch, batches_dir)
    if not output_path:
        print("Batch completed but no output file was produced.", file=sys.stderr)
        if error_path:
            print(f"All requests failed — see error file: {error_path}", file=sys.stderr)
        return 1

    records, failures = parse_results(output_path, {task.custom_id: task for task in tasks})
    dataset_path = run_dir / "datasets" / "patient_trajectories.json"
    write_dataset(records, dataset_path)
    canonical = merge_into_canonical(settings.output_dir, records)
    print(f"Saved {len(records)} trajectories to {dataset_path}")
    print(f"Merged {len(records)} into canonical dataset: {canonical}")

    if state is not None:
        state["status"] = "completed"
        state["batch_id"] = batch.id
        state["batch_status"] = batch.status
        save_run_state(run_dir, state)

    if failures:
        failure_path = run_dir / "datasets" / "parse_failures.json"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
        print(f"Saved {len(failures)} failures to {failure_path}")
    if error_path:
        print(f"OpenAI error file: {error_path}")

    return 0 if not failures else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic clinical trajectories.")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Records to generate this run (default: remaining until DATASET_TARGET_COUNT).",
    )
    parser.add_argument("--output-dir", type=Path, help="Output root directory.")
    parser.add_argument("--model", help="OpenAI model (default: MODEL_NAME from .env).")
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="Build batch input only.")
    parser.add_argument("--submit", action="store_true", help="Upload and create a batch job.")
    parser.add_argument("--wait", action="store_true", help="Poll until the batch finishes.")
    parser.add_argument("--batch-id", help="Collect results from an existing batch.")
    parser.add_argument("--run-dir", type=Path, help="Resume a specific run directory.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from canonical dataset or latest incomplete run.",
    )
    parser.add_argument("--poll-interval", type=int, default=30)
    args = parser.parse_args()

    settings = Settings.load(
        count=args.count,
        output_dir=args.output_dir,
        model=args.model,
        poll_interval=args.poll_interval,
    )
    client = OpenAI(api_key=settings.api_key)

    run_dir = args.run_dir.resolve() if args.run_dir else None
    state: dict | None = None

    if args.batch_id:
        manifest_path = find_manifest(settings.output_dir, args.batch_id)
        if not manifest_path:
            print(f"No manifest found for batch {args.batch_id}.", file=sys.stderr)
            return 1
        run_dir = manifest_path.parent.parent
        tasks = load_tasks(run_dir)
        state = load_run_state(run_dir) if (run_dir / "run_state.json").exists() else None
        batch = client.batches.retrieve(args.batch_id)
        if args.wait and batch.status not in {"completed", "failed", "expired", "cancelled"}:
            print("Waiting for batch completion...")
            batch = wait_for_batch(client, args.batch_id, settings.poll_interval)
        return _collect_batch(client, run_dir=run_dir, tasks=tasks, batch=batch, settings=settings, state=state)

    if args.resume and not run_dir:
        run_dir = find_resumable_run(settings.output_dir)

    if run_dir:
        run_dir = run_dir.resolve()
        state = load_run_state(run_dir)
        tasks = load_tasks(run_dir)
        batch_id = state.get("batch_id")
        if batch_id and state.get("status") != "completed":
            batch = client.batches.retrieve(batch_id)
            if args.wait and batch.status not in {"completed", "failed", "expired", "cancelled"}:
                print("Waiting for batch completion...")
                batch = wait_for_batch(client, batch_id, settings.poll_interval)
            if batch.status == "completed":
                return _collect_batch(
                    client, run_dir=run_dir, tasks=tasks, batch=batch, settings=settings, state=state
                )
            if not args.submit:
                print(
                    f"Run {run_dir} has batch {batch_id} (status={batch.status}). "
                    "Pass --wait to collect results or --submit to retry."
                )
                return 0

    start_index, remaining = resume_start_index(settings.output_dir, settings.target_count)
    batch_count = args.count if args.count is not None else remaining
    if batch_count <= 0:
        canonical = canonical_dataset_path(settings.output_dir)
        print(f"Canonical dataset already has {start_index - 1} patients (target={settings.target_count}).")
        print(f"No new trajectories needed. See {canonical}")
        return 0

    if not run_dir:
        run_dir = settings.output_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        batches_dir = run_dir / "batches"
        batches_dir.mkdir(parents=True, exist_ok=True)

        tasks = plan_tasks(batch_count, seed=args.seed, start_index=start_index)
        total = len(tasks)
        print(f"Planned {total} generation tasks starting at PT-{start_index:06d}:")
        for key, count in specialty_counts(tasks).items():
            print(f"  {key}: {count} ({count / total * 100:.1f}%)")

        input_path = batches_dir / "batch_input.jsonl"
        write_batch_input(tasks, settings.model, input_path)
        save_tasks(tasks, run_dir)
        state = {
            "version": 1,
            "target_count": settings.target_count,
            "start_index": start_index,
            "batch_count": batch_count,
            "model": settings.model,
            "status": "pending",
            "batch_id": None,
            "batch_status": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_run_state(run_dir, state)
        print(f"Wrote batch input: {input_path}")

        if args.dry_run or not args.submit:
            print("Dry run complete." if args.dry_run else "Pass --submit to enqueue the batch.")
            print(f"Run directory: {run_dir}")
            return 0

        batch = submit_batch(client, input_path, f"HERA synthetic trajectories ({len(tasks)} records)")
        manifest_path = batches_dir / f"{batch.id}_manifest.json"
        save_manifest(batch, manifest_path, input_jsonl=input_path, task_count=len(tasks))
        state["batch_id"] = batch.id
        state["batch_status"] = batch.status
        state["status"] = "submitted"
        save_run_state(run_dir, state)
        print(f"Created batch {batch.id} (status: {batch.status})")

        if not args.wait:
            print(
                "Track with: python clinical_data_gen/structured_clinical_data/generate.py "
                f"--run-dir \"{run_dir}\" --resume --wait"
            )
            return 0

        print("Waiting for batch completion...")
        batch = wait_for_batch(client, batch.id, settings.poll_interval)
        save_manifest(batch, manifest_path, input_jsonl=input_path, task_count=len(tasks))
        print(f"Batch finished with status: {batch.status}")
        return _collect_batch(client, run_dir=run_dir, tasks=tasks, batch=batch, settings=settings, state=state)

    print(f"Nothing to do in run directory {run_dir}. Pass --submit to enqueue a new batch.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
