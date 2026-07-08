"""Environment helpers for OpenAI-backed pipelines."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str
    model: str


def load_openai_settings(*, model: str | None = None) -> OpenAISettings:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("MODEL_API_KEY")
    if not api_key:
        raise ValueError("Set OPENAI_API_KEY or MODEL_API_KEY in the environment.")
    return OpenAISettings(
        api_key=api_key,
        model=model or os.getenv("MODEL_NAME", "gpt-4o-mini"),
    )


def default_output_dir(env_var: str, fallback: Path) -> Path:
    return Path(os.getenv(env_var, fallback))
