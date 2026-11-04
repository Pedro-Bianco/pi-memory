from __future__ import annotations

import hashlib
import math
import unicodedata
import uuid
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id() -> str:
    return str(uuid.uuid4())


def stable_id(*parts: str, owner: str | None = None) -> str:
    """A short id from parts compared without case ("Ata.md" == "ata.md"). The owner, when given,
    is taken exactly as written: owners "Ana" and "ana" are different and must never share an id
    (one would overwrite the other's records)."""
    joined = "\x1f".join(p.casefold() for p in parts)
    if owner is not None:
        joined = owner + "\x1e" + joined
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def plain(text: str) -> str:
    """Casefolded, without accents."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """For equality checks: no accents, no case, no punctuation at the ends, single spaces."""
    return " ".join(plain(text).split()).strip(" .!?;:")


def unit(vector) -> list[float]:
    """L2-normalized copy: cosine similarity becomes a dot product in every store."""
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values] if norm else values
