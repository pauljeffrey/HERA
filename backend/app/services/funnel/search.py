"""Full-text search (FTS) and vector search (VS) retrieval.

`NoteChunk` carries identifiers only (patient_id, encounter_id, chunk_id) —
not the note text. Bulk FTS/VS queries return up to thousands of rows;
carrying full text for all of them was the main memory cost of the funnel.
Text is hydrated lazily, only for the much smaller post-merge candidate set,
via `fetch_chunk_text`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime

from app.db.connection import connect
from app.models.search import SearchCriteria
from app.services.funnel import vector_store

logger = logging.getLogger(__name__)

VS_MIN_SIMILARITY = float(os.getenv("VS_MIN_SIMILARITY", "0.72"))


@dataclass(frozen=True)
class NoteChunk:
    patient_id: str
    encounter_id: str
    chunk_id: str
    encounter_date: datetime
    source_type: str
    vector_score: float | None = None


def _fts_query(keywords: list[str]) -> str:
    return " | ".join(k.strip() for k in keywords if k.strip())


def fetch_unique_patient_count() -> int:
    """Count distinct patients in the DB — used as the raw search-space metric."""
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM patients")
            row = cur.fetchone()
            if row and row[0]:
                return int(row[0])
    except Exception as exc:
        logger.warning("Patient count query failed: %s", exc)

    from app.services.clinical.mock_data import DEMO_PATIENTS

    return len(DEMO_PATIENTS)


def fetch_fts_chunks(keywords: list[str], *, limit: int = 10_000) -> list[NoteChunk]:
    query = _fts_query(keywords)
    if not query:
        return []

    sql = """
        SELECT chunk_id, patient_id, encounter_id, encounter_date, source_type
        FROM patient_notes_embeddings, plainto_tsquery('english', %s) q
        WHERE fts_doc @@ q
        ORDER BY encounter_date DESC
        LIMIT %s
    """
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (query, limit))
            return [_row_to_chunk(row) for row in cur.fetchall()]
    except Exception as exc:
        logger.warning("FTS failed, falling back to source-table FTS: %s", exc)
        try:
            return _fts_soap_fallback(query, limit)
        except Exception as exc:
            logger.warning("Source-table FTS fallback failed: %s", exc)
            return []


def _fts_soap_fallback(query: str, limit: int) -> list[NoteChunk]:
    """Fallback FTS directly against clinical_progress_notes, lab_results, and
    encounter_investigations (each tied to an encounter) — used only when the
    primary `patient_notes_embeddings` query itself errors (e.g. table missing).
    Constraints are typically found in lab/investigation results, so those
    tables must be searchable here too, not just SOAP notes."""
    sql = """
        SELECT c.id, p.patient_id, e.encounter_id, e.occurred_at, 'soap_note'
        FROM clinical_progress_notes c
        JOIN encounters e ON e.id = c.encounter_id
        JOIN patients p ON p.patient_id = c.patient_id,
        plainto_tsquery('english', %s) q
        WHERE c.fts_doc @@ q

        UNION ALL

        SELECT lr.id, p.patient_id, e.encounter_id, e.occurred_at, 'lab_result'
        FROM lab_results lr
        JOIN lab_panels lp ON lp.id = lr.lab_panel_id
        JOIN encounters e ON e.id = lp.encounter_id
        JOIN patients p ON p.patient_id = e.patient_id,
        plainto_tsquery('english', %s) q
        WHERE lr.fts_doc @@ q

        UNION ALL

        SELECT ei.id, p.patient_id, e.encounter_id, e.occurred_at, 'investigation'
        FROM encounter_investigations ei
        JOIN encounters e ON e.id = ei.encounter_id
        JOIN patients p ON p.patient_id = e.patient_id,
        plainto_tsquery('english', %s) q
        WHERE ei.fts_doc @@ q

        ORDER BY 4 DESC
        LIMIT %s
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (query, query, query, limit))
        chunks = [
            NoteChunk(
                patient_id=row[1],
                encounter_id=row[2],
                chunk_id=str(row[0]),
                encounter_date=row[3],
                source_type=row[4],
            )
            for row in cur.fetchall()
        ]
        logger.debug("FTS fallback matched %s rows across notes/labs/investigations", len(chunks))
        return chunks


def fetch_chunk_text(chunk_id: str) -> str:
    """Lazily hydrate the text for one chunk — cheap PK lookup, called only
    for the small post-merge candidate set, never for bulk FTS/VS results."""
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT raw_text FROM patient_notes_embeddings WHERE chunk_id = %s::uuid",
                (chunk_id,),
            )
            row = cur.fetchone()
            return row[0] if row else ""
    except Exception as exc:
        logger.warning("fetch_chunk_text failed for chunk_id=%s: %s", chunk_id, exc)
        return ""


