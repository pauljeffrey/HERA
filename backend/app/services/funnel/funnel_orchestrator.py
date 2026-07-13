"""Full-text search (FTS) + vector search (VS) hybrid funnel.

Chunks only ever carry identifiers (patient_id, encounter_id, chunk_id) —
text is hydrated lazily via `search.fetch_encounter_text`, and only for the
merged FTS+VS candidate set (bounded by FTS_TOP_K / SEMANTIC_TOP_K).

The windowed math guard ranks survivors before the Tier 3 cap — it does
not filter anyone out. Qualitative-only notes ("creatinine elevated") may rank
lower but still reach Tier 3 when the cap allows; the analysis agent remains
the source of truth for eligibility.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass

from app.config import get_settings
from app.models.search import NumericalConstraint, SearchCriteria
from app.services.funnel.math_guard import ConstraintEvaluation, evaluate_windowed_math_guard
from app.services.funnel.search import (
    NoteChunk,
    fetch_encounter_texts_bulk,
    fetch_unique_patient_count,
    full_text_search,
    upsert_chunk,
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


def _vs_chunk_kept(
    chunk: NoteChunk,
    *,
    fts_patient_ids: set[str],
    merge_threshold: float,
) -> bool:
    if not fts_patient_ids:
        return True
    if chunk.patient_id in fts_patient_ids:
        return True
    return (chunk.vector_score or 0.0) >= merge_threshold


def _guard_by_encounter(
    survivors: list[NoteChunk],
    constraints: list[NumericalConstraint],
    texts_by_pair: dict[tuple[str, str], str],
) -> dict[tuple[str, str], list[ConstraintEvaluation]]:
    guard: dict[tuple[str, str], list[ConstraintEvaluation]] = {}
    seen: set[tuple[str, str]] = set()
    for chunk in survivors:
        pair = (chunk.patient_id, chunk.encounter_id)
        if pair in seen:
            continue
        seen.add(pair)
        text = texts_by_pair.get(pair, "")
        _, evaluations = evaluate_windowed_math_guard(text, constraints)
        guard[pair] = evaluations
    return guard


def _patient_rank_key(
    timeline: PatientTimeline,
    *,
    guard_by_pair: dict[tuple[str, str], list[ConstraintEvaluation]],
    merge_threshold: float,
) -> tuple[int, int, float, float]:
    """Higher tuple = higher priority for Tier 3."""
    evaluations: list[ConstraintEvaluation] = []
    seen_pairs: set[tuple[str, str]] = set()
    for chunk in timeline.chunks:
        pair = (chunk.patient_id, chunk.encounter_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        evaluations.extend(guard_by_pair.get(pair, []))

    strict_pass = sum(1 for item in evaluations if item.passed)
    soft_observed = sum(1 for item in evaluations if item.observed_values)
    vs_scores = [chunk.vector_score for chunk in timeline.chunks if chunk.vector_score is not None]
    max_vs = max(vs_scores) if vs_scores else 0.0
    semantic = max_vs if max_vs >= merge_threshold else 0.0
    latest = max(chunk.encounter_date.timestamp() for chunk in timeline.chunks)
    return (strict_pass, soft_observed, semantic, latest)


def _tier3_cap(payload: SearchCriteria, settings) -> int:
    """Hard ceiling for Agent 2 evaluations: min(requested, TIER3_PATIENT_CAP)."""
    hard_cap = settings.tier3_patient_cap
    requested = payload.n_candidates
    if requested is not None and requested > 0:
        return min(requested, hard_cap)
    return hard_cap


async def run_fts_vector_filter(payload: SearchCriteria) -> tuple[list[PatientTimeline], FunnelMetrics]:
    """Run FTS and vector retrieval concurrently, merge, rank, then cap for Tier 3."""
    settings = get_settings()
    fts_task = asyncio.to_thread(full_text_search, payload)
    vs_task = asyncio.to_thread(vector_search, payload)
    fts_chunks, vs_chunks = await asyncio.gather(fts_task, vs_task)

    fts_patient_ids = {chunk.patient_id for chunk in fts_chunks}
    merged: dict[str, NoteChunk] = {}
    merge_threshold = settings.vs_merge_score_threshold

    for chunk in fts_chunks:
        merged[chunk.chunk_id] = chunk
    for chunk in vs_chunks:
        if _vs_chunk_kept(chunk, fts_patient_ids=fts_patient_ids, merge_threshold=merge_threshold):
            upsert_chunk(merged, chunk)

    survivors: list[NoteChunk] = list(merged.values())
    guard_by_pair: dict[tuple[str, str], list[ConstraintEvaluation]] = {}
    if payload.numerical_constraints:
        pairs = [(chunk.patient_id, chunk.encounter_id) for chunk in survivors]
        texts_by_pair = await asyncio.to_thread(fetch_encounter_texts_bulk, pairs)
        guard_by_pair = _guard_by_encounter(survivors, payload.numerical_constraints, texts_by_pair)
        soft_hits = sum(
            1
            for evaluations in guard_by_pair.values()
            if any(item.passed or item.observed_values for item in evaluations)
        )
        logger.info(
            "Math guard ranking signal: %s/%s encounters show constraint-relevant text",
            soft_hits,
            len(guard_by_pair),
        )

    grouped: dict[str, list[NoteChunk]] = defaultdict(list)
    for chunk in survivors:
        grouped[chunk.patient_id].append(chunk)

    timelines = [
        PatientTimeline(
            patient_id=patient_id,
            chunks=sorted(chunks, key=lambda chunk: chunk.encounter_date, reverse=True),
        )
        for patient_id, chunks in grouped.items()
    ]
    timelines.sort(
        key=lambda timeline: _patient_rank_key(
            timeline,
            guard_by_pair=guard_by_pair,
            merge_threshold=merge_threshold,
        ),
        reverse=True,
    )
    cap = _tier3_cap(payload, settings)
    timelines = timelines[:cap]

    raw_search_space = fetch_unique_patient_count()
    metrics = FunnelMetrics(
        search_space_raw=raw_search_space,
        search_space_after_fts=len(fts_chunks) or len(merged),
        search_space_after_vs=len(survivors),
    )
    logger.info(
        "Funnel complete: fts=%s merged=%s survivors=%s patients_to_tier3=%s (cap=%s)",
        len(fts_chunks),
        len(merged),
        len(survivors),
        len(timelines),
        cap,
    )
    return timelines, metrics
