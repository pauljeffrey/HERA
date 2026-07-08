"""Confirm embedding generation and pgvector similarity search."""

from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")


def _embedding_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM patient_notes_embeddings WHERE embedding IS NOT NULL")
        return int(cur.fetchone()[0])


def _vector_search(conn, embedding: list[float], limit: int = 5) -> list[tuple]:
    vector_literal = f"[{','.join(str(v) for v in embedding)}]"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT patient_id, encounter_id, source_type,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM patient_notes_embeddings
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector_literal, vector_literal, limit),
        )
        return cur.fetchall()


def test_embeddings_table_and_index(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM pg_indexes
            WHERE tablename = 'patient_notes_embeddings' AND indexname = 'idx_pne_vector'
            """
        )
        assert cur.fetchone(), "HNSW index idx_pne_vector missing — re-apply schema.sql"


def test_embed_texts_dimension():
    from app.services.clinical.ehr_ingest import EMBED_DIM, embed_texts

    vectors = embed_texts(["heart failure with preserved ejection fraction"])
    assert len(vectors) == 1
    assert len(vectors[0]) == EMBED_DIM


def test_vector_similarity_search(db_conn):
    if _embedding_count(db_conn) == 0:
        pytest.skip("No embeddings — run: python -m scripts.ingest_ehr")

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT embedding::text
            FROM patient_notes_embeddings
            WHERE embedding IS NOT NULL
            LIMIT 1
            """
        )
        row = cur.fetchone()
    assert row, "Expected at least one stored embedding"

    embedding = [float(x) for x in row[0].strip("[]").split(",")]
    hits = _vector_search(db_conn, embedding, limit=3)
    assert hits
    assert hits[0][3] >= 0.99, "Self-similarity should be ~1.0 for identical vector"


def test_semantic_query_finds_related_chunks(db_conn):
    from app.services.clinical.ehr_ingest import embed_texts

    if _embedding_count(db_conn) == 0:
        pytest.skip("No embeddings — run: python -m scripts.ingest_ehr")

    query = "patient with reduced left ventricular ejection fraction heart failure"
    query_vector = embed_texts([query])[0]
    hits = _vector_search(db_conn, query_vector, limit=5)
    assert hits, "Semantic vector search returned no results"
    assert hits[0][3] > 0.3, "Top hit should be reasonably similar to the clinical query"
