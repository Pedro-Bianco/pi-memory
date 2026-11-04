"""the memory and document scenarios give the same results on every installed store.
Each store runs the same unit tests in a subprocess (the store is chosen by an environment
variable read by tests.fakes.make_pm)."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLOWS = ["tests/unit/test_memories.py", "tests/unit/test_memories_windows.py",
         "tests/unit/test_documents.py", "tests/contract/test_isolation.py"]
STORES = [pytest.param(name, marks=pytest.mark.skipif(not importlib.util.find_spec(module),
                                                      reason=f"extra {name} não instalado"))
          for name, module in (("qdrant", "qdrant_client"), ("chroma", "chromadb"))]


@pytest.mark.parametrize("store", STORES)
def test_flows_pass_on_store(store):
    env = {**os.environ, "PI_MEMORY_TEST_STORE": store, "PYTHONIOENCODING": "utf-8"}
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *FLOWS],
                         cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                         timeout=600)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-2000:]
