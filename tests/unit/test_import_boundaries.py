"""Swappable pieces: outside the engine/reader/prompt/render/server packages, nothing names a
concrete engine or an optional dependency. defaults.py is the single composition point."""

import ast
from pathlib import Path

import pi_memory

PACKAGE = Path(pi_memory.__file__).parent
ALLOWED = {"defaults.py"}
FORBIDDEN_MODULES = ("qdrant_client", "fastembed", "chromadb", "psycopg", "pgvector", "pypdf",
                     "mcp")
FORBIDDEN_PREFIXES = ("pi_memory.engines.embedders", "pi_memory.engines.llms",
                      "pi_memory.engines.stores")


def imported_names(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_core_modules_do_not_import_concrete_engines():
    offenders = []
    for path in PACKAGE.glob("*.py"):
        if path.name in ALLOWED:
            continue
        for name in imported_names(path):
            if name.split(".")[0] in FORBIDDEN_MODULES or name.startswith(FORBIDDEN_PREFIXES):
                offenders.append(f"{path.name}: {name}")
    assert offenders == []


def test_text_io_is_utf8_and_there_are_no_shell_calls():
    """Windows, Linux and macOS: text always read/written as UTF-8, no shell (paths with spaces
    and accents keep working)."""
    problems = []
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in ("read_text", "write_text"):
                has_encoding = any(k.arg == "encoding" for k in node.keywords) or (
                    name == "read_text" and node.args) or (name == "write_text"
                                                          and len(node.args) > 1)
                if not has_encoding:
                    problems.append(f"{path.name}:{node.lineno} {name} sem encoding")
            if name == "open" and isinstance(node.func, ast.Name):
                mode = node.args[1].value if len(node.args) > 1 and isinstance(
                    node.args[1], ast.Constant) else "r"
                if "b" not in mode and not any(k.arg == "encoding" for k in node.keywords):
                    problems.append(f"{path.name}:{node.lineno} open sem encoding")
            if name in ("system", "Popen", "run", "call", "check_output") and isinstance(
                    node.func, ast.Attribute) and getattr(node.func.value, "id", "") in (
                    "os", "subprocess"):
                problems.append(f"{path.name}:{node.lineno} chamada de shell")
    assert problems == []
