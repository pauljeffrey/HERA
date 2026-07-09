from __future__ import annotations

import os

from pydantic_ai import InlineDefsJsonSchemaTransformer
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
_DEFAULT_OR_SETTINGS = OpenRouterModelSettings(
    openrouter_cache_instructions=True,
    openrouter_cache_messages=True,
    openrouter_cache_tool_definitions=True,
)


def _openrouter_model(model_name: str, api_key: str) -> OpenRouterModel:
    if not api_key:
        raise ValueError("OpenRouter models require MODEL_API_KEY or OPENROUTER_API_KEY")
    return OpenRouterModel(
        model_name,
        provider=OpenRouterProvider(api_key=api_key),
        settings=_DEFAULT_OR_SETTINGS,
    )


def select_model(model_name: str, model_api_key: str):
    """Route to the right provider from MODEL_NAME.

    - ``provider/model`` (contains ``/``) → OpenRouter
    - ``gemini`` → Google
    - ``claude`` / ``anthropic`` → Anthropic
    - ``gpt`` / ``openai`` → OpenAI
    - anything else → OpenRouter fallback (covers unknown slugs on OR)
    """
    name = (model_name or os.getenv("MODEL_NAME") or _DEFAULT_MODEL).strip()
    lowered = name.lower()
    openrouter_key = model_api_key or os.getenv("OPENROUTER_API_KEY", "")
    openai_key = model_api_key or os.getenv("OPENAI_API_KEY", "")
    google_key = model_api_key or os.getenv("GOOGLE_API_KEY", "")

    if "/" in name:
        return _openrouter_model(name, openrouter_key)
    if "gemini" in lowered:
        if not google_key:
            raise ValueError("Gemini models require MODEL_API_KEY or GOOGLE_API_KEY")
        return GoogleModel(name, provider=GoogleProvider(api_key=google_key))
    if "claude" in lowered or "anthropic" in lowered:
        if not model_api_key:
            raise ValueError("Anthropic models require MODEL_API_KEY")
        return AnthropicModel(name, provider=AnthropicProvider(api_key=model_api_key))
    if "gpt" in lowered or "openai" in lowered:
        if not openai_key:
            raise ValueError("OpenAI models require MODEL_API_KEY or OPENAI_API_KEY")
        return OpenAIChatModel(name, provider=OpenAIProvider(api_key=openai_key))
    return _openrouter_model(name, openrouter_key)


def select_vllm_model(model_name: str, *, base_url: str, api_key: str = "not-needed"):
    """An OpenAI-compatible model pointed at a self-hosted vLLM server (e.g.
    the Modal deployment in `workers/modal_app.py`). vLLM's OpenAI-compatible
    server doesn't support every OpenAI Chat Completions extension, so the
    profile disables the ones that trip it up (strict tool schemas, multiple
    system messages, `max_completion_tokens`)."""
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        profile=OpenAIModelProfile(
            json_schema_transformer=InlineDefsJsonSchemaTransformer,
            openai_supports_strict_tool_definition=False,
            openai_chat_supports_multiple_system_messages=False,
            openai_chat_supports_max_completion_tokens=False,
        ),
    )
