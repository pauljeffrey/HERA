"""JSON dataset read/write helpers shared across pipelines and backend."""

from __future__ import annotations

import json
from pathlib import Path

def load_json_list(path: Path, key: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get(key, [])
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unrecognized JSON format in {path}")

def write_json_dataset(records: list[dict], path: Path, *, wrapper_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"count": len(records), wrapper_key: records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def batch_response_content(line: dict) -> str | None:
    if line.get("error"):
        return None
    response = line.get("response") or {}
    if response.get("status_code") != 200:
        return None
    choices = (response.get("body") or {}).get("choices") or []
    if not choices:
        return None
    return (choices[0].get("message") or {}).get("content")
