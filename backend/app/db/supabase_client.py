from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    if settings.database_mode != "supabase":
        raise RuntimeError("Supabase client requested but DATABASE_MODE is not supabase")
    return create_client(settings.supabase_url, settings.supabase_secret_key)
