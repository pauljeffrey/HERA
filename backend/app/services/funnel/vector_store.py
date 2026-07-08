"""Pluggable vector backend — Pinecone (default, integrated hosted embeddings)
or pgvector (local embedding model).

`VECTOR_BACKEND=pinecone` (default): the Pinecone index has a model attached
(`create_index_for_model`), so both ingestion and query embed server-side —
no local embedding model download, no `client.inference.embed` call in our
code at all. We just upsert/search raw text records
(`index.upsert_records` / `index.search`), each carrying a `text` field
(the index's `embed.field_map` is `{"text": "text"}`) plus `patient_id`,
`encounter_id`, `source_type`, `lab_result_id`, `investigation_id` as
metadata fields. Row text still lives in Postgres
`patient_notes_embeddings` too (that's what `services.funnel.search.
fetch_chunk_text`/`fetch_encounter_text` read) so FTS and lazy text
hydration stay backend-agnostic.

`VECTOR_BACKEND=pgvector`: embeddings are generated locally via
`sentence-transformers` (see `services.clinical.ehr_ingest.embed_texts`) and
stored directly in the `patient_notes_embeddings.embedding` column.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger(__name__)


def vector_backend() -> str:
    return get_settings().vector_backend.strip().lower()


def uses_pinecone() -> bool:
    return vector_backend() == "pinecone"


def embed_texts(texts: list[str]) -> list[list[float]]:
    """pgvector path only — local sentence-transformers embedding. Pinecone
    embeds server-side (see `search_records`/`upsert_records`) and never
    calls this."""
    from app.services.clinical.ehr_ingest import embed_texts as embed_texts_local

    return embed_texts_local(texts)


@lru_cache
def _pinecone_client():
    from pinecone import Pinecone

    settings = get_settings()
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is required when VECTOR_BACKEND=pinecone")
    return Pinecone(api_key=settings.pinecone_api_key)


def ensure_pinecone_index() -> None:
    """Idempotently create the integrated-inference index if it doesn't exist yet.
    Call this once before ingesting (the ingestion script does this automatically)."""
    settings = get_settings()
    client = _pinecone_client()
    if client.has_index(settings.pinecone_index):
        return
    logger.info(
        "Creating Pinecone index %s (model=%s, cloud=%s, region=%s)",
        settings.pinecone_index,
        settings.pinecone_embed_model,
        settings.pinecone_cloud,
        settings.pinecone_region,
    )
    client.create_index_for_model(
        name=settings.pinecone_index,
        cloud=settings.pinecone_cloud,
        region=settings.pinecone_region,
        embed={"model": settings.pinecone_embed_model, "field_map": {"text": "text"}},
    )


@lru_cache
def _pinecone_index():
    settings = get_settings()
    client = _pinecone_client()
    host = settings.pinecone_index_host or client.describe_index(settings.pinecone_index).host
    return client.Index(host=host)


def upsert_records(records: list[dict]) -> int:
    """Upsert raw-text records into Pinecone. Each record must have `_id`,
    `text`, and any metadata fields (patient_id, encounter_id,
    source_type, lab_result_id, investigation_id, encounter_date). No-op for
    pgvector — that path writes the `embedding` column directly via
    `ehr_ingest.upsert_chunks_pg`."""
    if not uses_pinecone() or not records:
        return 0
    index = _pinecone_index()
    namespace = get_settings().pinecone_namespace
    batch_size = 96  # Pinecone's upsert_records batch limit
    upserted = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        index.upsert_records(records=batch, namespace=namespace)
        upserted += len(batch)
        logger.info("Upserted %s/%s records into Pinecone index", upserted, len(records))
    return upserted


def search_records(query_text: str, *, top_k: int = 400, patient_ids: list[str] | None = None) -> list[dict]:
    """Server-side embedded semantic search. Returns hit dicts with
    `chunk_id`, `score`, and whatever metadata fields were requested."""
    if not uses_pinecone():
        raise RuntimeError("search_records is only used for the pinecone backend")
    index = _pinecone_index()
    namespace = get_settings().pinecone_namespace
    filter_ = {"patient_id": {"$in": patient_ids}} if patient_ids else None
    response = index.search(
        namespace=namespace,
        inputs={"text": query_text},
        top_k=top_k,
        filter=filter_,
        fields=["patient_id", "encounter_id", "source_type", "encounter_date"],
    )
    return [
        {
            "chunk_id": hit.id,
            "score": hit.score,
            "patient_id": hit.fields.get("patient_id"),
            "encounter_id": hit.fields.get("encounter_id"),
            "source_type": hit.fields.get("source_type"),
            "encounter_date": hit.fields.get("encounter_date"),
        }
        for hit in response.result.hits
    ]
