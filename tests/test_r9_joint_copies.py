"""R9: disagreeing copies of a joint account (tests first; hand-written cases 03 and 04).

SCOPING R9: a joint account appears under each holder. If the copies disagree on the same date
the value is unresolved -- never a silent pick -- so the value cell becomes a marker and the
adviser gets a blocking conflict naming both figures and the date. If they disagree on
different dates the later copy wins and the earlier is superseded (the table footnote), exactly
like any two dated figures under R3. Identical copies are one answer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import Account
from agent_pipeline.pipeline import _apply_account_states, _apply_values, _tied_account_ids
from agent_pipeline.sources.adapters.json_accounts import AccountRecord

DAY = date(2026, 4, 15)


def _account() -> Account:
    return Account(
        id="J-GIA",
        owners=["Ann Bell", "Bob Bell"],
        type="General Investment Account",
        platform="Alpha",
        in_scope=True,
    )


def _record(value: str, day: date = DAY) -> AccountRecord:
    return AccountRecord(
        account_id="J-GIA",
        type="General Investment Account",
        owner="Joint",
        status="open",
        value=Decimal(value),
        currency="GBP",
        valuation_date=day,
    )


def test_same_date_disagreeing_copies_select_nothing_and_raise_a_blocking_conflict() -> None:
    accounts, items = _apply_values(
        {"J-GIA": _account()},
        {"J-GIA": _record("61000")},
        {},
        {"J-GIA": [_record("63000")]},
    )
    assert accounts["J-GIA"].value is None
    (item,) = items
    assert item.kind == "conflict" and item.blocking and item.refs == ["J-GIA"]
    assert "£61,000" in item.detail and "£63,000" in item.detail
    assert "15 April 2026" in item.detail
    assert "before anything is finalised" in item.detail


def test_a_later_dated_copy_wins_and_the_earlier_is_superseded() -> None:
    accounts, items = _apply_values(
        {"J-GIA": _account()},
        {"J-GIA": _record("61000", date(2026, 3, 1))},
        {},
        {"J-GIA": [_record("63000", date(2026, 4, 15))]},
    )
    assert accounts["J-GIA"].value is not None
    assert accounts["J-GIA"].value.amount == Decimal("63000")
    assert [s.amount for s in accounts["J-GIA"].superseded] == [Decimal("61000")]
    assert [i.kind for i in items] == ["superseded"]


def test_identical_copies_are_one_answer() -> None:
    accounts, items = _apply_values(
        {"J-GIA": _account()},
        {"J-GIA": _record("61000")},
        {},
        {"J-GIA": [_record("61000")]},
    )
    assert accounts["J-GIA"].value is not None and items == []


def test_no_other_copies_changes_nothing() -> None:
    accounts, items = _apply_values({"J-GIA": _account()}, {"J-GIA": _record("61000")}, {})
    assert accounts["J-GIA"].value is not None and items == []


def test_tied_accounts_are_found_from_the_same_candidates() -> None:
    tied = _tied_account_ids(
        {"J-GIA": _account()},
        {"J-GIA": _record("61000")},
        {},
        {"J-GIA": [_record("63000")]},
    )
    assert tied == {"J-GIA"}
    assert _tied_account_ids({"J-GIA": _account()}, {"J-GIA": _record("61000")}, {}, {}) == set()


def test_a_tie_becomes_a_conflict_named_value_cell_marker_without_a_no_value_row() -> None:
    accounts, _ = _apply_values(
        {"J-GIA": _account()},
        {"J-GIA": _record("61000")},
        {},
        {"J-GIA": [_record("63000")]},
    )
    updated, markers, review = _apply_account_states(
        list(accounts.values()), {"J-GIA": "GBP"}, tied_ids=frozenset({"J-GIA"})
    )
    assert updated[0].value is None
    assert [m.key for m in markers] == ["gia_same_date_conflict_value"]
    assert review == []  # the blocking conflict already tells the adviser; no "no value" row
