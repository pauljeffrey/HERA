"""Direct psycopg connection for FTS / pgvector / raw SQL queries.

Single connector for both `DATABASE_MODE=local` and Supabase-direct-Postgres,
replacing the previous split between `services/postgres.py` (no retries) and
`db/db_connect.py` (local-only, with retries).
"""

from __future__ import annotations

import logging
import os
import socket
import time
from urllib.parse import urlparse

import psycopg

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = int(os.getenv("HERA_DB_CONNECT_TIMEOUT", "8"))


def _resolve_ipv4(hostname: str) -> str | None:
    """Docker's default network often can't route IPv6 egress even though the
    host machine can — DNS for *.supabase.co returns both A and AAAA records,
    and glibc/libpq will happily pick the unreachable AAAA one, hanging or
    failing with 'Network is unreachable'. Resolve an IPv4 address explicitly
    and pass it as `hostaddr` (libpq still uses `host` for TLS SNI)."""
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        return infos[0][4][0] if infos else None
    except OSError:
        return None


def postgres_url(settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()

    if settings.database_mode == "local" and settings.database_url:
        url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        if "sslmode=" not in url:
            url = f"{url}?sslmode=disable"
        return url

    host = os.getenv("SUPABASE_DB_HOST") or os.getenv("LOCAL_DB_HOST")
    password = os.getenv("SUPABASE_DB_PASSWORD") or os.getenv("LOCAL_DB_PASSWORD")
    user = os.getenv("SUPABASE_DB_USER") or os.getenv("LOCAL_DB_USER", "postgres")
    port = os.getenv("SUPABASE_DB_PORT") or os.getenv("LOCAL_DB_PORT", "5432")
    name = os.getenv("SUPABASE_DB_NAME") or os.getenv("LOCAL_DB_NAME", "postgres")
    if not host or not password:
        return None
    sslmode = "disable" if settings.database_mode == "local" else "require"
    return f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"


def connect(*, retries: int = 1) -> psycopg.Connection:
    """Connect to Postgres, retrying with exponential backoff when `retries > 1`."""
    url = postgres_url()
    if not url:
        raise RuntimeError("Postgres URL unavailable — set SUPABASE_DB_HOST/PASSWORD or DATABASE_MODE=local")

    connect_kwargs: dict = {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    explicit_hostaddr = os.getenv("SUPABASE_DB_HOSTADDR", "").strip()
    if explicit_hostaddr:
        connect_kwargs["hostaddr"] = explicit_hostaddr
    else:
        hostname = urlparse(url).hostname
        if hostname:
            ipv4 = _resolve_ipv4(hostname)
            if ipv4:
                connect_kwargs["hostaddr"] = ipv4

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return psycopg.connect(url, **connect_kwargs)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            delay = min(2**attempt, 30)
            logger.warning("Database connection failed (%s/%s): %s — retry in %ss", attempt, retries, exc, delay)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def execute_batch(cur, sql: str, rows: list[dict], *, page_size: int = 100) -> None:
    """psycopg3 has no `psycopg.extras.execute_batch` (that's a psycopg2-only
    helper) — `executemany` is the native equivalent, chunked to bound
    memory/roundtrip size on large ingests."""
    for start in range(0, len(rows), page_size):
        cur.executemany(sql, rows[start : start + page_size])
