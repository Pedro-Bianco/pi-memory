"""The local admin page in a real browser: overview items open the right tab and nothing logs a
JavaScript error. Needs Playwright and Chrome: pip install playwright; pytest -m browser"""

import importlib.util
import threading

import pytest

from pi_memory.servers.http import make_server
from tests.fakes import make_pm

pytestmark = [pytest.mark.browser,
              pytest.mark.skipif(not importlib.util.find_spec("playwright"),
                                 reason="playwright não instalado")]


@pytest.fixture
def base():
    pm = make_pm()
    for text, topic in [("O usuário tem uma gata chamada Mel", "animais"),
                        ("O usuário corre 5 km", "saúde"), ("O usuário gosta de jazz", "lazer")]:
        pm.memories.remember(text, owner="ana", topic=topic)
    pm.documents.add_text("Relatório", "As vendas cresceram.", owner="ana", collection="financeiro")
    pm.documents.add_text("Ata", "A reunião aprovou o orçamento.", owner="ana", collection="atas")
    server = make_server(pm, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_overview_items_open_the_right_tab(base):
    from playwright.sync_api import Error, sync_playwright

    errors = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Error:
            pytest.skip("Chrome não encontrado")
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(base + "/?owner=ana#overview")

        page.click("#by-topic .rowlink:has-text('animais')")
        page.wait_for_selector("#tab-memories:not([hidden]) #memory-list li")
        assert page.input_value("#memory-topic") == "animais"
        assert page.locator("#memory-list .tag").all_inner_texts() == ["animais"]

        page.click("nav button[data-tab=overview]")
        page.click("#overview-collections .rowlink:has-text('financeiro')")
        page.wait_for_function(
            "document.querySelector('#documents-title').textContent.includes('financeiro')")
        assert page.locator("#document-list .tag").all_inner_texts() == ["financeiro"]

        page.click("nav button[data-tab=overview]")
        page.click(".kpi:has-text('memórias')")
        page.wait_for_function("document.querySelector('#memory-count').textContent.includes('3')")
        assert page.input_value("#memory-topic") == ""
        browser.close()
    assert errors == []
