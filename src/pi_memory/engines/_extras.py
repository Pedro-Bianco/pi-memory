from __future__ import annotations

import importlib
from types import ModuleType

from pi_memory.errors import MissingExtraError


def require(module: str, extra: str, what: str | None = None) -> ModuleType:
    """Imports an optional dependency, or explains which extra to install."""
    try:
        return importlib.import_module(module)
    except ImportError:
        raise MissingExtraError(extra, what or f"O módulo '{module}'") from None
