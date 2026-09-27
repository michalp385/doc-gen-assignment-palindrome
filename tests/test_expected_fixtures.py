"""Consistency checks for eval/expected/<client>.json against data/<client>/ (T2).

These tests hold no client values themselves: every client-specific figure, name or
quote lives in the fixture or the source files under data/, never here (this file is
generic across clients, unlike the fixtures it checks).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from document_formatter.loading import read_file
from report_eval.expected import ExpectedFacts, load_expected

DATA_ROOT = Path("data")
EXPECTED_ROOT = Path("eval/expected")

REAL_CLIENTS = sorted(
    p.name for p in DATA_ROOT.iterdir() if p.is_dir() and (p / "client_data_db.json").exists()
)

GENERAL_DOCUMENT_NAMES = {"platform_market_update.docx", "portfolio_pack.docx"}
TEXT_SUFFIXES = {".docx", ".md"}

_MONEY_RE = re.compile(r"£\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)|GBP\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _account_ids(client: str) -> set[str]:
    db = json.loads((DATA_ROOT / client / "client_data_db.json").read_text(encoding="utf-8"))
    ids = set()
    for holder in db.get("holders", {}).values():
        for acc in holder.get("accounts", []):
            ids.add(acc["account_id"])
    return ids


def _account_values(client: str) -> set[Decimal]:
    db = json.loads((DATA_ROOT / client / "client_data_db.json").read_text(encoding="utf-8"))
    values = set()
    for holder in db.get("holders", {}).values():
        for acc in holder.get("accounts", []):
            if isinstance(acc.get("value"), (int, float)):
                values.add(Decimal(str(acc["value"])))
    return values


def _account_owners(client: str) -> dict[str, set[str]]:
    """account_id -> the set of holder names whose record contains it (R1, R9)."""
    db = json.loads((DATA_ROOT / client / "client_data_db.json").read_text(encoding="utf-8"))
    owners: dict[str, set[str]] = {}
    for holder in db.get("holders", {}).values():
        name = holder["name"]
        for acc in holder.get("accounts", []):
            owners.setdefault(acc["account_id"], set()).add(name)
    return owners


def _text_files(client: str) -> list[Path]:
    return sorted(
        p for p in (DATA_ROOT / client).iterdir() if p.is_file() and p.suffix in TEXT_SUFFIXES
    )


def _all_source_text(client: str) -> str:
    return "\n".join(read_file(p) for p in _text_files(client))


def _general_document_text(client: str) -> str:
    return "\n".join(read_file(p) for p in _text_files(client) if p.name in GENERAL_DOCUMENT_NAMES)


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
    """Parse a reportable figure's rendered string into (kind, number)."""
    m = _MONEY_RE.search(value)
    if m:
        raw = (m.group(1) or m.group(2)).replace(",", "")
        return ("money", Decimal(raw))
    m = _PERCENT_RE.search(value)
    if m:
        return ("percent", Decimal(m.group(1)))
    return None


@pytest.fixture(scope="module")
def sources() -> dict[str, dict]:
    """Per-client: account ids, account values, owners, all-source text, general-doc text."""
    return {
        client: {
            "account_ids": _account_ids(client),
            "account_values": _account_values(client),
            "owners": _account_owners(client),
            "all_text": _all_source_text(client),
            "general_text": _general_document_text(client),
        }
        for client in REAL_CLIENTS
    }


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_fixture_loads(client: str) -> None:
    facts = load_expected(client)
    assert isinstance(facts, ExpectedFacts)
    assert facts.client == client


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_table_accounts_exist_or_are_new(client: str, sources: dict) -> None:
    facts = load_expected(client)
    ids = sources[client]["account_ids"]
    for row in facts.table_rows:
        assert row.account in ids or row.account.startswith("new:"), (
            f"{client}: table row {row.account!r} is neither a real account nor a 'new:' one"
        )


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_not_in_table_accounts_exist(client: str, sources: dict) -> None:
    facts = load_expected(client)
    ids = sources[client]["account_ids"]
    for row in facts.not_in_table:
        assert row.account in ids, f"{client}: not-in-table account {row.account!r} isn't real"


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_table_owners_match_account_data(client: str, sources: dict) -> None:
    facts = load_expected(client)
    owners_by_id = sources[client]["owners"]
    for row in facts.table_rows:
        if row.account.startswith("new:"):
            continue
        expected = owners_by_id[row.account]
        assert set(row.owners) == expected, (
            f"{client}: {row.account} owners {row.owners} != account data {expected}"
        )


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_reportable_figures_are_grounded(client: str, sources: dict) -> None:
    """Every reportable figure is a real source or db value, or a stated calculation over them."""
    facts = load_expected(client)
    known_money = _money_amounts(sources[client]["all_text"]) | sources[client]["account_values"]
    known_percent = _percentages(sources[client]["all_text"])
    by_value = {f.value: f for f in facts.reportable_figures}

    for fig in facts.reportable_figures:
        parsed = _figure_number(fig.value)
        assert parsed is not None, f"{client}: reportable figure {fig.value!r} has no number in it"
        kind, number = parsed
        pool = known_money if kind == "money" else known_percent

        if number in pool:
            continue

        assert fig.derived_from, (
            f"{client}: {fig.value!r} isn't a source or db value and has no derived_from"
        )
        inputs = []
        for ref in fig.derived_from:
            ref_fig = by_value.get(ref)
            assert ref_fig is not None, (
                f"{client}: derived_from {ref!r} isn't itself a listed figure"
            )
            ref_parsed = _figure_number(ref)
            assert ref_parsed is not None
            inputs.append(ref_parsed[1])

        matches_sum = number == sum(inputs)
        matches_difference = len(inputs) == 2 and number == inputs[0] - inputs[1]
        assert matches_sum or matches_difference, (
            f"{client}: {fig.value!r} ({number}) doesn't equal the sum or difference of "
            f"derived_from {fig.derived_from} ({inputs})"
        )


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_must_not_appear_occurs_in_a_general_document(client: str, sources: dict) -> None:
    facts = load_expected(client)
    general_text = sources[client]["general_text"]
    for phrase in facts.must_not_appear:
        assert _quote_in(phrase, general_text), (
            f"{client}: must_not_appear phrase {phrase!r} isn't actually in a general document"
        )


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_evidence_quotes_occur_in_sources(client: str, sources: dict) -> None:
    facts = load_expected(client)
    all_text = sources[client]["all_text"]

    quotes: list[str] = []
    quotes += [o.evidence_quote for o in facts.extraction.value_observations]
    quotes += [m.evidence_quote for m in facts.extraction.money_items]
    quotes += [d.evidence_quote for d in facts.extraction.disposals]
    quotes += [a.evidence_quote for a in facts.extraction.open_actions]
    quotes += [c.source_quote for c in facts.material_claims if c.source_quote]

    assert quotes, f"{client}: no evidence quotes to check (fixture likely incomplete)"
    for quote in quotes:
        assert _quote_in(quote, all_text), f"{client}: quote not found verbatim: {quote!r}"


@pytest.mark.parametrize("client", REAL_CLIENTS)
def test_release_state_is_draft_for_the_four_real_clients(client: str) -> None:
    facts = load_expected(client)
    assert facts.release.state == "draft"
