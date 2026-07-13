"""Server-sent event helpers for mimicked LLM streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator


def chunk_text(text: str, size: int = 28) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]


async def sse_payloads(events: AsyncIterator[dict]) -> AsyncIterator[str]:
    async for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
