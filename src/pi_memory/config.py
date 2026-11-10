"""Defaults and measured constants, in one place. Numbers marked "earlier measurement" were
measured before this library existed and are not in eval/; only eval/results/ backs public
claims."""

DEFAULT_PATH = "pi_memory_data"
COLLECTION_PREFIX = "pi_memory"
SCHEMA_VERSION = 1
TIMEOUT_S = 60.0

# e5-large: right piece in the top 3 for 50/52 questions (Qdrant) and exact terms 11/12
# (eval documents, 2026-11-04); ~272 ms per piece on CPU (earlier measurement, 2026-11-01).
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
# qwen2.5:14b: 54/58 memory cases, 0 wrongful deletions, median 6.7 s per conversation
# (eval memory, 2026-11-04). qwen3:8b got 36/56 and qwen3:4b-instruct 34/56 with these prompts.
DEFAULT_LLM_MODEL = "qwen2.5:14b"
OLLAMA_HOST = "http://localhost:11434"

# A fixed list tagged 28/30 memories right; vectors alone kept only 43-49% of nearest-neighbour
# links inside a topic (earlier measurement, 2026-10-31).
DEFAULT_TOPICS = (
    "perfil", "família", "trabalho", "saúde", "rotina", "lazer", "animais", "casa", "finanças",
    "estudos", "outros",
)
FALLBACK_TOPIC = "outros"

# Messages sent to the extractor per call (earlier measurement).
EXTRACTION_WINDOW = 16
# Similar memories compared with each new fact (earlier measurement; mem0 uses the same idea).
DECISION_CANDIDATES = 3
# How decision candidates are found: "dense" (meaning only) or "hybrid" (meaning + exact word).
# Measured 2026-11-04, qwen2.5:14b, 57 cases: both 53/57, 0 wrongful deletions. But with hybrid the
# word "usuário" pulled unrelated memories up and "A usuária mora em Curitiba" was left out of the 3
# candidates, so "me mudei para Recife" replaced the NAME memory (case update-14); dense kept the
# city among the candidates and replaced it. The public search stays hybrid.
DECISION_SEARCH = "dense"
MAX_MEMORY_CHARS = 2000

# 8 sentences, 1 shared: with 2 shared a 100-page PDF took 129 s instead of 105 s, with the same
# search and citation results (earlier measurement, 2026-10-31).
CHUNK_SENTENCES = 8
CHUNK_OVERLAP = 1
# Small batches pad less: 185-189 ms per piece at 4-8 versus 203 ms at 32 (CPU, 2026-10-31).
EMBED_BATCH = 8

# Candidates fetched from each side before fusing meaning and exact word.
HYBRID_PREFETCH = 20
