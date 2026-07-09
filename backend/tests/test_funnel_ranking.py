"""Funnel merge bypass and patient ranking."""

from datetime import datetime, timezone

from app.services.funnel.funnel_orchestrator import (
    PatientTimeline,
    _patient_rank_key,
    _vs_chunk_kept,
)
from app.services.funnel.search import NoteChunk


def _chunk(
    patient_id: str,
    *,
    score: float | None = None,
    day: int = 1,
) -> NoteChunk:
    return NoteChunk(
        patient_id=patient_id,
        encounter_id=f"ENC-{patient_id}",
        chunk_id=f"CHK-{patient_id}-{day}",
        encounter_date=datetime(2024, 1, day, tzinfo=timezone.utc),
        source_type="soap_note",
        vector_score=score,
    )


def test_vs_chunk_kept_for_fts_overlap():
    chunk = _chunk("P1", score=0.5)
    assert _vs_chunk_kept(chunk, fts_patient_ids={"P1"}, merge_threshold=0.9)


def test_vs_chunk_kept_for_high_score_without_fts():
    chunk = _chunk("P2", score=0.95)
    assert _vs_chunk_kept(chunk, fts_patient_ids={"P1"}, merge_threshold=0.9)


def test_vs_chunk_dropped_for_low_score_without_fts():
    chunk = _chunk("P2", score=0.8)
    assert not _vs_chunk_kept(chunk, fts_patient_ids={"P1"}, merge_threshold=0.9)


def test_patient_rank_key_prefers_guard_then_semantic():
    from app.services.funnel.math_guard import ConstraintEvaluation

    timeline = PatientTimeline(patient_id="P1", chunks=[_chunk("P1", score=0.95, day=2)])
    guard = {
        ("P1", "ENC-P1"): [
            ConstraintEvaluation("LVEF", True, [30.0], "lvef 30%"),
            ConstraintEvaluation("Creatinine", False, [1.2], "creatinine 1.2"),
        ]
    }
    rank = _patient_rank_key(timeline, guard_by_pair=guard, merge_threshold=0.42)
    assert rank[0] == 1
    assert rank[1] == 2
    assert rank[2] == 0.95


def test_fetch_fts_or_across_keywords():
    from app.services.funnel.search import fetch_fts_chunks

    keywords = [
        "HFrEF",
        "LVEF",
        "GDMT",
        "Guideline-directed medical therapy",
        "Serum Creatinine",
        "Heart Failure",
    ]
    assert len(fetch_fts_chunks(keywords, limit=5)) > 0
