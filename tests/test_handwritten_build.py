"""Build reproducibility and fixture consistency for the 20 hand-written cases (T3).

Two things are checked, both generically: no client value lives in this file, only in
eval/handwritten_src/*.md, data/synthetic/handwritten/*/ and eval/expected/case_*.json.

1. Rebuilding every case from its markdown source reproduces the committed folder
   byte-for-byte (scripts/build_handwritten.py must be deterministic).
2. Each case's expected facts are consistent with its own built source folder, using the
   same kind of checks as tests/test_expected_fixtures.py (T2), extended for the two
   cases that expect a failed generation.
"""

from __future__ import annotations

import filecmp
import importlib.util
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from document_formatter.loading import read_file
from report_eval.expected import ExpectedFacts, load_expected

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "eval" / "handwritten_src"
DATA_DIR = ROOT / "data" / "synthetic" / "handwritten"

CASES = sorted(p.stem for p in SRC_DIR.glob("case_*.md"))
FAILED_CASES = {"case_19", "case_20"}
DRAFT_CASES = [c for c in CASES if c not in FAILED_CASES]

_MONEY_RE = re.compile(r"£\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)|GBP\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _load_build_module():
    spec = importlib.util.spec_from_file_location(
        "build_handwritten", ROOT / "scripts" / "build_handwritten.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses needs the module registered to resolve types
    spec.loader.exec_module(module)
    return module


BUILD = _load_build_module()


def _account_ids(case: str) -> set[str]:
    db = json.loads((DATA_DIR / case / "client_data_db.json").read_text(encoding="utf-8"))
    return {
        acc["account_id"]
        for holder in db.get("holders", {}).values()
        for acc in holder.get("accounts", [])
    }


def _account_values(case: str) -> set[Decimal]:
    db = json.loads((DATA_DIR / case / "client_data_db.json").read_text(encoding="utf-8"))
    return {
        Decimal(str(acc["value"]))
        for holder in db.get("holders", {}).values()
        for acc in holder.get("accounts", [])
        if isinstance(acc.get("value"), (int, float))
    }


def _account_owners(case: str) -> dict[str, set[str]]:
    db = json.loads((DATA_DIR / case / "client_data_db.json").read_text(encoding="utf-8"))
    owners: dict[str, set[str]] = {}
    for holder in db.get("holders", {}).values():
        for acc in holder.get("accounts", []):
            owners.setdefault(acc["account_id"], set()).add(holder["name"])
    return owners


def _text_files(case: str) -> list[Path]:
    return sorted(
        p for p in (DATA_DIR / case).iterdir() if p.is_file() and p.suffix in {".docx", ".md"}
    )


def _all_source_text(case: str) -> str:
    return "\n".join(read_file(p) for p in _text_files(case))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _quote_in(quote: str, text: str) -> bool:
    return _normalize(quote) in _normalize(text)


def _money_amounts(text: str) -> set[Decimal]:
    amounts = set()
    for m in _MONEY_RE.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        amounts.add(Decimal(raw))
    return amounts


def _percentages(text: str) -> set[Decimal]:
    return {Decimal(m.group(1)) for m in _PERCENT_RE.finditer(text)}


def _figure_number(value: str) -> tuple[str, Decimal] | None:
    m = _MONEY_RE.search(value)
    if m:
        raw = (m.group(1) or m.group(2)).replace(",", "")
        return ("money", Decimal(raw))
    m = _PERCENT_RE.search(value)
    if m:
        return ("percent", Decimal(m.group(1)))
    return None


# ---------------------------------------------------------------- 1. build reproducibility


def test_every_case_has_a_source_and_expected_facts_file() -> None:
    assert len(CASES) == 20, f"expected 20 hand-written cases, found {len(CASES)}: {CASES}"
    for case in CASES:
        assert (SRC_DIR / f"{case}.md").exists()
        assert (ROOT / "eval" / "expected" / f"{case}.json").exists()


@pytest.mark.parametrize("case", CASES)
def test_rebuild_reproduces_the_committed_folder_byte_for_byte(case: str, tmp_path: Path) -> None:
    BUILD.build_case(SRC_DIR / f"{case}.md", tmp_path)
    committed = DATA_DIR / case
    rebuilt = tmp_path / case
    committed_names = sorted(p.name for p in committed.iterdir())
    rebuilt_names = sorted(p.name for p in rebuilt.iterdir())
    assert committed_names == rebuilt_names, f"{case}: file list changed on rebuild"
    _, mismatched, errors = filecmp.cmpfiles(committed, rebuilt, committed_names, shallow=False)
    assert not mismatched, f"{case}: rebuild differs from the committed files: {mismatched}"
    assert not errors, f"{case}: rebuild comparison errors: {errors}"


# ---------------------------------------------------------------- 2. fixture consistency


@pytest.fixture(scope="module")
def sources() -> dict[str, dict]:
    return {
        case: {
            "account_ids": _account_ids(case),
            "account_values": _account_values(case),
            "owners": _account_owners(case),
            "all_text": _all_source_text(case),
        }
        for case in CASES
    }


@pytest.mark.parametrize("case", CASES)
def test_fixture_loads(case: str) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    assert isinstance(facts, ExpectedFacts)
    assert facts.client == case


@pytest.mark.parametrize("case", FAILED_CASES)
def test_failed_cases_have_a_reason_and_no_draft_content(case: str) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    assert facts.release.state == "failed"
    assert facts.release.reason
    assert facts.table_rows == []
    assert facts.markers == []
    assert facts.reportable_figures == []
    assert facts.actions == []


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_draft_cases_are_released_as_draft(case: str) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    assert facts.release.state == "draft"


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_table_accounts_exist_or_are_new_or_unresolved(case: str, sources: dict) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    ids = sources[case]["account_ids"]
    for row in facts.table_rows:
        assert (
            row.account in ids
            or row.account.startswith("new:")
            or row.account.startswith("unresolved:")
        ), f"{case}: table row {row.account!r} is neither a real, 'new:' nor 'unresolved:' account"


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_not_in_table_accounts_exist(case: str, sources: dict) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    ids = sources[case]["account_ids"]
    for row in facts.not_in_table:
        assert row.account in ids, f"{case}: not-in-table account {row.account!r} isn't real"


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_table_owners_match_account_data(case: str, sources: dict) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    owners_by_id = sources[case]["owners"]
    for row in facts.table_rows:
        if row.account.startswith("new:") or row.account.startswith("unresolved:"):
            continue
        expected = owners_by_id[row.account]
        assert set(row.owners) == expected, (
            f"{case}: {row.account} owners {row.owners} != account data {expected}"
        )


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_reportable_figures_are_grounded(case: str, sources: dict) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    known_money = _money_amounts(sources[case]["all_text"]) | sources[case]["account_values"]
    known_percent = _percentages(sources[case]["all_text"])
    by_value = {f.value: f for f in facts.reportable_figures}

    for fig in facts.reportable_figures:
        parsed = _figure_number(fig.value)
        assert parsed is not None, f"{case}: reportable figure {fig.value!r} has no number in it"
        kind, number = parsed
        pool = known_money if kind == "money" else known_percent
        if number in pool:
            continue

        assert fig.derived_from, (
            f"{case}: {fig.value!r} isn't a source or db value and has no derived_from"
        )
        inputs = []
        for ref in fig.derived_from:
            ref_fig = by_value.get(ref)
            assert ref_fig is not None, f"{case}: derived_from {ref!r} isn't itself a listed figure"
            ref_parsed = _figure_number(ref)
            assert ref_parsed is not None
            inputs.append(ref_parsed[1])
        matches_sum = number == sum(inputs)
        matches_difference = len(inputs) == 2 and number == inputs[0] - inputs[1]
        assert matches_sum or matches_difference, (
            f"{case}: {fig.value!r} ({number}) doesn't equal the sum or difference of "
            f"derived_from {fig.derived_from} ({inputs})"
        )


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_evidence_quotes_occur_in_sources(case: str, sources: dict) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    all_text = sources[case]["all_text"]

    quotes: list[str] = []
    quotes += [o.evidence_quote for o in facts.extraction.value_observations]
    quotes += [m.evidence_quote for m in facts.extraction.money_items]
    quotes += [d.evidence_quote for d in facts.extraction.disposals]
    quotes += [a.evidence_quote for a in facts.extraction.open_actions]
    quotes += [c.source_quote for c in facts.material_claims if c.source_quote]

    for quote in quotes:
        assert _quote_in(quote, all_text), f"{case}: quote not found verbatim: {quote!r}"


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_must_not_appear_is_empty_with_no_general_document(case: str) -> None:
    """These cases have no platform-update-style general document, so nothing can be a
    verified general-document distractor (T2's fixtures already cover that check)."""
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    assert facts.must_not_appear == []


@pytest.mark.parametrize("case", DRAFT_CASES)
def test_investigation_expected_accounts_are_real(case: str, sources: dict) -> None:
    facts = load_expected(case, root=ROOT / "eval" / "expected")
    ids = sources[case]["account_ids"]
    for q in facts.investigation:
        if q.expected is not None:
            assert q.expected in ids, (
                f"{case}: investigation expected answer {q.expected!r} isn't a real account"
            )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
