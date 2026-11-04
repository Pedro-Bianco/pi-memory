from pi_memory import config
from tests.fakes import ScriptedLLM, make_pm


def test_long_conversation_is_extracted_in_windows():
    windows = []

    def handle(prompt):
        if prompt.startswith("Abaixo está"):
            windows.append(prompt.count(": mensagem "))
            return f"FATO: O usuário tem o fato número {len(windows)}"
        if prompt.startswith("Classifique"):
            return "1. outros\n2. outros\n3. outros"
        return "ADD"

    pm = make_pm(llm=ScriptedLLM(handler=handle))
    messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"mensagem {i}"}
                for i in range(40)]
    decisions = pm.memories.add(messages, owner="ana")["decisions"]
    assert windows == [config.EXTRACTION_WINDOW, config.EXTRACTION_WINDOW, 8]
    assert [d["event"] for d in decisions] == ["add", "add", "add"]
    assert pm.memories.list(owner="ana")["total"] == 3
