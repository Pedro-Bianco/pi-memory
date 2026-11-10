"""Word (.docx), PowerPoint (.pptx) and Excel (.xlsx) read straight from their zip packages of XML:
only the text is needed, so the standard library avoids three dependencies (an earlier version did
the same)."""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree

from pi_memory.errors import UnreadableDocumentError
from pi_memory.interfaces import Section
from pi_memory.readers.text import ROWS_PER_SECTION, group, rows_as_text

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _open(data: bytes, filename: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UnreadableDocumentError(
            f"Não consegui abrir '{filename}': o arquivo está corrompido ou protegido por senha."
        ) from None


def _xml(z: zipfile.ZipFile, name: str, filename: str):
    try:
        return ElementTree.fromstring(z.read(name))
    except (KeyError, ElementTree.ParseError):
        raise UnreadableDocumentError(
            f"Não consegui ler '{filename}': falta ou está danificada a parte {name}."
        ) from None


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    """Relationship id → target path, resolved relative to `part`."""
    folder, name = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", name + ".rels")
    if rels_name not in z.namelist():
        return {}
    root = ElementTree.fromstring(z.read(rels_name))
    return {r.get("Id"): posixpath.normpath(posixpath.join(folder, r.get("Target", "")))
            for r in root.iter(f"{_PR}Relationship")}


class DocxReader:
    extensions = frozenset({".docx"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        with _open(data, filename) as z:
            body = _xml(z, "word/document.xml", filename).find(f"{_W}body")
        paragraphs: list[str] = []
        for element in list(body) if body is not None else []:
            if element.tag == f"{_W}p":
                text = "".join(t.text or "" for t in element.iter(f"{_W}t")).strip()
                if text:
                    paragraphs.append(text)
            elif element.tag == f"{_W}tbl":
                for row in element.iter(f"{_W}tr"):
                    cells = ["".join(t.text or "" for t in cell.iter(f"{_W}t")).strip()
                             for cell in row.iter(f"{_W}tc")]
                    if any(cells):
                        paragraphs.append(" | ".join(c for c in cells if c))
        return group(paragraphs)


def _shape_text(root) -> list[str]:
    lines = []
    for paragraph in root.iter(f"{_A}p"):
        text = "".join(t.text or "" for t in paragraph.iter(f"{_A}t")).strip()
        if text:
            lines.append(text)
    return lines


class PptxReader:
    extensions = frozenset({".pptx"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        sections: list[Section] = []
        with _open(data, filename) as z:
            slides = sorted(
                (int(m.group(1)), name) for name in z.namelist()
                if (m := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)))
            for number, name in slides:
                text = "\n".join(_shape_text(_xml(z, name, filename)))
                if text:
                    sections.append(Section(f"slide {number}", text))
                notes = [t for t in _rels(z, name).values() if "notesSlide" in t]
                if notes and notes[0] in z.namelist():
                    # the notes page repeats the slide number in a placeholder: drop bare digits
                    lines = [line for line in _shape_text(_xml(z, notes[0], filename))
                             if not line.isdigit()]
                    if lines:
                        sections.append(Section(f"slide {number} (notas)", "\n".join(lines)))
        return sections


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "A").group(0)
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


class XlsxReader:
    extensions = frozenset({".xlsx"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        sections: list[Section] = []
        with _open(data, filename) as z:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                shared = ["".join(t.text or "" for t in si.iter(f"{_S}t"))
                          for si in _xml(z, "xl/sharedStrings.xml", filename).iter(f"{_S}si")]
            targets = _rels(z, "xl/workbook.xml")
            for sheet in _xml(z, "xl/workbook.xml", filename).iter(f"{_S}sheet"):
                part = targets.get(sheet.get(f"{_R}id"))
                if not part or part not in z.namelist():
                    continue
                rows = self._rows(_xml(z, part, filename), shared)
                sections.extend(self._sections(sheet.get("name", "?"), rows))
        return sections

    @staticmethod
    def _rows(root, shared: list[str]) -> list[tuple[int, list[str]]]:
        rows = []
        for row in root.iter(f"{_S}row"):
            values: dict[int, str] = {}
            for cell in row.iter(f"{_S}c"):
                kind, value = cell.get("t"), cell.find(f"{_S}v")
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in cell.iter(f"{_S}t"))
                elif value is None or value.text is None:
                    continue
                elif kind == "s":
                    text = shared[int(value.text)]
                else:
                    text = value.text
                if text.strip():
                    values[_column(cell.get("r", ""))] = text.strip()
            if values:
                width = max(values) + 1
                rows.append((int(row.get("r", len(rows) + 1)),
                             [values.get(i, "") for i in range(width)]))
        return rows

    @staticmethod
    def _sections(name: str, rows: list[tuple[int, list[str]]]) -> list[Section]:
        if not rows:
            return []
        header = rows[0][1]
        sections = []
        for start in range(0, len(rows), ROWS_PER_SECTION):
            chunk = rows[start:start + ROWS_PER_SECTION]
            body = [cells for number, cells in chunk if number != rows[0][0]]
            text = rows_as_text(header, body)
            if text:
                sections.append(Section(f"aba {name}, linhas {chunk[0][0]}–{chunk[-1][0]}", text))
        return sections
