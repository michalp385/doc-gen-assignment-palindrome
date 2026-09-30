"""`scripts/progression.py` writes two results files in one run. Their names come from a
one-second timestamp and the commit, so two sides finished in the same second would share a name
and the second would silently overwrite the first (the table then compared a file with itself)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "progression_script_3", ROOT / "scripts" / "progression.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROGRESSION = _load()


def test_a_second_side_finished_in_the_same_second_gets_a_later_stamp() -> None:
    assert (
        PROGRESSION.later_stamp("2026-09-30T12:00:00Z", "2026-09-30T12:00:00Z")
        == "2026-09-30T12:00:01Z"
    )


def test_an_already_later_stamp_is_kept() -> None:
    assert (
        PROGRESSION.later_stamp("2026-09-30T12:00:00Z", "2026-09-30T12:00:05Z")
        == "2026-09-30T12:00:05Z"
    )
