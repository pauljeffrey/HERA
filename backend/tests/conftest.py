"""Shared fixtures for database integration tests."""

from __future__ import annotations

import os

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv("../.env")
load_dotenv(".env")


def postgres_url() -> str | None:
    host = os.getenv("SUPABASE_DB_HOST") or os.getenv("LOCAL_DB_HOST")
    password = os.getenv("SUPABASE_DB_PASSWORD") or os.getenv("LOCAL_DB_PASSWORD")
    if not host or not password:
        return None
    user = os.getenv("SUPABASE_DB_USER") or os.getenv("LOCAL_DB_USER", "postgres")
    port = os.getenv("SUPABASE_DB_PORT") or os.getenv("LOCAL_DB_PORT", "5432")
    name = os.getenv("SUPABASE_DB_NAME") or os.getenv("LOCAL_DB_NAME", "postgres")
    sslmode = "require" if os.getenv("SUPABASE_DB_HOST") else "disable"
    return f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"


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
