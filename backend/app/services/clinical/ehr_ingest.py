"""Step 0: fetch EHR text from Supabase, scrub PII, chunk, embed, store in pgvector."""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

import tiktoken

logger = logging.getLogger(__name__)

EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "pritamdeka/S-PubMedBert-MS-MARCO")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "400"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "64"))
UPSERT_BATCH = int(os.getenv("INGEST_UPSERT_BATCH", "100"))
PAGE_SIZE = 1000

PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
MRN_RE = re.compile(r"\b(?:MRN|medical record)[:\s#]*\d+\b", re.I)

CHUNK_NS = uuid.UUID("c9bf9e59-1675-4b49-8e2b-0d6c8e8f0a11")


@dataclass
class EhrDocument:
    patient_id: str
    encounter_id: str
    encounter_uuid: str
    encounter_date: datetime
    source_type: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    lab_result_id: str | None = None
    investigation_id: str | None = None


@dataclass
class TextChunk:
    patient_id: str
    encounter_id: str
    encounter_uuid: str
    encounter_date: datetime
    source_type: str
    chunk_index: int
    raw_text: str
    metadata: dict[str, Any]
    lab_result_id: str | None = None
    investigation_id: str | None = None


def chunk_id_for(doc: TextChunk) -> str:
    key = f"{doc.patient_id}:{doc.encounter_id}:{doc.source_type}:{doc.chunk_index}"
    return str(uuid.uuid5(CHUNK_NS, key))


def scrub_pii(text: str, patient_names: Iterable[str] | None = None) -> str:
    cleaned = PHONE_RE.sub("[PHONE]", text)
    cleaned = EMAIL_RE.sub("[EMAIL]", cleaned)
    cleaned = SSN_RE.sub("[SSN]", cleaned)
    cleaned = MRN_RE.sub("[MRN]", cleaned)
    for name in sorted({n.strip() for n in (patient_names or []) if n and len(n.strip()) > 2}, key=len, reverse=True):
        cleaned = re.sub(re.escape(name), "[PATIENT]", cleaned, flags=re.IGNORECASE)
    return cleaned


def _encoding():
    return tiktoken.get_encoding("cl100k_base")


