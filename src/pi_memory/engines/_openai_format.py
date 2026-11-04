"""Shared by the OpenAI-format engines: the official API needs a key; a compatible local server
(Ollama /v1, LM Studio) usually does not."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from pi_memory.engines._http import resolve_key

OPENAI_URL = "https://api.openai.com/v1"
ENV = "OPENAI_API_KEY"


def resolve(base_url: str, key: str | None) -> tuple[str, str | None, dict]:
    """(base url without trailing slash, key or None, headers)."""
    base = base_url.rstrip("/")
    if urlparse(base).hostname == "api.openai.com":
        key = resolve_key(key, ENV, "A API da OpenAI")
    else:
        key = key or os.environ.get(ENV) or None
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return base, key, headers


def engine_name(base: str) -> str:
    if urlparse(base).hostname == "api.openai.com":
        return "a API da OpenAI"
    return f"o servidor {base}"
