"""Attacks on the local servers and on the command line (docs/GUIA.md, section 11.9; SECURITY.md).

- another site open in the browser sending operations to http://127.0.0.1 (CSRF);
- a site whose name starts pointing to 127.0.0.1 reading the answers (DNS rebinding);
- a caller of HTTP or MCP making documents.add read files of this machine by path;
- a broken Content-Length holding a connection forever;
- command line: short or visible token, missing files, unknown folders."""

import base64
import importlib.util
import json
import os
import socket
import threading
import urllib.error
import urllib.request

import pytest

from pi_memory import cli
from pi_memory.operations import allowed_path, dispatch
from pi_memory.servers.http import make_server
from tests.fakes import make_pm
from tests.unit.test_cli import run

TOKEN = "token-de-teste-com-32-caracteres"


@pytest.fixture
def secret(tmp_path):
    """A private file outside any allowed folder, and an allowed folder with a public one."""
    private = tmp_path / "privado" / "senhas.txt"
    private.parent.mkdir()
    private.write_text("SENHA=ficticia-123", encoding="utf-8")
    public = tmp_path / "publico" / "manual.txt"
    public.parent.mkdir()
    public.write_text("O manual do produto Exemplo.", encoding="utf-8")
    return {"private": private, "public": public, "docs": public.parent}


def serve(pm=None, **options):
    pm = pm or make_pm()
    server = make_server(pm, port=0, **options)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}", pm


def stop(server):
    server.shutdown()
    server.server_close()


def call(url, body=None, headers=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


JSON = {"Content-Type": "application/json"}


# ── CSRF: only application/json is accepted ─────────────────────────────────────────────────
@pytest.mark.parametrize("kind", [None, "text/plain", "application/x-www-form-urlencoded",
                                  "multipart/form-data; boundary=x"])
def test_simple_browser_requests_are_refused(kind):
    server, base, pm = serve()
    pm.memories.remember("O usuário tem uma gata", owner="ana", topic="animais")
    try:
        headers = {"Content-Type": kind} if kind else {}
        status, body = call(base + "/v1/memories.delete_all", {"owner": "ana"}, headers)
        assert status == 415 and json.loads(body)["error"]["code"] == "invalid_input"
        assert pm.memories.list(owner="ana")["total"] == 1          # nothing was deleted
        status, _ = call(base + "/v1/stats", {"owner": "ana"},
                         {"Content-Type": "application/json; charset=utf-8"})
        assert status == 200
    finally:
        stop(server)


# ── DNS rebinding: without a token, only a local Host ───────────────────────────────────────
def test_foreign_host_is_refused_without_token():
    server, base, pm = serve()
    pm.memories.remember("O usuário tem uma gata", owner="ana", topic="animais")
    port = server.server_address[1]
    try:
        for host in ("atacante.exemplo", f"atacante.exemplo:{port}", "127.0.0.1.exemplo",
                     "localhost.exemplo:80"):
            status, body = call(base + "/v1/memories.list", {"owner": "ana"},
                                {**JSON, "Host": host})
            assert status == 403 and "gata" not in body, host
            assert call(base + "/", headers={"Host": host})[0] == 403
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", "LOCALHOST", f"[::1]:{port}"):
            assert call(base + "/v1/memories.list", {"owner": "ana"},
                        {**JSON, "Host": host})[0] == 200, host
    finally:
        stop(server)


def test_with_token_any_host_but_token_required():
    """Behind a proxy with a real name the token is the protection (a browser cannot add it)."""
    server, base, _ = serve(token=TOKEN)
    try:
        headers = {**JSON, "Host": "memoria.exemplo"}
        assert call(base + "/v1/stats", {"owner": "ana"}, headers)[0] == 401
        assert call(base + "/v1/stats", {"owner": "ana"},
                    {**headers, "Authorization": f"Bearer {TOKEN}"})[0] == 200
    finally:
        stop(server)


# ── broken Content-Length ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("length", [b"-1", b"abc", b"1e3", b" -5 "])
def test_bad_content_length_answers_at_once(length):
    server, _, _ = serve()
    try:
        with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5) as c:
            c.sendall(b"POST /v1/stats HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                      b"Content-Type: application/json\r\nContent-Length: " + length +
                      b"\r\n\r\n{}")
            assert c.recv(100).startswith(b"HTTP/1.0 400")
    finally:
        stop(server)


# ── documents.add by path ───────────────────────────────────────────────────────────────────
def test_http_does_not_read_paths_by_default(secret):
    server, base, pm = serve()
    try:
        status, body = call(base + "/v1/documents.add",
                            {"owner": "x", "path": str(secret["private"])}, JSON)
        assert status == 400 and "content_base64" in json.loads(body)["error"]["message"]
        assert pm.documents.list(owner="x")["documents"] == []
        content = base64.b64encode(b"# Nota\n\nTexto enviado.").decode()
        assert call(base + "/v1/documents.add", {"owner": "x", "filename": "nota.md",
                                                 "content_base64": content}, JSON)[0] == 200
    finally:
        stop(server)


