"""The `check_repo.py` extensions (T29, DESIGN.md sections 7.3, 11, 16), tests first.

1. Synthetic clients' full names and account IDs are denied in `config/` and
   `src/agent_pipeline/` -- not their platforms, amounts or single name parts (a synthetic
   surname can be an ordinary word), and not in `src/report_eval/` (the generator's own name
   pools would be denied by the clients they produced).
2. Adviser names (from the report-request tables) and fund names (from the general
   documents) are denied too: a prompt or config must not name the real adviser or a
   distractor fund.
3. No run of six or more words is shared between a prompt (`config/prompts/*.md`) and a
   source document under `data/` (so a prompt can't quote a real meeting note). The report
   spec is exempt -- it is the requirement, not a client source -- and a general phrase can
   be allowlisted file by file, with a reason.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from docx import Document

ROOT = Path(__file__).resolve().parent.parent


def _load_check_repo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_repo_m5", ROOT / "scripts/check_repo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECK_REPO = _load_check_repo()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(CHECK_REPO, "ROOT", tmp_path)
    monkeypatch.setattr(CHECK_REPO, "DATA", tmp_path / "data")
    monkeypatch.setattr(CHECK_REPO, "SCAN_DIRS", [tmp_path / "src", tmp_path / "config"])
    monkeypatch.setattr(CHECK_REPO, "PROMPTS_DIR", tmp_path / "config" / "prompts")
    (tmp_path / "src" / "agent_pipeline").mkdir(parents=True)
    (tmp_path / "src" / "report_eval" / "synth").mkdir(parents=True)
    (tmp_path / "config" / "prompts").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    return tmp_path


def _accounts_file(path: Path, holders: dict[str, list[dict[str, object]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "holders": {
                    f"h{i}": {"name": name, "accounts": accounts}
                    for i, (name, accounts) in enumerate(holders.items())
                }
            }
        ),
        encoding="utf-8",
    )


def _docx(path: Path, paragraphs: list[str], table: list[tuple[str, str]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    if table:
        t = doc.add_table(rows=0, cols=2)
        for label, value in table:
            row = t.add_row()
            row.cells[0].text = label
            row.cells[1].text = value
    doc.save(str(path))


def _real_client(repo: Path) -> None:
    _accounts_file(
        repo / "data" / "client_x" / "client_data_db.json",
        {"Real Person": [{"account_id": "R-ISA-1", "platform": "Holloway", "value": 12345}]},
    )


def _synthetic_client(repo: Path) -> None:
    _accounts_file(
        repo / "data" / "synthetic" / "generated" / "synth_001" / "client_data_db.json",
        {
            "Ottoline Brambleweed": [
                {"account_id": "Z9-ISA-O", "platform": "Zedplatform", "value": 87654}
            ]
        },
    )


# --- synthetic names and account IDs -------------------------------------------------------


def test_synthetic_full_names_and_account_ids_are_collected(repo: Path) -> None:
    _synthetic_client(repo)
    assert CHECK_REPO.collect_synthetic_terms() == {"Ottoline Brambleweed", "Z9-ISA-O"}


def test_synthetic_platforms_amounts_and_name_parts_are_not_denied(repo: Path) -> None:
    _real_client(repo)
    _synthetic_client(repo)
    terms, amounts = CHECK_REPO.collect_denylist()
    assert "Zedplatform" not in terms
    assert "Brambleweed" not in terms and "Ottoline" not in terms
    assert 87654 not in amounts


def test_a_synthetic_name_in_the_pipeline_or_config_is_flagged(repo: Path) -> None:
    _synthetic_client(repo)
    (repo / "src" / "agent_pipeline" / "x.py").write_text(
        "# Ottoline Brambleweed was here\n", encoding="utf-8"
    )
    (repo / "config" / "c.json").write_text('{"id": "Z9-ISA-O"}', encoding="utf-8")
    problems = CHECK_REPO.check_overfitting(set(), {})
    assert any("x.py" in p and "Ottoline Brambleweed" in p for p in problems)
    assert any("c.json" in p and "Z9-ISA-O" in p for p in problems)


def test_the_generators_own_files_may_hold_synthetic_names(repo: Path) -> None:
    _synthetic_client(repo)
    (repo / "src" / "report_eval" / "synth" / "pool.py").write_text(
        "NAMES = ['Ottoline Brambleweed']\n", encoding="utf-8"
    )
    assert CHECK_REPO.check_overfitting(set(), {}) == []


def test_a_synthetic_surname_that_is_an_ordinary_word_does_not_flag_prose(repo: Path) -> None:
    _accounts_file(
        repo / "data" / "synthetic" / "handwritten" / "case_99" / "client_data_db.json",
        {"Klaus Under": [{"account_id": "U-ISA-01"}]},
    )
    (repo / "src" / "agent_pipeline" / "x.py").write_text(
        "# the amount under review\n", encoding="utf-8"
    )
    assert CHECK_REPO.check_overfitting(set(), {}) == []


# --- adviser and fund names ----------------------------------------------------------------


def test_adviser_names_are_read_from_the_report_request_table(repo: Path) -> None:
    _docx(
        repo / "data" / "client_x" / "report_request.docx",
        ["Report Requirement Summary"],
        [("Adviser", "Winifred Ackroyd"), ("Accounts covered", "Something")],
    )
    assert {"Winifred Ackroyd", "Winifred", "Ackroyd"} <= CHECK_REPO.collect_general_terms()


def test_fund_names_are_read_from_general_documents_without_a_leading_article(
    repo: Path,
) -> None:
    _docx(
        repo / "data" / "client_x" / "platform_market_update.docx",
        [
            "Our in-house Falconbridge Balanced Portfolio returned a little over the quarter.",
            "The Ravensmoor Multi-Asset Fund is also illustrative. Nothing else here.",
        ],
    )
    terms = CHECK_REPO.collect_general_terms()
    assert "Falconbridge Balanced Portfolio" in terms
    assert "Ravensmoor Multi-Asset Fund" in terms
    assert "The Ravensmoor Multi-Asset Fund" not in terms


def test_a_fund_or_adviser_name_in_a_prompt_or_config_is_flagged(repo: Path) -> None:
    _docx(
        repo / "data" / "client_x" / "platform_market_update.docx",
        ["Our Falconbridge Balanced Portfolio returned little."],
    )
    _docx(
        repo / "data" / "client_x" / "report_request.docx",
        ["Summary"],
        [("Adviser", "Winifred Ackroyd")],
    )
    (repo / "config" / "prompts" / "p.md").write_text(
        "Never mention the Falconbridge Balanced Portfolio or Winifred Ackroyd.\n",
        encoding="utf-8",
    )
    problems = CHECK_REPO.check_overfitting(set(), {})
    assert any("Falconbridge Balanced Portfolio" in p for p in problems)
    assert any("Winifred Ackroyd" in p for p in problems)


def test_the_real_repos_general_terms_include_its_adviser_and_funds() -> None:
    terms = CHECK_REPO.collect_general_terms()
    assert "Daniel Reeves" in terms
    for fund in (
        "Kestrel Balanced Portfolio",
        "Marlow Multi-Asset Fund",
        "Tavener Income Fund",
        "Pendle Global Fund",
        "Sutton Strategic Fund",
    ):
        assert fund in terms


# --- six-word overlap between prompts and source documents ---------------------------------

QUOTE = "I pulled up the account live during the meeting"


def test_a_six_word_run_shared_with_a_source_document_is_flagged(repo: Path) -> None:
    _docx(repo / "data" / "client_x" / "meeting_notes.docx", [f"Review held. {QUOTE}. Done."])
    (repo / "config" / "prompts" / "p.md").write_text(
        f"Look for wording such as: {QUOTE}, or similar.\n", encoding="utf-8"
    )
    problems = CHECK_REPO.check_prompt_overlap({})
    assert problems
    assert "config/prompts/p.md" in problems[0]
    assert "meeting_notes.docx" in problems[0]


def test_a_five_word_run_is_not_flagged(repo: Path) -> None:
    _docx(repo / "data" / "client_x" / "meeting_notes.docx", ["I pulled up the account."])
    (repo / "config" / "prompts" / "p.md").write_text(
        "Some pulled up the account text.\n", encoding="utf-8"
    )
    assert CHECK_REPO.check_prompt_overlap({}) == []


def test_synthetic_and_markdown_sources_count_too(repo: Path) -> None:
    _docx(repo / "data" / "synthetic" / "handwritten" / "case_01" / "n.docx", [QUOTE + "."])
    (repo / "data" / "client_x").mkdir(parents=True)
    (repo / "data" / "client_x" / "fde_notes.md").write_text(
        "Notes: the fee wording must stay exactly as supplied here.\n", encoding="utf-8"
    )
    (repo / "config" / "prompts" / "p.md").write_text(
        f"{QUOTE}. Also the fee wording must stay exactly as supplied.\n", encoding="utf-8"
    )
    problems = CHECK_REPO.check_prompt_overlap({})
    assert len(problems) == 2


def test_the_report_spec_is_exempt_it_is_the_requirement_not_a_client_source(repo: Path) -> None:
    (repo / "data" / "client_x").mkdir(parents=True)
    (repo / "data" / "client_x" / "template_spec.md").write_text(
        "Set out the ongoing fees and charges that apply.\n", encoding="utf-8"
    )
    (repo / "config" / "prompts" / "p.md").write_text(
        "Set out the ongoing fees and charges that apply.\n", encoding="utf-8"
    )
    assert CHECK_REPO.check_prompt_overlap({}) == []


def test_an_allowlisted_run_is_exempt_only_in_its_own_prompt(repo: Path) -> None:
    _docx(repo / "data" / "client_x" / "meeting_notes.docx", [QUOTE + "."])
    for name in ("a.md", "b.md"):
        (repo / "config" / "prompts" / name).write_text(f"{QUOTE}.\n", encoding="utf-8")
    allow = {"config/prompts/a.md": {"i pulled up the account live during the meeting"}}
    problems = CHECK_REPO.check_prompt_overlap(allow)
    assert [p.split(":")[0] for p in problems] == ["config/prompts/b.md"]


def test_the_repos_own_prompts_pass_the_overlap_check() -> None:
    _, per_file = CHECK_REPO.load_allowlist()
    assert CHECK_REPO.check_prompt_overlap(per_file) == []


def test_the_whole_repo_passes_every_check_repo_section() -> None:
    global_allow, per_file = CHECK_REPO.load_allowlist()
    assert CHECK_REPO.check_overfitting(global_allow, per_file) == []
