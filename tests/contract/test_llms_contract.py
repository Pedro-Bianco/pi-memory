"""HTTP language models against fake servers: text in, text out, errors translated."""

import httpx
import pytest

from pi_memory.engines.llms.anthropic import AnthropicLLM
from pi_memory.engines.llms.gemini import GeminiLLM
from pi_memory.engines.llms.openai import OpenAILLM
from pi_memory.errors import EngineAuthError, EngineResponseError, EngineTimeoutError
from tests.contract.test_embedders_contract import KEY, Server


def test_openai_llm_chat_completions():
    server = Server(lambda body: {"choices": [{"message": {"content": "FATO: x"}}]})
    llm = OpenAILLM("modelo-x", api_key=KEY, transport=server.transport)
    assert llm.complete("oi") == "FATO: x"
    request, body = server.requests[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert body["messages"] == [{"role": "user", "content": "oi"}]
    assert body["temperature"] == 0 and body["model"] == "modelo-x"


def test_openai_llm_local_server_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    server = Server(lambda body: {"choices": [{"message": {"content": "ok"}}]})
    llm = OpenAILLM("qwen2.5:14b", base_url="http://localhost:11434/v1/",
                    transport=server.transport)
    assert llm.complete("x") == "ok"
    assert str(server.requests[0][0].url) == "http://localhost:11434/v1/chat/completions"


def test_gemini_llm_generate_content():
    server = Server(lambda body: {"candidates": [{"content": {"parts": [{"text": "A"},
                                                                       {"text": "B"}]}}]})
    llm = GeminiLLM("gemini-3.5-flash", api_key=KEY, transport=server.transport)
    assert llm.complete("oi") == "AB"
    request, body = server.requests[0]
    assert str(request.url).endswith("/models/gemini-3.5-flash:generateContent")
    assert request.headers["x-goog-api-key"] == KEY and KEY not in str(request.url)
    assert body["contents"] == [{"role": "user", "parts": [{"text": "oi"}]}]
    assert body["generationConfig"]["temperature"] == 0


def test_gemini_blocked_answer_is_an_error():
    server = Server(lambda body: {"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(EngineResponseError, match="SAFETY"):
        GeminiLLM("gemini-3.5-flash", api_key=KEY, transport=server.transport).complete("x")


def test_anthropic_messages():
    server = Server(lambda body: {"content": [{"type": "text", "text": "DUPLICATE"}]})
    llm = AnthropicLLM("modelo-anthropic", api_key=KEY, transport=server.transport)
    assert llm.complete("oi") == "DUPLICATE"
    request, body = server.requests[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert body["max_tokens"] == 1024 and body["temperature"] == 0
    assert body["messages"] == [{"role": "user", "content": "oi"}]


def test_anthropic_missing_key_names_env_var(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(EngineAuthError, match="ANTHROPIC_API_KEY"):
        AnthropicLLM("modelo-anthropic")


def test_timeouts_are_translated():
    def handler(request):
        raise httpx.ReadTimeout("lento", request=request)
    llm = OpenAILLM("m", api_key=KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(EngineTimeoutError):
        llm.complete("x")


def test_unexpected_shape_is_an_engine_response_error():
    server = Server(lambda body: {"choices": []})
    with pytest.raises(EngineResponseError):
        OpenAILLM("m", api_key=KEY, transport=server.transport).complete("x")


def test_busy_answers_are_retried_then_explained():
    from pi_memory.engines._http import HttpEngine
    calls, waits = [], []

    def handler(request):
        calls.append(1)
        status = 503 if len(calls) < 3 else 200
        return httpx.Response(status, json={"ok": True})

    engine = HttpEngine("o Motor", transport=httpx.MockTransport(handler), sleep=waits.append)
    assert engine.post_json("http://x/y", {}) == {"ok": True}
    assert len(calls) == 3 and waits == [2.0, 5.0]

    always = HttpEngine("o Motor", sleep=waits.append,
                        transport=httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(EngineResponseError, match="limite de uso"):
        always.post_json("http://x/y", {})
