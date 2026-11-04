"""Which reader handles each extension. Readers the developer passes come first."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePath

from pi_memory.errors import UnsupportedFormatError
from pi_memory.interfaces import DocumentReader, Section
from pi_memory.readers.office import DocxReader, PptxReader, XlsxReader
from pi_memory.readers.pdf import PdfReader
from pi_memory.readers.text import CsvReader, MarkdownReader, TextReader

DEFAULT_READERS: tuple[DocumentReader, ...] = (
    PdfReader(), DocxReader(), PptxReader(), XlsxReader(), CsvReader(), TextReader(),
    MarkdownReader(),
)


class ReaderRegistry:
    def __init__(self, custom: Sequence[DocumentReader] = ()):
        self._by_ext: dict[str, DocumentReader] = {}
        for reader in (*DEFAULT_READERS, *custom):   # later wins: custom readers override
            for ext in reader.extensions:
                self._by_ext[ext.lower()] = reader

    def supported(self) -> list[str]:
        return sorted(self._by_ext)

    def read(self, data: bytes, filename: str) -> list[Section]:
        ext = PurePath(filename).suffix.lower()
        reader = self._by_ext.get(ext)
        if reader is None:
            raise UnsupportedFormatError(
                f"Formato não suportado ({ext or 'sem extensão'}) em '{filename}'. Aceitos: "
                f"{', '.join(self.supported())}. Para outro formato, passe um leitor próprio em "
                "PiMemory(readers=[...])."
            )
        return reader.read(data, filename)
