"""Full-text search (FTS) + vector search (VS) hybrid funnel.

Chunks only ever carry identifiers (patient_id, encounter_id, chunk_id) —
text is hydrated lazily via `search.fetch_encounter_text`, and only for the
merged FTS+VS candidate set (typically far smaller than the raw 10k+5k bulk
results), which is the actual memory-saving step.

The windowed math guard is evaluated here purely for observability/logging —
it does NOT filter candidates out. Clinical notes often state a constraint
qualitatively ("creatinine elevated") or in prose ("LVEF greater than 35%")
without a value the guard can extract; excluding on a guard miss risked
dropping eligible patients before the Tier 3 agent — which has the full
note and can reason about qualitative language — ever evaluated them. The
analysis agent is the sole source of truth for constraint validation.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass

from app.config import get_settings
from app.models.search import SearchCriteria
from app.services.funnel.math_guard import evaluate_windowed_math_guard
from app.services.funnel.search import (
    NoteChunk,
    fetch_encounter_text,
    fetch_unique_patient_count,
    full_text_search,
    vector_search,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatientTimeline:
    patient_id: str
    chunks: list[NoteChunk]


@dataclass(frozen=True)
class FunnelMetrics:
    search_space_raw: int
    search_space_after_fts: int
    search_space_after_vs: int


async def run_fts_vector_filter(payload: SearchCriteria) -> tuple[list[PatientTimeline], FunnelMetrics]:
    """Run FTS and vector retrieval concurrently, then apply windowed math guard."""
    fts_task = asyncio.to_thread(full_text_search, payload)
    vs_task = asyncio.to_thread(vector_search, payload)
    fts_chunks, vs_chunks = await asyncio.gather(fts_task, vs_task)

    fts_patient_ids = {chunk.patient_id for chunk in fts_chunks}
    merged: dict[str, NoteChunk] = {}

    for chunk in fts_chunks:
        merged[chunk.chunk_id] = chunk
    for chunk in vs_chunks:
        if chunk.patient_id in fts_patient_ids or not fts_patient_ids:
            merged[chunk.chunk_id] = chunk

    survivors: list[NoteChunk] = list(merged.values())
    if payload.numerical_constraints:
        # Hydrate the whole encounter (note + labs + investigations) only
        # for the much smaller merged candidate set — logging only, not a
        # filter. Constraints are frequently in a lab/investigation chunk
        # rather than the SOAP note chunk that actually matched FTS/VS.
        guard_texts = await asyncio.gather(
            *(asyncio.to_thread(fetch_encounter_text, chunk.patient_id, chunk.encounter_id) for chunk in survivors)
        )
        soft_hits = 0
        for chunk, text in zip(survivors, guard_texts, strict=True):
            passed, evaluations = evaluate_windowed_math_guard(text, payload.numerical_constraints)
            soft_hits += int(passed)
            logger.debug(
                "guard patient_id=%s encounter_id=%s passed=%s evaluations=%s",
                chunk.patient_id,
                chunk.encounter_id,
                passed,
                [(e.parameter_name, e.passed, e.observed_values) for e in evaluations],
            )
        logger.info(
            "Math guard (informational only, not filtering): %s/%s candidates show constraint-relevant text",
            soft_hits,
            len(survivors),
        )

    grouped: dict[str, list[NoteChunk]] = defaultdict(list)
    for chunk in survivors:
        grouped[chunk.patient_id].append(chunk)

    timelines = [
        PatientTimeline(patient_id=pid, chunks=sorted(chunks, key=lambda c: c.encounter_date, reverse=True))
        for pid, chunks in grouped.items()
    ]
    timelines.sort(key=lambda t: t.chunks[0].encounter_date if t.chunks else t.patient_id, reverse=True)
    cap = get_settings().tier3_patient_cap
    timelines = timelines[:cap]

    raw_search_space = fetch_unique_patient_count()
    metrics = FunnelMetrics(
        search_space_raw=raw_search_space,
        search_space_after_fts=len(fts_chunks) or len(merged),
        search_space_after_vs=len(survivors),
    )
    logger.info(
        "Funnel complete: fts=%s merged=%s survivors=%s patients=%s",
        len(fts_chunks),
        len(merged),
        len(survivors),
        len(timelines),
    )
    return timelines, metrics
