#!/usr/bin/env python3
"""Offline Step 0: chunk EHR records and index them for the active vector backend.

Usage (from backend/):
  python -m scripts.ingest_ehr
  python -m scripts.ingest_ehr --reset

With VECTOR_BACKEND=pinecone (the default — see .env), embeddings are
generated server-side by Pinecone; nothing extra to install. Only the
VECTOR_BACKEND=pgvector path needs a local embedding model:
  pip install -r requirements-ingest.txt
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT.parent / ".env")

from app.config import get_settings
from app.db.supabase_client import get_supabase_client
from app.services.clinical.ehr_ingest import run_ingestion

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest EHR text into patient_notes_embeddings")
    parser.add_argument("--reset", action="store_true", help="Truncate embeddings table before insert")
    args = parser.parse_args()

    if args.reset:
        os.environ["INGEST_RESET"] = "1"

    settings = get_settings()
    if settings.database_mode != "supabase":
        logger.error("Ingestion expects DATABASE_MODE=supabase")
        sys.exit(1)

    client = get_supabase_client()
    stats = run_ingestion(client)
    logger.info(
        "Ingestion complete: documents=%s chunks=%s upserted=%s",
        stats["documents"],
        stats["chunks"],
        stats["upserted"],
    )


if __name__ == "__main__":
    main()
