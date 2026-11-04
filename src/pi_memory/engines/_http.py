"""HTTP calls to engines (Ollama and cloud APIs) with a timeout and errors translated into the
library's own exceptions. API keys never appear in messages or logs."""

from __future__ import annotations

import os
import time

import httpx

from pi_memory import config
from pi_memory.errors import (
    EngineAuthError,
    EngineResponseError,
    EngineTimeoutError,
    EngineUnavailableError,
)


def mask(secret: str | None) -> str:
    if not secret:
        return ""
    return f"{secret[:3]}…{secret[-4:]}" if len(secret) > 10 else "…"


def resolve_key(explicit: str | None, env_var: str, engine: str) -> str:
    key = explicit or os.environ.get(env_var)
    if not key:
        raise EngineAuthError(
            f"{engine}: chave de API ausente. Passe api_key=... ou defina a variável de ambiente "
            f"{env_var}."
        )
    return key


# 429 (quota per minute) and 503 (high demand) came back from the Gemini free tier on
# 2026-11-04 and pass after a few seconds; other errors are not retried.
RETRY_STATUS = (429, 503)
RETRY_WAITS = (2.0, 5.0)


class HttpEngine:
    """engine: name shown in messages ("o Ollama", "a API da OpenAI")."""

    def __init__(self, engine: str, timeout: float = config.TIMEOUT_S,
                 secret: str | None = None, key_hint: str = "",
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.engine = engine
        self.secret = secret
        self.key_hint = key_hint
        self._sleep = sleep
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _clean(self, text: str) -> str:
        return text.replace(self.secret, mask(self.secret)) if self.secret else text

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        for wait in (*RETRY_WAITS, None):
            response = self._post(url, payload, headers)
            if response.status_code not in RETRY_STATUS or wait is None:
                break
            self._sleep(wait)
        if response.status_code == 429:
            raise EngineResponseError(
                f"{self.engine} recusou por limite de uso (429), mesmo depois de esperar. "
                "Tente mais tarde ou confira a cota do seu plano."
            )
        return self._read(response)

    def _post(self, url: str, payload: dict, headers: dict | None) -> httpx.Response:
        try:
            return self._client.post(url, json=payload, headers=headers or {})
        except httpx.TimeoutException:
            raise EngineTimeoutError(
                f"{self.engine} não respondeu a tempo em {url}. Aumente o timeout ou verifique "
                "se ele está sobrecarregado."
            ) from None
        except httpx.HTTPError:
            raise EngineUnavailableError(
                f"{self.engine} não respondeu em {url} — ele está aberto?"
            ) from None

    def _read(self, response: httpx.Response) -> dict:
        if response.status_code in (401, 403):
            hint = f" Confira {self.key_hint}." if self.key_hint else ""
            raise EngineAuthError(f"{self.engine} recusou a chave de API.{hint}")
        if response.status_code >= 400:
            detail = self._clean(response.text[:300])
            raise EngineResponseError(
                f"{self.engine} devolveu erro {response.status_code}: {detail}"
            )
        try:
            return response.json()
        except ValueError:
            raise EngineResponseError(
                f"{self.engine} devolveu uma resposta que não é JSON."
            ) from None

    def close(self) -> None:
        self._client.close()
