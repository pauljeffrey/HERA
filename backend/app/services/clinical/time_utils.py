"""Shared datetime parsing for agent tool calls."""

from __future__ import annotations

from datetime import datetime


def parse_at(datetime_iso: str | None) -> datetime | None:
    if not datetime_iso:
        return None
    return datetime.fromisoformat(datetime_iso.replace("Z", "+00:00"))
