"""Push SOAP progress notes JSON into Supabase."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

DEFAULT_TABLE = "clinical_progress_notes"


def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise ValueError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) in .env")
    return create_client(url, key)


def load_notes(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "notes" in payload:
        return payload["notes"]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unrecognized SOAP dataset format in {path}")


def to_rows(notes: list[dict]) -> list[dict]:
    return [
        {
            "patient_id": note["patient_id"],
            "encounter_id": note["encounter_id"],
            "encounter_index": note["encounter_index"],
            "encounter_type": note.get("encounter_type"),
            "specialty_key": note.get("specialty_key"),
            "specialty_label": note.get("specialty_label"),
            "scenario_brief": note.get("scenario_brief"),
            "soap_note": note["soap_note"],
        }
        for note in notes
    ]


def push_notes(
    client: Client,
    rows: list[dict],
    *,
    table: str,
    batch_size: int = 500,
    upsert: bool = True,
) -> int:
    inserted = 0
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        if upsert:
            client.table(table).upsert(chunk, on_conflict="patient_id,encounter_index").execute()
        else:
            client.table(table).insert(chunk).execute()
        inserted += len(chunk)
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Load SOAP notes JSON into Supabase.")
    parser.add_argument("--input", type=Path, required=True, help="Path to soap_progress_notes.json")
    parser.add_argument("--table", default=os.getenv("SUPABASE_NOTES_TABLE", DEFAULT_TABLE))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--insert", action="store_true", help="Use INSERT instead of UPSERT.")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        client = get_client()
        notes = load_notes(args.input)
        rows = to_rows(notes)
        count = push_notes(
            client,
            rows,
            table=args.table,
            batch_size=args.batch_size,
            upsert=not args.insert,
        )
    except Exception as exc:
        print(f"Failed to push notes: {exc}", file=sys.stderr)
        return 1

    print(f"Pushed {count} rows to Supabase table '{args.table}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
