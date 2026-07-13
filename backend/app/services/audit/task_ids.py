"""Task ID parsing — agents and markdown often append trailing punctuation."""

from __future__ import annotations

import re
import uuid

_TASK_ID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def normalize_task_id(raw: str) -> str:
    """Extract a canonical UUID from a path segment or free text."""
    match = _TASK_ID_RE.search(raw.strip())
    if not match:
        raise ValueError(f"Invalid task_id: {raw!r}")
    value = match.group(1).lower()
    uuid.UUID(value)  # validate version nibble layout
    return value
