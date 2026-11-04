"""Loads eval/fixtures/make_fixtures.py (not a package) for the tests."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "make_fixtures.py"
_spec = importlib.util.spec_from_file_location("make_fixtures", _PATH)
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)

FILES = fixtures.all_fixtures()
