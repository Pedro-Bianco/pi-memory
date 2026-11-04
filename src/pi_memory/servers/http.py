"""HTTP server with the standard library only: POST /v1/<operation> with the parameters as JSON,
the same JSON back as the Python API. GET /v1/health, GET /v1/openapi.json, and GET / with the
local administration page (memories, collections, documents, chunks, search, graph), which only
calls the same /v1 operations.

Listens on 127.0.0.1 by default. With a token (make_server(token=...), `serve-http --token` or
PI_MEMORY_TOKEN), every /v1 operation needs "Authorization: Bearer <token>"; the admin page asks
for it. Outside this machine the command line refuses to start without a token.

Browser attacks against a local server: operations only accept "Content-Type: application/json"
(a page from another site cannot send that without the browser asking first, and this server
never allows it), and without a token only a local Host header is accepted (a site whose name
starts pointing to 127.0.0.1, "DNS rebinding", is refused). documents.add does not read files by
path unless a folder is given (docs_dir); see operations.allowed_path. One PiMemory per
process; calls are served one at a time (the local Qdrant client is not meant for concurrent use
from several threads).
"""

from __future__ import annotations

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from pi_memory import __version__
from pi_memory.operations import OPERATIONS, dispatch, openapi

if TYPE_CHECKING:
    from pi_memory.client import PiMemory

MAX_BODY = 50 * 1024 * 1024   # 50 MB: documents arrive as base64
STATUS = {"invalid_input": 400, "unsupported_format": 400, "no_text": 400,
          "unreadable_document": 400, "not_found": 404, "embedder_mismatch": 409,
          "store_busy": 409, "engine_unavailable": 502, "engine_timeout": 502,
          "engine_auth": 502, "engine_response": 502}


# Nothing from the internet: scripts and styles are inline, data comes from this same server.
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self' data:; frame-src 'self'; base-uri 'none'; "
       "form-action 'none'")


def admin_page() -> bytes:
    return resources.files("pi_memory.servers").joinpath("admin.html").read_bytes()


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _host_name(header: str) -> str:
    """"127.0.0.1:8765" -> "127.0.0.1"; "[::1]:8765" -> "::1"."""
    header = header.strip().lower()
    if header.startswith("["):
        return header[1:].split("]", 1)[0]
    return header.rsplit(":", 1)[0] if header.count(":") == 1 else header


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def make_handler(pm: PiMemory, lock: threading.Lock, token: str | None = None,
                 docs_dir: Path | None = None, host: str = "127.0.0.1"):
    expected = f"Bearer {token}".encode() if token else None
    local_hosts = LOCAL_HOSTS | {host.strip("[]").lower()}
    files = docs_dir if docs_dir is not None else False

    class Handler(BaseHTTPRequestHandler):
        server_version = f"pi-memory/{__version__}"

        def _local_host(self) -> bool:
            """Without a token, only requests addressed to this machine by name (anti DNS
            rebinding). With a token, an attacker's browser has nothing to send."""
            if expected is not None or _host_name(self.headers.get("Host") or "") in local_hosts:
                return True
            self._send(403, _error("forbidden_host", "Endereço (Host) não permitido sem token. "
                                                     "Acesse por http://127.0.0.1 ou use --token."))
            return False

        def _authorized(self) -> bool:
            if expected is None:
                return True
            given = (self.headers.get("Authorization") or "").strip().encode("utf-8")
            if hmac.compare_digest(given, expected):   # constant time: no timing leak
                return True
            self._send(401, _error("unauthorized", "Token ausente ou inválido. Envie o cabeçalho "
                                                   "'Authorization: Bearer <token>'."))
            return False

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 (http.server API)
            if not self._local_host():
                return
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                page = admin_page()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Security-Policy", CSP)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
            elif self.path == "/v1/health":
                self._send(200, {"status": "ok", "version": __version__})
            elif self.path == "/v1/openapi.json":
                if not self._authorized():
                    return
                self._send(200, openapi(__version__))
            else:
                self._send(404, _error("not_found", f"Caminho desconhecido: {self.path}"))

        def do_POST(self):  # noqa: N802
            name = self.path.removeprefix("/v1/")
            if not self._local_host() or not self._authorized():
                return
            if not self.path.startswith("/v1/") or name not in OPERATIONS:
                self._send(404, _error("not_found", f"Operação desconhecida: {self.path}. Veja "
                                                    "GET /v1/openapi.json"))
                return
            kind = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if kind != "application/json":
                self._send(415, _error("invalid_input", "Envie o corpo com o cabeçalho "
                                                        "'Content-Type: application/json'."))
                return
            raw = (self.headers.get("Content-Length") or "0").strip()
            if not raw.isdigit():
                self._send(400, _error("invalid_input", "Content-Length inválido."))
                return
            length = int(raw)
            if length > MAX_BODY:
                self._send(413, _error("invalid_input", "Corpo maior que 50 MB."))
                return
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, UnicodeDecodeError):
                self._send(400, _error("invalid_input", "O corpo precisa ser JSON em UTF-8."))
                return
            with lock:
                result = dispatch(pm, name, params, files=files)
            error = result.get("error") if isinstance(result, dict) else None
            status = 200 if not isinstance(error, dict) else STATUS.get(error.get("code"), 500)
            self._send(status, result)

        def log_message(self, format, *args):  # noqa: A002
            pass   # no request log: bodies and paths may carry personal data

    return Handler


def make_server(pm: PiMemory, host: str = "127.0.0.1", port: int = 8765,
                token: str | None = None, docs_dir: str | Path | None = None
                ) -> ThreadingHTTPServer:
    """port=0 picks a free port (tests); the chosen one is server.server_address[1].
    docs_dir: the only folder documents.add may read by path (default: none)."""
    folder = Path(docs_dir) if docs_dir is not None else None
    return ThreadingHTTPServer((host, port), make_handler(pm, threading.Lock(), token or None,
                                                          folder, host))
