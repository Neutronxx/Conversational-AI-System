from __future__ import annotations

import json
import os
from typing import AsyncGenerator, Dict, List

import httpx


Message = Dict[str, str]


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
# If backend runs in Docker, set OLLAMA_BASE_URL to the host, e.g.:
# http://host.docker.internal:11434 (Mac/Windows) or http://<host-ip>:11434 (Linux).
OLLAMA_CHAT_ENDPOINT = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")


def _messages_to_ollama(messages: List[Message]) -> List[Dict[str, str]]:
    """Convert to Ollama chat format: list of { role, content }."""
    out: List[Dict[str, str]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out


def _messages_to_prompt(messages: List[Message]) -> str:
    """Convert chat messages to a single prompt for /api/generate."""
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


async def _stream_from_chat(client: httpx.AsyncClient, messages: List[Message]) -> AsyncGenerator[str, None]:
    """Stream using POST /api/chat (messages array)."""
    async with client.stream(
        "POST",
        OLLAMA_CHAT_ENDPOINT,
        json={
            "model": OLLAMA_MODEL,
            "messages": _messages_to_ollama(messages),
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
            content = (data.get("message") or {}).get("content")
            if content:
                yield content


async def _stream_from_generate(client: httpx.AsyncClient, messages: List[Message]) -> AsyncGenerator[str, None]:
    """Stream using POST /api/generate (single prompt)."""
    prompt = _messages_to_prompt(messages)
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


async def stream_chat_completion(
    messages: List[Message],
) -> AsyncGenerator[str, None]:
    """Stream tokens from a local Ollama model. Tries /api/chat, then /api/generate on 404."""
    if not _messages_to_ollama(messages):
        return

    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async for chunk in _stream_from_chat(client, messages):
                yield chunk
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                async for chunk in _stream_from_generate(client, messages):
                    yield chunk
            else:
                raise


async def complete_chat(messages: List[Message]) -> str:
    """Non-streaming helper that joins all streamed chunks."""
    chunks: List[str] = []
    async for chunk in stream_chat_completion(messages):
        chunks.append(chunk)
    return "".join(chunks)

