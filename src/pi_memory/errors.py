"""Exceptions of the library. Every one has a stable `code` and a message in Portuguese saying
what to do; `to_dict()` is the JSON error shared by the library, the CLI, HTTP and MCP."""

from __future__ import annotations


class PiMemoryError(Exception):
    code = "internal"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


class InvalidInputError(PiMemoryError):
    code = "invalid_input"


class NotFoundError(PiMemoryError):
    code = "not_found"


class EngineUnavailableError(PiMemoryError):
    code = "engine_unavailable"


class EngineTimeoutError(PiMemoryError):
    code = "engine_timeout"


class EngineAuthError(PiMemoryError):
    code = "engine_auth"


class EngineResponseError(PiMemoryError):
    code = "engine_response"


class EmbedderMismatchError(PiMemoryError):
    code = "embedder_mismatch"


class StoreBusyError(PiMemoryError):
    code = "store_busy"


class UnsupportedFormatError(PiMemoryError):
    code = "unsupported_format"


class NoTextError(PiMemoryError):
    code = "no_text"


class UnreadableDocumentError(PiMemoryError):
    code = "unreadable_document"


REPO_URL = "git+https://github.com/Pedro-Bianco/pi-memory"


class MissingExtraError(PiMemoryError):
    code = "missing_extra"

    def __init__(self, extra: str, what: str):
        super().__init__(
            f"{what} precisa do extra opcional '{extra}'. Instale com: "
            f'pip install "pi-memory[{extra}] @ {REPO_URL}"'
        )
        self.extra = extra
