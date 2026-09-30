"""`check_repo.py`: no file under outputs/ names internal tooling ("CLAUDE.md"). Review sheets and
ledgers are adviser-facing, so a reference to the project's own agent instructions is a leak."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_check_repo() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_repo_outputs", ROOT / "scripts" / "check_repo.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECK_REPO = _load_check_repo()


@pytest.fixture
def outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(CHECK_REPO, "ROOT", tmp_path)
    out = tmp_path / "outputs" / "handwritten"
    out.mkdir(parents=True)
    return out


def test_a_file_under_outputs_naming_claude_md_is_flagged(outputs: Path) -> None:
    (outputs / "case_01.review.md").write_text(
        "- #1: ongoing charge (never estimated (CLAUDE.md non-negotiable))\n", encoding="utf-8"
    )

    problems = CHECK_REPO.check_outputs_internal_refs()

    assert len(problems) == 1
    assert "outputs/handwritten/case_01.review.md" in problems[0]


def test_clean_outputs_pass(outputs: Path) -> None:
    (outputs / "case_01.review.md").write_text(
        "- #1: ongoing charge (firm policy: never estimated)\n", encoding="utf-8"
    )

    assert CHECK_REPO.check_outputs_internal_refs() == []


def test_a_missing_outputs_dir_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CHECK_REPO, "ROOT", tmp_path)

    assert CHECK_REPO.check_outputs_internal_refs() == []
