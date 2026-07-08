"""Confirm Tier 1 full-text search against stored tsvector + GIN indexes."""

from __future__ import annotations

import pytest

FTS_CASES = [
    ("clinical_progress_notes", "heart failure"),
    ("lab_results", "creatinine"),
    ("encounter_investigations", "echocardiogram"),
    ("patient_notes_embeddings", "ejection fraction"),
]


def _table_has_fts(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = 'fts_doc'
            """,
            (table,),
        )
        return cur.fetchone() is not None


def _fts_search(conn, table: str, query: str, limit: int = 10) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT 1
            FROM {table}, plainto_tsquery('english', %s) q
            WHERE fts_doc @@ q
            LIMIT %s
            """,
            (query, limit),
        )
        return cur.fetchall()


@pytest.mark.parametrize("table,query", FTS_CASES)
def test_fts_index_column_exists(db_conn, table: str, query: str):
    assert _table_has_fts(db_conn, table), f"{table}.fts_doc missing — re-apply schema.sql"


@pytest.mark.parametrize("table,query", FTS_CASES)
def test_fts_returns_matches(db_conn, table: str, query: str):
    if not _table_has_fts(db_conn, table):
        pytest.skip(f"{table} has no fts_doc column")

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        if int(cur.fetchone()[0]) == 0:
            pytest.skip(f"{table} is empty — prepopulate + ingest first")

    rows = _fts_search(db_conn, table, query)
    assert rows, f"FTS query '{query}' returned no rows from {table}"


def test_fts_uses_stored_tsvector_not_runtime_to_tsvector(db_conn):
    """EXPLAIN should reference the GIN index on fts_doc, not compute to_tsvector at query time."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            EXPLAIN (FORMAT TEXT)
            SELECT patient_id FROM clinical_progress_notes, plainto_tsquery('english', 'creatinine') q
            WHERE fts_doc @@ q
            LIMIT 5
            """
        )
        plan = "\n".join(row[0] for row in cur.fetchall()).lower()

    if "clinical_progress_notes" not in plan:
        pytest.skip("clinical_progress_notes not available")

    assert "gin" in plan or "bitmap" in plan
