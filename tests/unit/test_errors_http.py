import httpx
import pytest

from pi_memory.engines._http import HttpEngine, mask, resolve_key
from pi_memory.engines.llms.function import FunctionLLM
from pi_memory.engines.llms.ollama import OllamaLLM
from pi_memory.errors import (
    EngineAuthError,
    EngineResponseError,
    EngineTimeoutError,
    EngineUnavailableError,
    MissingExtraError,
    NotFoundError,
)

SECRET = "chave-ficticia-1234567890abcd"


def engine(handler, secret=None):
    return HttpEngine("o Motor Exemplo", 5, secret=secret, key_hint="MOTOR_API_KEY",
                      transport=httpx.MockTransport(handler))


def test_error_to_dict_shape():
    assert NotFoundError("não achei").to_dict() == {
        "error": {"code": "not_found", "message": "não achei"}}


def test_missing_extra_names_the_install_command():
    err = MissingExtraError("qdrant", "O banco Qdrant")
    assert err.code == "missing_extra"
    assert 'pip install "pi-memory[qdrant]' in err.message


def test_connect_error_becomes_unavailable_in_portuguese():
    def handler(request):
        raise httpx.ConnectError("recusado", request=request)
    expected = "não respondeu em http://x/y — ele está aberto"
    with pytest.raises(EngineUnavailableError, match=expected):
        engine(handler).post_json("http://x/y", {})


def test_timeout_becomes_engine_timeout():
    def handler(request):
        raise httpx.ReadTimeout("lento", request=request)
    with pytest.raises(EngineTimeoutError):
        engine(handler).post_json("http://x/y", {})


def test_401_is_auth_error_and_never_shows_the_key():
    def handler(request):
        return httpx.Response(401, text=f"bad key {SECRET}")
    with pytest.raises(EngineAuthError) as info:
        engine(handler, SECRET).post_json("http://x/y", {})
    assert SECRET not in info.value.message
    assert "MOTOR_API_KEY" in info.value.message


def test_500_body_is_masked():
    def handler(request):
        return httpx.Response(500, text=f"falhou com {SECRET}")
    with pytest.raises(EngineResponseError) as info:
        engine(handler, SECRET).post_json("http://x/y", {})
    assert SECRET not in info.value.message
    assert mask(SECRET) in info.value.message


def test_missing_api_key_names_env_var(monkeypatch):
    monkeypatch.delenv("MOTOR_API_KEY", raising=False)
    with pytest.raises(EngineAuthError, match="MOTOR_API_KEY"):
        resolve_key(None, "MOTOR_API_KEY", "O Motor Exemplo")
    monkeypatch.setenv("MOTOR_API_KEY", SECRET)
    assert resolve_key(None, "MOTOR_API_KEY", "O Motor Exemplo") == SECRET


def test_ollama_llm_sends_chat_and_reads_content():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"message": {"content": "FATO: algo"}})

    llm = OllamaLLM(model="modelo-exemplo", transport=httpx.MockTransport(handler))
    assert llm.complete("oi") == "FATO: algo"
    assert seen["url"].endswith("/api/chat")
    assert '"stream":false' in seen["body"].replace(" ", "")


def test_ollama_missing_model_says_how_to_pull():
    def handler(request):
        return httpx.Response(404, json={"error": "model 'modelo-exemplo' not found"})
    llm = OllamaLLM(model="modelo-exemplo", transport=httpx.MockTransport(handler))
    with pytest.raises(EngineResponseError, match="ollama pull modelo-exemplo"):
        llm.complete("oi")


def test_function_llm_wraps_errors_and_types():
    assert FunctionLLM(lambda p: p.upper()).complete("a") == "A"
    with pytest.raises(EngineResponseError, match="deve devolver texto"):
        FunctionLLM(lambda p: 3).complete("a")

    def broken(prompt):
        raise ValueError("quebrou")
    with pytest.raises(EngineResponseError, match="quebrou"):
        FunctionLLM(broken).complete("a")
