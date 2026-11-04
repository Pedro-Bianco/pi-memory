"""HTTP server: local admin page at /, health, OpenAPI and status codes."""

import json
import re
import threading
import urllib.error
import urllib.request

import pytest

from pi_memory.servers.http import make_server
from tests.fakes import make_pm


@pytest.fixture
def base():
    server = make_server(make_pm(), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url) as response:
        return response.status, dict(response.headers), response.read().decode("utf-8")


def post(url, body: bytes):
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_admin_page_is_local_only(base):
    status, headers, html = get(base + "/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "pi-memory" in html and "/v1/" in html
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert "http://" not in html and "https://" not in html


def test_health_and_openapi(base):
    assert json.loads(get(base + "/v1/health")[2])["status"] == "ok"
    paths = json.loads(get(base + "/v1/openapi.json")[2])["paths"]
    assert "/v1/collections.delete" in paths and "/v1/stats" in paths


def test_status_codes(base):
    assert post(base + "/v1/stats", b'{"owner": "ana"}')[0] == 200
    assert post(base + "/v1/stats", b"isto nao e json")[0] == 400
    assert post(base + "/v1/stats", b"{}")[0] == 400
    assert post(base + "/v1/memories.get", b'{"owner": "ana", "memory_id": "x"}')[0] == 404
    assert post(base + "/v1/nada", b"{}")[0] == 404
    status, body = post(base + "/v1/collections.delete", b'{"owner": "ana", "name": "x"}')
    assert status == 404 and body["error"]["code"] == "not_found"


def test_token_protects_every_operation():
    server = make_server(make_pm(), port=0, token="segredo-de-teste")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = post(base + "/v1/stats", b'{"owner": "ana"}')
        assert status == 401 and body["error"]["code"] == "unauthorized"
        request = urllib.request.Request(base + "/v1/stats", data=b'{"owner": "ana"}', headers={
            "Content-Type": "application/json", "Authorization": "Bearer errado"})
        with pytest.raises(urllib.error.HTTPError) as info:
            urllib.request.urlopen(request)
        assert info.value.code == 401
        request.add_header("Authorization", "Bearer segredo-de-teste")
        with urllib.request.urlopen(request) as response:
            assert json.loads(response.read())["owner"] == "ana"
        assert get(base + "/v1/health")[0] == 200            # health stays open
        assert get(base + "/")[0] == 200                       # the page asks for the token
        with pytest.raises(urllib.error.HTTPError):
            get(base + "/v1/openapi.json")
    finally:
        server.shutdown()
        server.server_close()


def test_cli_refuses_to_listen_outside_without_token(monkeypatch):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    from pi_memory import cli

    monkeypatch.setattr(cli, "open_memory", lambda args: make_pm())
    monkeypatch.delenv("PI_MEMORY_TOKEN", raising=False)
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = cli.main(["serve-http", "--host", "0.0.0.0", "--port", "0"])
    assert code == 2 and "token" in json.loads(out.getvalue())["error"]["message"]
