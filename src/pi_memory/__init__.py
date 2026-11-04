"""pi-memory: memória de longo prazo, base de documentos com busca híbrida e grafo por assunto."""

from pi_memory.aio import AsyncPiMemory
from pi_memory.client import PiMemory
from pi_memory.errors import (
    EmbedderMismatchError,
    EngineAuthError,
    EngineResponseError,
    EngineTimeoutError,
    EngineUnavailableError,
    InvalidInputError,
    MissingExtraError,
    NoTextError,
    NotFoundError,
    PiMemoryError,
    StoreBusyError,
    UnreadableDocumentError,
    UnsupportedFormatError,
)

__version__ = "0.1.0"

__all__ = [
    "PiMemory",
    "AsyncPiMemory",
    "PiMemoryError",
    "InvalidInputError",
    "NotFoundError",
    "EngineUnavailableError",
    "EngineTimeoutError",
    "EngineAuthError",
    "EngineResponseError",
    "EmbedderMismatchError",
    "StoreBusyError",
    "UnsupportedFormatError",
    "NoTextError",
    "UnreadableDocumentError",
    "MissingExtraError",
    "__version__",
]
