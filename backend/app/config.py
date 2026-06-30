from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HERA"
    debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite+aiosqlite:///./hera.db"
    redis_url: str = "redis://:redispassword@localhost:6380/0"

    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"

    mock_mode: bool = True
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    presidio_enabled: bool = True
    token_cost_per_1k_input: float = 0.00015
    token_cost_per_1k_output: float = 0.0006


@lru_cache
def get_settings() -> Settings:
    return Settings()
