"""Criteria extraction and API helpers."""

from __future__ import annotations

import json
import logging
import random
import re
from collections import Counter

from app.config import CRITERIA_CACHE, CRITERIA_COUNTS_CACHE, get_settings, load_json_list, trajectories_path
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def all_criteria_counts(patients: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for patient in patients:
        raw = (patient.get("inclusion_exclusion_criteria") or "").strip()
        if raw:
            counts[raw] += 1
    return [{"text": text, "patient_count": count} for text, count in counts.most_common()]


def top_criteria_clauses(patients: list[dict], limit: int = 20) -> list[dict]:
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for patient in patients:
        raw = (patient.get("inclusion_exclusion_criteria") or "").strip()
        if not raw:
            continue
        for part in re.split(r";|\n|(?<=\.)\s+(?=[A-Z])", raw):
            clause = re.sub(r"\s+", " ", part).strip(" .")
            if len(clause) < 24:
                continue
            key = clause.lower()
            counts[key] += 1
            display.setdefault(key, clause[0].upper() + clause[1:] if clause else clause)
    return [
        {"text": display[key], "patient_count": count}
        for key, count in counts.most_common(limit)
    ]


def _criteria_from_file(limit: int | None = None) -> list[dict]:
    path = trajectories_path()
    if not path.exists():
        return []
    patients = load_json_list(path, "patients")
    items = all_criteria_counts(patients)
    return items[:limit] if limit else items


def _prompts_from_cache(limit: int) -> list[dict]:
    if CRITERIA_CACHE.exists():
        payload = json.loads(CRITERIA_CACHE.read_text(encoding="utf-8"))
        return payload.get("prompts", [])[:limit]
    path = trajectories_path()
    if not path.exists():
        return []
    return top_criteria_clauses(load_json_list(path, "patients"), limit)


def _counts_from_cache() -> list[dict]:
    if CRITERIA_COUNTS_CACHE.exists():
        payload = json.loads(CRITERIA_COUNTS_CACHE.read_text(encoding="utf-8"))
        return payload.get("criteria", [])
    return _criteria_from_file()


def _top_criteria_from_supabase(*, limit: int = 20) -> list[dict]:
    result = (
        get_supabase_client()
        .table("patients")
        .select("inclusion_exclusion_criteria")
        .not_.is_("inclusion_exclusion_criteria", "null")
        .neq("inclusion_exclusion_criteria", "")
        .execute()
    )
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for row in result.data or []:
        text = (row.get("inclusion_exclusion_criteria") or "").strip()
        if not text:
            continue
        key = text.lower()
        counts[key] += 1
        display.setdefault(key, text)
    return [{"text": display[key], "patient_count": count} for key, count in counts.most_common(limit)]


async def get_criteria_prompts(*, limit: int = 20) -> dict:
    settings = get_settings()

    if settings.database_mode == "supabase":
        try:
            prompts = _top_criteria_from_supabase(limit=limit)
            if prompts:
                return {"source": "supabase", "count": len(prompts), "prompts": prompts}
        except Exception as exc:
            logger.warning("Supabase criteria query failed, using cache fallback: %s", exc)
    elif settings.database_url.startswith("postgresql"):
        from sqlalchemy import func, select

        from app.db.database import AsyncSessionLocal
        from app.db.models import Patient

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(
                        Patient.inclusion_exclusion_criteria,
                        func.count(Patient.patient_id).label("patient_count"),
                    )
                    .where(Patient.inclusion_exclusion_criteria.is_not(None))
                    .where(Patient.inclusion_exclusion_criteria != "")
                    .group_by(Patient.inclusion_exclusion_criteria)
                    .order_by(func.count(Patient.patient_id).desc())
                    .limit(limit)
                )
            ).all()
            prompts = [{"text": row[0], "patient_count": int(row[1])} for row in rows if row[0]]
            if prompts:
                return {"source": "database", "count": len(prompts), "prompts": prompts}

    prompts = _prompts_from_cache(limit)
    return {"source": "dataset_cache", "count": len(prompts), "prompts": prompts}


def get_random_criterion() -> dict:
    criteria = _counts_from_cache()
    if not criteria:
        return {"source": "dataset_cache", "count": 0, "criterion": None}
    return {
        "source": "dataset_cache",
        "count": len(criteria),
        "criterion": random.choice(criteria),
    }