def chunk_text(text: str, *, max_tokens: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split on token boundaries with overlap so clinical context spans chunk edges."""
    tokens = _encoding().encode(text)
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    enc = _encoding()
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        piece = enc.decode(tokens[start:end]).strip()
        if piece:
            chunks.append(piece)
        if end >= len(tokens):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.fromisoformat("1970-01-01T00:00:00+00:00")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _paginate(client, table: str, select: str, *, order: str | None = None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        query = client.table(table).select(select)
        if order:
            query = query.order(order)
        result = query.range(offset, offset + PAGE_SIZE - 1).execute()
        batch = result.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def fetch_patient_names(client) -> set[str]:
    rows = _paginate(client, "patients", "name")
    return {row["name"] for row in rows if row.get("name")}


def fetch_ehr_documents(client) -> list[EhrDocument]:
    encounters = {
        row["id"]: row
        for row in _paginate(
            client,
            "encounters",
            "id, patient_id, encounter_id, occurred_at, encounter_type, encounter_index",
            order="occurred_at",
        )
    }
    documents: list[EhrDocument] = []

    for row in _paginate(client, "clinical_progress_notes", "*", order="patient_id"):
        enc = encounters.get(row["encounter_id"])
        if not enc:
            continue
        documents.append(
            EhrDocument(
                patient_id=row["patient_id"],
                encounter_id=enc["encounter_id"],
                encounter_uuid=row["encounter_id"],
                encounter_date=_parse_dt(enc.get("occurred_at")),
                source_type="soap_note",
                text=row.get("soap_note") or "",
                metadata={
                    "encounter_type": row.get("encounter_type"),
                    "specialty_key": row.get("specialty_key"),
                    "encounter_index": row.get("encounter_index"),
                },
            )
        )

    panel_rows = _paginate(client, "lab_panels", "id, encounter_id, panel_name")
    panels = {p["id"]: p for p in panel_rows}
    for row in _paginate(client, "lab_results", "id, lab_panel_id, test_name, test_value"):
        panel = panels.get(row["lab_panel_id"])
        if not panel:
            continue
        enc = encounters.get(panel["encounter_id"])
        if not enc:
            continue
        text = f"{row['test_name']}: {row['test_value']}"
        documents.append(
            EhrDocument(
                patient_id=enc["patient_id"],
                encounter_id=enc["encounter_id"],
                encounter_uuid=panel["encounter_id"],
                encounter_date=_parse_dt(enc.get("occurred_at")),
                source_type="lab_result",
                text=text,
                metadata={"panel_name": panel.get("panel_name"), "test_name": row["test_name"]},
                lab_result_id=row["id"],
            )
        )

    for row in _paginate(client, "encounter_investigations", "id, encounter_id, investigation"):
        enc = encounters.get(row["encounter_id"])
        if not enc:
            continue
        documents.append(
            EhrDocument(
                patient_id=enc["patient_id"],
                encounter_id=enc["encounter_id"],
                encounter_uuid=row["encounter_id"],
                encounter_date=_parse_dt(enc.get("occurred_at")),
                source_type="investigation",
                text=row.get("investigation") or "",
                metadata={"encounter_type": enc.get("encounter_type")},
                investigation_id=row["id"],
            )
        )

    documents.sort(key=lambda d: (d.patient_id, d.encounter_date, d.source_type))
    return documents


def build_chunks(documents: list[EhrDocument], patient_names: set[str]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for doc in documents:
        cleaned = scrub_pii(doc.text.strip(), patient_names)
        if not cleaned:
            continue
        for index, piece in enumerate(chunk_text(cleaned)):
            meta = {
                **doc.metadata,
                "patient_id": doc.patient_id,
                "encounter_id": doc.encounter_id,
                "source_type": doc.source_type,
            }
            chunks.append(
                TextChunk(
                    patient_id=doc.patient_id,
                    encounter_id=doc.encounter_id,
                    encounter_uuid=doc.encounter_uuid,
                    encounter_date=doc.encounter_date,
                    source_type=doc.source_type,
                    chunk_index=index,
                    raw_text=piece,
                    metadata=meta,
                    lab_result_id=doc.lab_result_id,
                    investigation_id=doc.investigation_id,
                )
            )
    return chunks


def embed_texts(texts: list[str], model_name: str = EMBED_MODEL) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    vectors = model.encode(texts, batch_size=EMBED_BATCH, show_progress_bar=len(texts) > EMBED_BATCH)
    return [v.tolist() for v in vectors]


def upsert_chunks_pg(chunks: list[TextChunk], embeddings: list[list[float]]) -> int:
    import json

    import psycopg

    from app.db.connection import execute_batch, postgres_url

    url = postgres_url()
    if not url:
        raise RuntimeError("Set SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD for vector upserts")

    rows = []
    for chunk, vector in zip(chunks, embeddings, strict=True):
        rows.append(
            {
                "chunk_id": chunk_id_for(chunk),
                "patient_id": chunk.patient_id,
                "encounter_id": chunk.encounter_id,
                "encounter_uuid": chunk.encounter_uuid,
                "lab_result_id": chunk.lab_result_id,
                "investigation_id": chunk.investigation_id,
                "encounter_date": chunk.encounter_date.isoformat(),
                "chunk_index": chunk.chunk_index,
                "source_type": chunk.source_type,
                "raw_text": chunk.raw_text,
                "metadata": json.dumps(chunk.metadata),
                "embedding": f"[{','.join(str(v) for v in vector)}]" if vector else None,
            }
        )

    sql = """
        INSERT INTO patient_notes_embeddings (
            chunk_id, patient_id, encounter_id, encounter_uuid, lab_result_id, investigation_id,
            encounter_date, chunk_index, source_type, raw_text, metadata, embedding
        ) VALUES (
            %(chunk_id)s::uuid, %(patient_id)s, %(encounter_id)s, %(encounter_uuid)s::uuid,
            %(lab_result_id)s::uuid, %(investigation_id)s::uuid,
            %(encounter_date)s::timestamptz, %(chunk_index)s, %(source_type)s,
            %(raw_text)s, %(metadata)s::jsonb, %(embedding)s::vector
        )
        ON CONFLICT (patient_id, encounter_id, source_type, chunk_index) DO UPDATE SET
            raw_text = EXCLUDED.raw_text,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            encounter_date = EXCLUDED.encounter_date,
            encounter_uuid = EXCLUDED.encounter_uuid,
            lab_result_id = EXCLUDED.lab_result_id,
            investigation_id = EXCLUDED.investigation_id
    """

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            if os.getenv("INGEST_RESET", "").lower() in ("1", "true", "yes"):
                cur.execute("TRUNCATE TABLE patient_notes_embeddings")
            for start in range(0, len(rows), UPSERT_BATCH):
                execute_batch(cur, sql, rows[start : start + UPSERT_BATCH], page_size=UPSERT_BATCH)
        conn.commit()
    return len(rows)


def run_ingestion(client) -> dict[str, int]:
    from app.services.funnel import vector_store

    names = fetch_patient_names(client)
    documents = fetch_ehr_documents(client)
    chunks = build_chunks(documents, names)
    if not chunks:
        logger.warning("No EHR text found to ingest")
        return {"documents": 0, "chunks": 0, "upserted": 0}

    backend = vector_store.vector_backend()
    logger.info("Ingesting %s chunks from %s documents via %s backend", len(chunks), len(documents), backend)

    if vector_store.uses_pinecone():
        # Pinecone embeds server-side from the `text` field (the index's
        # embed.field_map is {"text": "text"}) — no local embedding call in
        # our code at all. Text/metadata still land in Postgres too
        # (embedding column stays NULL there) so FTS and text hydration by
        # chunk_id/encounter stay backend-agnostic.
        vector_store.ensure_pinecone_index()
        upserted_pg = upsert_chunks_pg(chunks, [None] * len(chunks))
        records = [
            {
                "_id": chunk_id_for(c),
                "text": c.raw_text,
                "patient_id": c.patient_id,
                "encounter_id": c.encounter_id,
                "source_type": c.source_type,
                "lab_result_id": c.lab_result_id or "",
                "investigation_id": c.investigation_id or "",
                "encounter_date": c.encounter_date.isoformat(),
            }
            for c in chunks
        ]
        upserted = vector_store.upsert_records(records)
        logger.info("Pinecone upserted=%s, Postgres text rows=%s", upserted, upserted_pg)
    else:
        texts = [c.raw_text for c in chunks]
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            embeddings.extend(embed_texts(texts[start : start + EMBED_BATCH]))
        upserted = upsert_chunks_pg(chunks, embeddings)

    return {"documents": len(documents), "chunks": len(chunks), "upserted": upserted}
