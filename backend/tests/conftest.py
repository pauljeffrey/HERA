"""Shared fixtures for database integration tests."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from app.db.connection import postgres_url


@pytest.fixture(scope="session")
def db_url() -> str:
    url = postgres_url()
    if not url:
        pytest.skip("Set SUPABASE_DB_HOST + SUPABASE_DB_PASSWORD (or LOCAL_DB_*) to run search tests")
    return url


@pytest.fixture
def db_conn(db_url: str):
    with psycopg.connect(db_url) as conn:
        yield conn
