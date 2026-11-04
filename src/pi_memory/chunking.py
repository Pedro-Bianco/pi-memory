"""Default chunker: groups of sentences inside one section, so every piece keeps an exact
citation."""

from __future__ import annotations

import re

from pi_memory import config
from pi_memory.interfaces import ChunkText, Section

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")


class SentenceChunker:
    """size sentences per piece, `overlap` shared with the next (values in config.py, measured).
    A line break also ends a sentence: spreadsheet rows and lists stay whole."""

    def __init__(self, size: int = config.CHUNK_SENTENCES, overlap: int = config.CHUNK_OVERLAP):
        if size < 1 or not 0 <= overlap < size:
            raise ValueError("size >= 1 e 0 <= overlap < size")
        self.size = size
        self.overlap = overlap

    def split(self, sections: list[Section]) -> list[ChunkText]:
        chunks: list[ChunkText] = []
        step = self.size - self.overlap
        for section in sections:
            sentences = [s.strip() for s in _SENTENCE_END.split(section.text) if s.strip()]
            for start in range(0, len(sentences), step):
                piece = sentences[start:start + self.size]
                chunks.append(ChunkText(section.location, " ".join(piece)))
                if start + self.size >= len(sentences):
                    break
        return chunks
