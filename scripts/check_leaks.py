"""Leak check before publishing: the files git would publish (tracked + untracked not ignored)
must have no personal data, secrets or personal paths; anything else to block (names, internal
words, attribution lines) goes in the private terms file.

    python scripts/check_leaks.py
    PI_MEMORY_LEAK_TERMS=/caminho/fora/do/repo/termos.txt python scripts/check_leaks.py

The private terms file (one term per line, '#' for comments) lives OUTSIDE the repository: the
terms themselves are private. Exit code 0 = nothing found; 1 = findings (file:line: kind).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Public identity that is allowed on purpose (repository URL and the GitHub noreply author).
ALLOWED = [
    "152442224+Pedro-Bianco@users.noreply.github.com",
    "github.com/Pedro-Bianco/pi-memory",
    "Pedro-Bianco",
]

PATTERNS = {
    "e-mail": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "CPF": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    "telefone": re.compile(r"\(?\b\d{2}\)?\s?9\d{4}-?\d{4}\b"),
    "chave Google": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    "chave Google (AQ.)": re.compile(r"\bAQ\.[0-9A-Za-z_-]{30,}"),
    "chave OpenAI/Anthropic": re.compile(r"\bsk-(?:ant-|proj-)?[0-9A-Za-z_-]{20,}"),
    "token GitHub": re.compile(r"\bgh[pousr]_[0-9A-Za-z]{30,}"),
    "chave Hugging Face": re.compile(r"\bhf_[0-9A-Za-z]{30,}"),
    "pasta pessoal": re.compile(r"(?i)(?:[a-z]:[\\/]+users[\\/]+[^\\/\s\"']+|/home/[^/\s\"']+|"
                                r"/Users/[^/\s\"']+)"),
}
# e-mails that are clearly placeholders or examples
SAFE_EMAIL = re.compile(r"@(?:example\.(?:com|org)|exemplo\.com|users\.noreply\.github\.com)$")
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".docx", ".xlsx", ".pptx", ".ico", ".zip"}


def publishable_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                         cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    return [ROOT / name for name in out.split("\0") if name]


def private_terms() -> list[str]:
    path = os.environ.get("PI_MEMORY_LEAK_TERMS")
    if not path:
        return []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [t.strip() for t in lines if t.strip() and not t.lstrip().startswith("#")]


def scan(path: Path, terms: list[str]) -> list[str]:
    if path.suffix.lower() in BINARY or not path.is_file() or path == Path(__file__).resolve():
        return []   # this file holds the patterns themselves
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    findings = []
    rel = path.relative_to(ROOT).as_posix()
    for number, line in enumerate(text.splitlines(), 1):
        clean = line
        for allowed in ALLOWED:
            clean = clean.replace(allowed, "")
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(clean):
                if kind == "e-mail" and SAFE_EMAIL.search(match.group(0)):
                    continue
                findings.append(f"{rel}:{number}: {kind}: {match.group(0)[:60]}")
        low = clean.casefold()
        for term in terms:
            if term.casefold() in low:
                findings.append(f"{rel}:{number}: termo privado")
    return findings


def main() -> int:
    terms = private_terms()
    if not terms:
        print("aviso: PI_MEMORY_LEAK_TERMS não definido; termos privados não verificados",
              file=sys.stderr)
    files = publishable_files()
    findings = [f for path in files for f in scan(path, terms)]
    for finding in findings:
        print(finding)
    print(f"{len(files)} arquivos verificados, {len(findings)} ocorrência(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
