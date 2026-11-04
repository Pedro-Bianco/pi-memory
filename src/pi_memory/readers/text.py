"""Plain text (.txt), Markdown (.md) and CSV (.csv)."""

from __future__ import annotations

import csv
import io
import re

from pi_memory.interfaces import Section

PARAGRAPHS_PER_SECTION = 20   # .txt has no pages: "trecho N" groups paragraphs
ROWS_PER_SECTION = 40
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def decode(data: bytes) -> str:
    """UTF-8 first; files saved by older Windows programs are often cp1252."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]


def group(paragraphs: list[str], size: int = PARAGRAPHS_PER_SECTION) -> list[Section]:
    return [Section(f"trecho {n}", "\n".join(paragraphs[i:i + size]))
            for n, i in enumerate(range(0, len(paragraphs), size), 1)]


class TextReader:
    extensions = frozenset({".txt"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        return group(_paragraphs(decode(data)))


class MarkdownReader:
    """Each heading starts a section named after it; text before the first one is "início"."""

    extensions = frozenset({".md", ".markdown"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        sections: list[Section] = []
        title, lines = "início", []

        def flush():
            body = "\n".join(_paragraphs("\n".join(lines)))
            if body:
                sections.append(Section(title if title == "início" else f"seção {title}", body))

        for line in decode(data).splitlines():
            heading = _HEADING.match(line)
            if heading:
                flush()
                title, lines = heading.group(1), []
            else:
                lines.append(line)
        flush()
        return sections


def rows_as_text(header: list[str], rows: list[list[str]]) -> str:
    """"coluna: valor | coluna: valor" — the column name next to each value helps the search."""
    lines = []
    for row in rows:
        cells = [f"{h}: {v}" if h else v for h, v in zip(header, row, strict=False) if v]
        cells += [v for v in row[len(header):] if v]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


class CsvReader:
    extensions = frozenset({".csv"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        text = decode(data)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), dialect)]
        rows = [r for r in rows if any(r)]
        if not rows:
            return []
        header, body = rows[0], rows[1:]
        sections = []
        for start in range(0, len(body), ROWS_PER_SECTION):
            chunk = body[start:start + ROWS_PER_SECTION]
            first, last = start + 2, start + 1 + len(chunk)   # file lines; line 1 is the header
            content = rows_as_text(header, chunk)
            if content:
                sections.append(Section(f"linhas {first}–{last}", content))
        return sections
