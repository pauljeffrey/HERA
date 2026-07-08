from __future__ import annotations

from pydantic_ai import InlineDefsJsonSchemaTransformer
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider


def select_model(model_name: str, model_api_key: str):
    lowered = model_name.lower()
    if "gpt" in lowered or "openai" in lowered:
        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=model_api_key))
    if "gemini" in lowered:
        return GoogleModel(model_name, provider=GoogleProvider(api_key=model_api_key))
    if "claude" in lowered or "anthropic" in lowered:
        return AnthropicModel(model_name, provider=AnthropicProvider(api_key=model_api_key))
    raise ValueError(f"Unsupported model: {model_name}")


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
