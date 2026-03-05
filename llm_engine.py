from __future__ import annotations

import json
import os
from typing import AsyncGenerator, Dict, List

import httpx


Message = Dict[str, str]


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Some Ollama installations don't expose /api/chat yet; /api/generate is
# supported more broadly, so we use that and build a plain-text prompt.
OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3")


def _messages_to_prompt(messages: List[Message]) -> str:
    """Convert chat-style messages into a single prompt string.

    This keeps the system prompt at the top, then alternates `User:` /
    `Assistant:` blocks so that generate-style models can follow the
    conversation without a native chat API.
    """
    parts: List[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not content:
            continue
        if role == "system":
            parts.append(f"System instructions:\n{content}\n")
        elif role == "assistant":
            parts.append(f"Assistant:\n{content}\n")
        else:
            parts.append(f"User:\n{content}\n")

    parts.append("Assistant:")
    return "\n".join(parts)


async def stream_chat_completion(
    messages: List[Message],
) -> AsyncGenerator[str, None]:
    """Stream tokens from a local Ollama model as plain text chunks."""
    prompt = _messages_to_prompt(messages)

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            OLLAMA_GENERATE_ENDPOINT,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                data = json.loads(line)

                if data.get("done"):
                    break

                content = data.get("response")

                if content:
                    yield content


async def complete_chat(messages: List[Message]) -> str:
    """Non-streaming helper that joins all streamed chunks."""
    chunks: List[str] = []
    async for chunk in stream_chat_completion(messages):
        chunks.append(chunk)
    return "".join(chunks)

