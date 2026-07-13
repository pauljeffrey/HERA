"""Shared patient-id helpers for incremental clinical data pipelines."""

from __future__ import annotations
import re
from pathlib import Path
from hera_io.datasets import load_json_list

PT_ID = re.compile(r"^PT-(\d+)$")


def parse_patient_index(patient_id: str) -> int | None:
    match = PT_ID.match(patient_id.strip())
    if not match:
        return None
    return int(match.group(1))


def max_patient_index(records: list[dict]) -> int:
    indices = [idx for record in records if (idx := parse_patient_index(record.get("patient_id", ""))) is not None]
    return max(indices) if indices else 0


def merge_records_by_id(existing: list[dict], new: list[dict], *, id_key: str) -> list[dict]:
    merged = {row[id_key]: row for row in existing if row.get(id_key)}
    for row in new:
        key = row.get(id_key)
        if key:
            merged[key] = row
    return sorted(merged.values(), key=lambda row: row[id_key])


def load_canonical_patients(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return load_json_list(path, "patients")


def load_canonical_notes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return load_json_list(path, "notes")


def patient_ids_with_notes(notes: list[dict]) -> set[str]:
    return {note["patient_id"] for note in notes if note.get("patient_id") and (note.get("soap_note") or "").strip()}
