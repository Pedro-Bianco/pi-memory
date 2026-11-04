from pi_memory.chunking import SentenceChunker
from pi_memory.interfaces import Section


def sentences(n, prefix="Frase"):
    return " ".join(f"{prefix} número {i}." for i in range(1, n + 1))


def test_eight_sentences_with_one_shared():
    chunks = SentenceChunker().split([Section("página 1", sentences(15))])
    assert len(chunks) == 2
    assert chunks[0].text.startswith("Frase número 1.") and chunks[0].text.endswith("número 8.")
    assert chunks[1].text.startswith("Frase número 8.") and chunks[1].text.endswith("número 15.")
    assert {c.location for c in chunks} == {"página 1"}


def test_never_crosses_sections_and_drops_empty():
    chunks = SentenceChunker().split([Section("página 1", sentences(3, "A")),
                                      Section("página 2", "   "),
                                      Section("página 3", sentences(2, "B"))])
    assert [(c.location, c.text.split()[0]) for c in chunks] == [("página 1", "A"),
                                                                ("página 3", "B")]


def test_lines_count_as_sentences():
    rows = "\n".join(f"linha {i}" for i in range(1, 11))
    chunks = SentenceChunker(size=4, overlap=0).split([Section("aba X", rows)])
    assert [c.text.count("linha") for c in chunks] == [4, 4, 2]
