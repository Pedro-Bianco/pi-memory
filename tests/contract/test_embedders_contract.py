"""HTTP embedders against fake servers (httpx.MockTransport): request shape, output, errors."""

import json
import math

import httpx
import pytest

from pi_memory.engines.embedders.gemini import GeminiEmbedder
from pi_memory.engines.embedders.ollama import OllamaEmbedder
from pi_memory.engines.embedders.openai import OpenAIEmbedder
from pi_memory.errors import EngineAuthError, EngineResponseError

KEY = "chave-ficticia-0123456789"


def norm(v):
    return math.sqrt(sum(x * x for x in v))


class Server:
    """Records requests and answers with `reply(request_json) -> dict`."""

    def __init__(self, reply, status=200):
        self.reply, self.status, self.requests = reply, status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.requests.append((request, body))
        return httpx.Response(self.status, json=self.reply(body))

    @property
    def transport(self):
        return httpx.MockTransport(self)


def test_ollama_embedder_batches_and_normalizes():
    server = Server(lambda body: {"embeddings": [[3.0, 4.0] for _ in body["input"]]})
    emb = OllamaEmbedder("nomic-embed-text", transport=server.transport)
    vectors = emb.embed_documents(["a", "b"])
    request, body = server.requests[0]
    assert str(request.url) == "http://localhost:11434/api/embed"
    assert body["model"] == "nomic-embed-text"
    assert body["input"] == ["search_document: a", "search_document: b"]   # nomic prefixes
    assert vectors == [[0.6, 0.8], [0.6, 0.8]]
    emb.embed_query("q")
    assert server.requests[-1][1]["input"] == ["search_query: q"]
    assert emb.name == "ollama:nomic-embed-text" and emb.dimension == 2


def test_openai_embedder_custom_base_url_sorts_by_index(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    server = Server(lambda body: {"data": [{"index": 1, "embedding": [0.0, 2.0]},
                                           {"index": 0, "embedding": [2.0, 0.0]}]})
    emb = OpenAIEmbedder("modelo-x", base_url="http://localhost:11434/v1",
                         transport=server.transport)
    assert emb.embed_documents(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]
    request, body = server.requests[0]
    assert str(request.url) == "http://localhost:11434/v1/embeddings"
    assert "authorization" not in request.headers     # local server: no key needed
    assert body == {"model": "modelo-x", "input": ["a", "b"]}


def test_openai_embedder_needs_key_for_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(EngineAuthError, match="OPENAI_API_KEY"):
        OpenAIEmbedder("text-embedding-3-small")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    server = Server(lambda body: {"data": [{"index": 0, "embedding": [1.0]}]})
    OpenAIEmbedder("text-embedding-3-small", transport=server.transport).embed_query("x")
    assert server.requests[0][0].headers["authorization"] == f"Bearer {KEY}"


def test_gemini_embedder_task_types_and_key_header():
    server = Server(lambda body: {"embeddings": [{"values": [1.0, 1.0]} for _ in body["requests"]]})
    emb = GeminiEmbedder(api_key=KEY, transport=server.transport)
    vectors = emb.embed_documents(["a", "b", "c"])
    request, body = server.requests[0]
    assert str(request.url).endswith("/models/gemini-embedding-001:batchEmbedContents")
    assert KEY not in str(request.url) and request.headers["x-goog-api-key"] == KEY
    assert [r["taskType"] for r in body["requests"]] == ["RETRIEVAL_DOCUMENT"] * 3
    assert body["requests"][0]["content"]["parts"][0]["text"] == "a"
    assert all(abs(norm(v) - 1) < 1e-9 for v in vectors)
    emb.embed_query("q")
    assert server.requests[-1][1]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


def test_gemini_embedder_batches_of_100():
    server = Server(lambda body: {"embeddings": [{"values": [1.0]} for _ in body["requests"]]})
    emb = GeminiEmbedder(api_key=KEY, transport=server.transport)
    assert len(emb.embed_documents([str(i) for i in range(250)])) == 250
    assert [len(b["requests"]) for _, b in server.requests] == [100, 100, 50]


def test_wrong_count_is_an_engine_response_error():
    server = Server(lambda body: {"embeddings": [[1.0]]})
    emb = OllamaEmbedder("m", transport=server.transport)
    with pytest.raises(EngineResponseError, match="vetores"):
        emb.embed_documents(["a", "b"])


def test_bad_key_is_masked():
    server = Server(lambda body: {"error": f"invalid key {KEY}"}, status=403)
    emb = GeminiEmbedder(api_key=KEY, transport=server.transport)
    with pytest.raises(EngineAuthError) as info:
        emb.embed_query("x")
    assert KEY not in info.value.message and "GEMINI_API_KEY" in info.value.message
