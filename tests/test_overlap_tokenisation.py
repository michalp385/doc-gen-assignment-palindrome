"""Tokenisation for the six-word overlap checks (T29 verifier checkpoint), tests first.

A source document with curly apostrophes ("client’s") and a prompt with straight ones
("client's") must tokenise alike, or a quoted run is split and evades both the prompt-overlap
check in `scripts/check_repo.py` and the phrase-bank check in `report_eval.synth.phrases`. A
placeholder followed by a possessive ("{holder}'s cash account") must also match a real name
plus "'s".

The quoted run in these tests is exactly six words with the apostrophe word inside it and
different words on either side, so a split apostrophe leaves no other six-word run to catch.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from docx import Document

from report_eval.synth import phrases
from report_eval.synth.phrases import PHRASE_BANK, bank_overlap

ROOT = Path(__file__).resolve().parent.parent


def _load_check_repo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_repo_tok", ROOT / "scripts/check_repo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECK_REPO = _load_check_repo()

SOURCE_CURLY = "alpha so the client’s account was reviewed omega"
PROMPT_STRAIGHT = "beta so the client's account was reviewed gamma"
SOURCE_STRAIGHT = "alpha so the client's account was reviewed omega"
PROMPT_CURLY = "beta so the client’s account was reviewed gamma"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(CHECK_REPO, "ROOT", tmp_path)
    monkeypatch.setattr(CHECK_REPO, "DATA", tmp_path / "data")
    monkeypatch.setattr(CHECK_REPO, "PROMPTS_DIR", tmp_path / "config" / "prompts")
    (tmp_path / "config" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "client_x").mkdir(parents=True)
    return tmp_path


def _docx(path: Path, text: str) -> None:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(path))


def test_curly_and_straight_apostrophes_tokenise_alike() -> None:
    curly = CHECK_REPO._words(SOURCE_CURLY)  # noqa: SLF001  # unit under test
    straight = CHECK_REPO._words(SOURCE_STRAIGHT)  # noqa: SLF001  # unit under test
    assert curly == straight


def test_a_straight_apostrophe_prompt_quoting_a_curly_apostrophe_source_is_flagged(
    repo: Path,
) -> None:
    _docx(repo / "data" / "client_x" / "meeting_notes.docx", SOURCE_CURLY)
    (repo / "config" / "prompts" / "p.md").write_text(PROMPT_STRAIGHT + "\n", encoding="utf-8")
    assert CHECK_REPO.check_prompt_overlap({})


def test_a_curly_apostrophe_prompt_quoting_a_straight_apostrophe_source_is_flagged(
    repo: Path,
) -> None:
    _docx(repo / "data" / "client_x" / "meeting_notes.docx", SOURCE_STRAIGHT)
    (repo / "config" / "prompts" / "p.md").write_text(PROMPT_CURLY + "\n", encoding="utf-8")
    assert CHECK_REPO.check_prompt_overlap({})


def test_the_phrase_bank_check_sees_a_curly_apostrophe_document() -> None:
    real = PHRASE_BANK["precondition_blocking"][0].format(holder="Alan", platform="Wexcombe")
    curly = real.replace("'", "’")
    assert curly != real
    hits = bank_overlap([f"Noted. {curly} Done."])
    assert {pattern for pattern, _ in hits} == {"precondition_blocking"}


def test_a_placeholder_followed_by_a_possessive_matches_a_name_and_its_s() -> None:
    real = PHRASE_BANK["precondition_soft"][1].format(holder="Bertram", platform="Pennington")
    assert "Bertram's" in real
    hits = bank_overlap([real])
    assert "precondition_soft" in {pattern for pattern, _ in hits}


def test_a_field_with_a_possessive_is_one_wildcard_token() -> None:
    assert phrases._template_tokens("{holder}'s cash account") == [  # noqa: SLF001  # unit under test
        None,
        "cash",
        "account",
    ]
    assert phrases._template_tokens("the {account} entirely") == [  # noqa: SLF001  # unit under test
        "the",
        None,
        "entirely",
    ]