def fetch_encounter_text(patient_id: str, encounter_id: str) -> str:
    """All indexed text for one encounter — SOAP note + lab results +
    investigations, concatenated. Constraints (e.g. a creatinine threshold)
    are often stated in a lab/investigation chunk rather than the SOAP note
    chunk that matched FTS/VS, so guard evaluation and Tier 3 review should
    see the whole encounter, not just the one matched chunk."""
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_type, raw_text
                FROM patient_notes_embeddings
                WHERE patient_id = %s AND encounter_id = %s
                ORDER BY source_type, chunk_index
                """,
                (patient_id, encounter_id),
            )
            rows = cur.fetchall()
            logger.debug(
                "fetch_encounter_text patient_id=%s encounter_id=%s rows=%s", patient_id, encounter_id, len(rows)
            )
            return "\n".join(f"[{source_type}] {text}" for source_type, text in rows)
    except Exception as exc:
        logger.warning("fetch_encounter_text failed patient_id=%s encounter_id=%s: %s", patient_id, encounter_id, exc)
        return ""


def fetch_encounter_texts_bulk(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Batched version of `fetch_encounter_text` — one connection, one query,
    for the whole merged candidate set. Opening a fresh connection per
    candidate (the original approach) fires dozens of concurrent connections
    at the Supabase pooler, which starts timing them out under that load."""
    if not pairs:
        return {}
    patient_ids = [p for p, _ in pairs]
    encounter_ids = [e for _, e in pairs]
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT pne.patient_id, pne.encounter_id, pne.source_type, pne.raw_text
                FROM patient_notes_embeddings pne
                JOIN unnest(%s::text[], %s::text[]) AS pairs(patient_id, encounter_id)
                  ON pne.patient_id = pairs.patient_id AND pne.encounter_id = pairs.encounter_id
                ORDER BY pne.patient_id, pne.encounter_id, pne.source_type, pne.chunk_index
                """,
                (patient_ids, encounter_ids),
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("fetch_encounter_texts_bulk failed for %s pairs: %s", len(pairs), exc)
        return {}

    grouped: dict[tuple[str, str], list[str]] = {}
    for patient_id, encounter_id, source_type, raw_text in rows:
        grouped.setdefault((patient_id, encounter_id), []).append(f"[{source_type}] {raw_text}")
    return {key: "\n".join(parts) for key, parts in grouped.items()}


def _fetch_vs_chunks_pgvector(query_vector: list[float], *, limit: int) -> list[NoteChunk]:
    vector_literal = f"[{','.join(str(v) for v in query_vector)}]"
    sql = """
        SELECT chunk_id, patient_id, encounter_id, encounter_date, source_type,
               1 - (embedding <=> %s::vector) AS similarity
        FROM patient_notes_embeddings
        WHERE embedding IS NOT NULL
          AND 1 - (embedding <=> %s::vector) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (vector_literal, vector_literal, VS_MIN_SIMILARITY, vector_literal, limit))
        return [
            NoteChunk(
                patient_id=row[1],
                encounter_id=row[2],
                chunk_id=str(row[0]),
                encounter_date=row[3],
                source_type=row[4],
                vector_score=float(row[5]),
            )
            for row in cur.fetchall()
        ]


def _fetch_vs_chunks_pinecone(query_text: str, *, limit: int, patient_ids: list[str] | None) -> list[NoteChunk]:
    matches = vector_store.search_records(query_text, top_k=limit, patient_ids=patient_ids)
    chunks: list[NoteChunk] = []
    for match in matches:
        encounter_date = match.get("encounter_date")
        chunks.append(
            NoteChunk(
                patient_id=match["patient_id"],
                encounter_id=match["encounter_id"],
                chunk_id=match["chunk_id"],
                encounter_date=datetime.fromisoformat(encounter_date) if encounter_date else datetime.now(),
                source_type=match.get("source_type", "unknown"),
                vector_score=match.get("score"),
            )
        )
    return chunks


def embed_query(text: str) -> list[float]:
    try:
        return vector_store.embed_texts([text])[0]
    except Exception as exc:
        logger.warning("Embedding model unavailable: %s", exc)
        return []


def full_text_search(payload: SearchCriteria, *, limit: int = 10_000) -> list[NoteChunk]:
    chunks = fetch_fts_chunks(payload.lexical_keywords, limit=limit)
    if payload.target_patient_ids:
        allowed = set(payload.target_patient_ids)
        chunks = [c for c in chunks if c.patient_id in allowed]
    return chunks


def _search_one_query(query_text: str, *, limit: int, patient_ids: list[str] | None) -> list[NoteChunk]:
    if not query_text.strip():
        return []
    try:
        if vector_store.uses_pinecone():
            return _fetch_vs_chunks_pinecone(query_text, limit=limit, patient_ids=patient_ids)
        vector = embed_query(query_text)
        if not vector:
            return []
        return _fetch_vs_chunks_pgvector(vector, limit=limit)
    except Exception as exc:
        logger.warning("Vector search unavailable for query %r: %s", query_text[:80], exc)
        return []


def vector_search(payload: SearchCriteria, *, limit: int = 5_000) -> list[NoteChunk]:
    """Runs `semantic_query` plus any `semantic_query_variants` (dissimilar
    rephrasings the chat agent generated) and merges results, so recall
    doesn't depend on one phrasing matching the note's exact wording."""
    queries = [payload.semantic_query, *payload.semantic_query_variants]
    seen: dict[str, NoteChunk] = {}
    for query_text in queries:
        for chunk in _search_one_query(query_text, limit=limit, patient_ids=payload.target_patient_ids):
            existing = seen.get(chunk.chunk_id)
            if existing is None or (chunk.vector_score or 0) > (existing.vector_score or 0):
                seen[chunk.chunk_id] = chunk
    chunks = list(seen.values())
    if payload.target_patient_ids:
        allowed = set(payload.target_patient_ids)
        chunks = [c for c in chunks if c.patient_id in allowed]
    logger.debug("vector_search: %s queries -> %s merged chunks", len(queries), len(chunks))
    return chunks


def _row_to_chunk(row) -> NoteChunk:
    return NoteChunk(
        patient_id=row[1],
        encounter_id=row[2],
        chunk_id=str(row[0]),
        encounter_date=row[3],
        source_type=row[4],
    )
