"""PDF with pypdf (0.65 s for 100 pages, original project, 2026-11-01). Scanned PDFs (images
only) have no text: OCR is out of this version and could come as a custom reader."""

from __future__ import annotations

import io

from pi_memory.engines._extras import require
from pi_memory.errors import UnreadableDocumentError
from pi_memory.interfaces import Section


class PdfReader:
    extensions = frozenset({".pdf"})

    def read(self, data: bytes, filename: str) -> list[Section]:
        pypdf = require("pypdf", "pdf", "Ler PDF")
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise UnreadableDocumentError(f"O PDF '{filename}' está protegido por senha.")
            sections = []
            for number, page in enumerate(reader.pages, 1):
                text = "\n".join(line.strip() for line in (page.extract_text() or "").splitlines()
                                 if line.strip())
                if text:
                    sections.append(Section(f"página {number}", text))
            return sections
        except UnreadableDocumentError:
            raise
        except Exception as e:   # pypdf raises several error types for broken files
            raise UnreadableDocumentError(
                f"Não consegui ler o PDF '{filename}': ele parece corrompido ({type(e).__name__})."
            ) from None