def test_http_docs_dir_allows_only_that_folder(secret):
    server, base, pm = serve(docs_dir=secret["docs"])
    try:
        ok = call(base + "/v1/documents.add", {"owner": "x", "path": "manual.txt"}, JSON)
        assert ok[0] == 200, ok
        for attempt in (str(secret["private"]), "../privado/senhas.txt",
                        str(secret["docs"] / ".." / "privado" / "senhas.txt")):
            status, body = call(base + "/v1/documents.add", {"owner": "x", "path": attempt},
                                JSON)
            assert status == 400 and "pasta liberada" in body, attempt
        assert [d["source"] for d in pm.documents.list(owner="x")["documents"]] == ["manual.txt"]
    finally:
        stop(server)


def test_allowed_path_rules(secret, tmp_path):
    docs = secret["docs"]
    assert allowed_path(str(secret["private"]), True) == str(secret["private"])
    assert allowed_path("manual.txt", docs) == str((docs / "manual.txt").resolve())
    with pytest.raises(Exception, match="não lê arquivos"):
        allowed_path("manual.txt", False)
    with pytest.raises(Exception, match="pasta liberada"):
        allowed_path(str(tmp_path / "publico-falso" / "x.txt"), docs)   # same prefix, not inside
    link = docs / "atalho.txt"
    try:
        os.symlink(secret["private"], link)
    except (OSError, NotImplementedError):
        pytest.skip("sem permissão para criar links neste sistema")
    with pytest.raises(Exception, match="pasta liberada"):
        allowed_path("atalho.txt", docs)


def test_dispatch_refuses_paths_unless_told(secret):
    pm = make_pm()
    params = {"owner": "x", "path": str(secret["public"])}
    assert dispatch(pm, "documents.add", params)["error"]["code"] == "invalid_input"
    assert dispatch(pm, "documents.add", params, files=True)["status"] == "added"


@pytest.mark.skipif(not importlib.util.find_spec("mcp"), reason="extra mcp não instalado")
def test_mcp_does_not_read_paths_by_default(secret):
    from tests.transports import via_mcp

    pm = make_pm()
    refused = via_mcp(pm, [("documents.add", {"owner": "x", "path": str(secret["private"])})])
    assert refused[0]["error"]["code"] == "invalid_input"

    import anyio
    from mcp.client import Client

    from pi_memory.servers.mcp import make_server as make_mcp

    async def allowed():
        async with Client(make_mcp(pm, docs_dir=secret["docs"])) as client:
            answer = await client.call_tool("documents_add", {"owner": "x", "path": "manual.txt"})
            return json.loads(answer.content[0].text)

    assert anyio.run(allowed)["status"] == "added"
    assert [d["source"] for d in pm.documents.list(owner="x")["documents"]] == ["manual.txt"]


# ── command line ────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli_pm(monkeypatch):
    instance = make_pm()
    instance.close = lambda: None
    monkeypatch.setattr(cli, "open_memory", lambda args: instance)
    return instance


def test_cli_reads_the_users_own_files(cli_pm, secret):
    code, out, _ = run("documents", "add", "--owner", "ana", "--path", str(secret["public"]))
    assert code == 0 and json.loads(out)["status"] == "added"


def test_cli_refuses_short_token(cli_pm, monkeypatch):
    monkeypatch.delenv("PI_MEMORY_TOKEN", raising=False)
    code, out, _ = run("serve-http", "--token", "1234")
    assert code == 2 and "curto" in json.loads(out)["error"]["message"]
    monkeypatch.setenv("PI_MEMORY_TOKEN", "abc")
    code, out, _ = run("serve-http")
    assert code == 2 and "curto" in json.loads(out)["error"]["message"]


def test_cli_warns_about_token_typed_on_the_command_line(cli_pm, monkeypatch):
    started = []
    monkeypatch.setattr("pi_memory.servers.http.make_server",
                        lambda *a, **k: started.append((a, k)) or _NoServer())
    code, _, err = run("serve-http", "--token", TOKEN)
    assert code == 0 and "PI_MEMORY_TOKEN" in err and started
    monkeypatch.setenv("PI_MEMORY_TOKEN", TOKEN)
    code, _, err = run("serve-http")
    assert code == 0 and "Aviso" not in err and started[-1][0][3] == TOKEN


class _NoServer:
    server_address = ("127.0.0.1", 8765)

    def serve_forever(self):
        pass

    def server_close(self):
        pass


def test_cli_docs_dir_must_exist(cli_pm, tmp_path):
    for command in ("serve-http", "serve-mcp"):
        code, out, _ = run(command, "--docs-dir", str(tmp_path / "nao-existe"))
        assert code == 2 and "não existe" in json.loads(out)["error"]["message"], command


def test_cli_missing_files_are_clear_errors(cli_pm, tmp_path):
    missing = str(tmp_path / "nao-existe.json")
    for argv in (["memories", "list", "--params", "@" + missing],
                 ["memories", "search", "--owner", "ana", "--query", "x",
                  "--filters", "@" + missing],
                 ["graph", "html", "--owner", "ana", "--out",
                  str(tmp_path / "pasta-que-nao-existe" / "g.html")]):
        code, out, err = run(*argv)
        assert code == 2, argv
        assert json.loads(out)["error"]["code"] == "invalid_input"
        assert "Traceback" not in err
