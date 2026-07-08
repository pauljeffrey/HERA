"""Redis-backed store for agent chat history and pipeline intermediate state."""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from redis.asyncio import Redis, from_url

from app.config import get_settings

CHAT_KEY_PREFIX = "hera:chat:"
TRACE_KEY_PREFIX = "hera:trace:"
TASK_STATE_KEY_PREFIX = "hera:task:"

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        # Explicit timeouts matter here: on Windows, connecting to "localhost"
        # tries the IPv6 loopback first and can take a very long time to fall
        # back to IPv4 if nothing is listening — an unreachable Redis should
        # fail in seconds, not hang the whole request for minutes.
        _client = from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def load_chat_history(conversation_id: str) -> list[ModelMessage] | None:
    """Load prior turns for a conversation in pydantic_ai's message_history format."""
    raw = await get_redis().get(f"{CHAT_KEY_PREFIX}{conversation_id}")
    if not raw:
        return None
    return ModelMessagesTypeAdapter.validate_json(raw)


async def save_chat_history(
    conversation_id: str,
    messages: list[ModelMessage],
    *,
    ttl_seconds: int | None = None,
) -> None:
    """Persist the full run transcript (result.all_messages()) for a conversation."""
    settings = get_settings()
    payload = ModelMessagesTypeAdapter.dump_json(messages)
    await get_redis().set(
        f"{CHAT_KEY_PREFIX}{conversation_id}",
        payload,
        ex=ttl_seconds or settings.redis_chat_ttl_seconds,
    )


async def delete_chat_history(conversation_id: str) -> None:
    await get_redis().delete(f"{CHAT_KEY_PREFIX}{conversation_id}")


async def save_agent_trace(
    trace_id: str,
    messages: list[ModelMessage],
    *,
    ttl_seconds: int | None = None,
) -> None:
    """Write-only log of a single agent run (tool calls, reasoning, output) for audit/debug."""
    settings = get_settings()
    payload = ModelMessagesTypeAdapter.dump_json(messages)
    await get_redis().set(
        f"{TRACE_KEY_PREFIX}{trace_id}",
        payload,
        ex=ttl_seconds or settings.redis_task_ttl_seconds,
    )


async def set_task_state(task_id: str, **fields: Any) -> None:
    """Cache trial-matching task fields (status, progress, result_summary, ...) as they change."""
    if not fields:
        return
    settings = get_settings()
    key = f"{TASK_STATE_KEY_PREFIX}{task_id}"
    client = get_redis()
    encoded = {name: json.dumps(value, default=str) for name, value in fields.items()}
    await client.hset(key, mapping=encoded)
    await client.expire(key, settings.redis_task_ttl_seconds)


async def get_task_state(task_id: str) -> dict[str, Any] | None:
    raw = await get_redis().hgetall(f"{TASK_STATE_KEY_PREFIX}{task_id}")
    if not raw:
        return None
    return {name: json.loads(value) for name, value in raw.items()}


async def delete_task_state(task_id: str) -> None:
    await get_redis().delete(f"{TASK_STATE_KEY_PREFIX}{task_id}")
