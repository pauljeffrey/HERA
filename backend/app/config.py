from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hera_io.datasets import load_json_list

_REPO_ROOT = Path(os.getenv("HERA_REPO_ROOT", Path(__file__).resolve().parents[2]))
_APP_ROOT = Path(__file__).resolve().parent
_DATA_ROOT = _APP_ROOT / "data"
CRITERIA_CACHE = _DATA_ROOT / "criteria_prompts.json"
CRITERIA_COUNTS_CACHE = _DATA_ROOT / "criteria_counts.json"
SCHEMA_SQL = _APP_ROOT / "db" / "schema.sql"


def trajectories_path(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    if cfg.patient_trajectories_path:
        return Path(cfg.patient_trajectories_path)
    return _REPO_ROOT / "clinical_data_gen" / "structured_clinical_data" / "output" / "patient_trajectories.json"


def soap_notes_path(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    if cfg.soap_notes_path:
        return Path(cfg.soap_notes_path)
    return _REPO_ROOT / "clinical_data_gen" / "soap_notes" / "output" / "soap_progress_notes.json"


def generate_postgres_url(*, user: str, password: str, host: str, port: int, name: str) -> str:
    return (
        f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}"
    )


def _build_redis_url() -> str:
    """Build REDIS_URL from REDIS_SERVER_HOST/PORT/PASSWORD (e.g. a Dokploy-
    managed Redis service) when set; falls back to a local default."""
    host = os.getenv("REDIS_SERVER_HOST")
    if not host:
        return "redis://localhost:6379/0"
    port = os.getenv("REDIS_SERVER_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "")
    auth = f":{quote_plus(password)}@" if password else ""
    return f"redis://{auth}{host}:{port}/0"


_VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "pinecone").strip().lower()
_VS_MIN_DEFAULT = "0.35" if _VECTOR_BACKEND == "pinecone" else "0.72"
_VS_MERGE_DEFAULT = "0.42" if _VECTOR_BACKEND == "pinecone" else "0.90"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HERA"
    debug: bool = True
    api_prefix: str = "/api/v1"

    database_mode: Literal["supabase", "local"] = os.getenv("DATABASE_MODE", "supabase")
    database_url: str = os.getenv("DATABASE_URL", "")

    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_secret_key: str = os.getenv("SUPABASE_SECRET_KEY", "")

    local_db_host: str = os.getenv("LOCAL_DB_HOST", "localhost")
    local_db_port: int = int(os.getenv("LOCAL_DB_PORT", "5432"))
    local_db_user: str = os.getenv("LOCAL_DB_USER", "postgres")
    local_db_password: str = os.getenv("LOCAL_DB_PASSWORD", "postgres")
    local_db_name: str = os.getenv("LOCAL_DB_NAME", "hera")

    prepopulate_db: str = os.getenv("PREPOPULATE_DB", "")
    patient_trajectories_path: str = os.getenv("PATIENT_TRAJECTORIES_PATH", "")
    soap_notes_path: str = os.getenv("SOAP_NOTES_PATH","")

    cors_origins: list[str] = ["*"]

    model_name: str = os.getenv("MODEL_NAME", "meta-llama/llama-3.3-70b-instruct:free")
    model_api_key: str = os.getenv("MODEL_API_KEY", "")

    n_final_candidates: int = int(os.getenv("N_FINAL_CANDIDATES", "15"))
    tier3_patient_cap: int = int(os.getenv("TIER3_PATIENT_CAP", "20"))
    fts_top_k: int = int(os.getenv("FTS_TOP_K", "10"))
    semantic_top_k: int = int(os.getenv("SEMANTIC_TOP_K", "10"))
    vs_min_similarity: float = float(os.getenv("VS_MIN_SIMILARITY", _VS_MIN_DEFAULT))
    vs_merge_score_threshold: float = float(os.getenv("VS_MERGE_SCORE_THRESHOLD", _VS_MERGE_DEFAULT))

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8010")

    # Tier 3 eligibility engine: "api" (default cloud model via MODEL_NAME) |
    # "modal" (self-hosted vLLM behind an OpenAI-compatible endpoint, see
    # workers/modal_app.py)
    tier3_engine: str = os.getenv("HERA_TIER3_ENGINE", "api")
    modal_vllm_base_url: str = os.getenv("MODAL_VLLM_BASE_URL", "")
    modal_vllm_api_key: str = os.getenv("MODAL_VLLM_API_KEY", "not-needed")
    modal_vllm_model: str = os.getenv("MODAL_VLLM_MODEL", "google/gemma-3-4b-it")

    vector_backend: str = os.getenv("VECTOR_BACKEND", "pinecone")
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_index: str = os.getenv("PINECONE_INDEX", "hera")
    pinecone_index_host: str = os.getenv("PINECONE_INDEX_HOST", "")
    pinecone_namespace: str = os.getenv("PINECONE_NAMESPACE", "clinical-notes")
    pinecone_embed_model: str = os.getenv("PINECONE_MODEL", "multilingual-e5-large")
    pinecone_cloud: str = os.getenv("PINECONE_CLOUD", "aws")
    pinecone_region: str = os.getenv("PINECONE_REGION", "us-east-1")

    redis_url: str = os.getenv("REDIS_URL") or _build_redis_url()
    redis_chat_ttl_seconds: int = int(os.getenv("REDIS_CHAT_TTL_SECONDS", str(60 * 60 * 24)))
    redis_task_ttl_seconds: int = int(os.getenv("REDIS_TASK_TTL_SECONDS", str(60 * 60 * 24 * 3)))

    @model_validator(mode="after")
    def configure_database(self) -> Settings:
        if self.database_mode == "local":
            self.database_url = generate_postgres_url(
                user=self.local_db_user,
                password=self.local_db_password,
                host=self.local_db_host,
                port=self.local_db_port,
                name=self.local_db_name,
            )
        elif not self.supabase_url or not self.supabase_secret_key:
            raise ValueError(
                "DATABASE_MODE=supabase requires SUPABASE_URL and SUPABASE_SECRET_KEY"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()