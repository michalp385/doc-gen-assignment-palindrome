"""R3's same-date tie (tests first).

"The most recent dated figure wins" has no answer when two candidates carry the same latest
date and different amounts -- the account data's snapshot and a figure viewed in the meeting
on that same day, or two figures viewed at once. `max` used to take the first, silently the
account-data figure. Following R9 (same-date, different-value joint copies are unresolved: the
value cell is a marker), such a tie now selects nothing, and the review sheet gets a conflict
naming the candidates. Candidates that agree on the amount are not a tie.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.ledger import Account, Value
from agent_pipeline.pipeline import _apply_account_states, _apply_values
from agent_pipeline.reconcile.values import select_values, superseded_values, tied_candidates
from agent_pipeline.sources.adapters.json_accounts import AccountRecord

MEETING = date(2026, 5, 14)
SNAPSHOT = date(2026, 4, 30)


def _viewed(text: str, day: date | None = MEETING, source: str = "meeting_notes.docx") -> Value:
    parsed = parse_amount(text)
    assert parsed is not None
    return Value(
        amount=parsed.amount,
        currency=parsed.currency,
        precision=parsed.precision,
        qualifier=parsed.qualifier,
        date=day,
        source_id=source,
        quote=text,
        selected_by="R3",
    )


def test_a_same_date_disagreement_selects_nothing() -> None:
    viewed = [_viewed("around £45,000")]
    assert select_values(Decimal("40000"), MEETING, "GBP", viewed) is None


def test_the_tied_candidates_are_reported() -> None:
    viewed = [_viewed("around £45,000")]
    tied = tied_candidates(Decimal("40000"), MEETING, "GBP", viewed)
    assert sorted(v.amount for v in tied) == [Decimal("40000"), Decimal("45000")]


def test_nothing_is_superseded_when_nothing_is_selected() -> None:
    viewed = [_viewed("around £45,000")]
    assert superseded_values(Decimal("40000"), MEETING, "GBP", viewed, None) == []


def test_two_figures_viewed_on_the_same_day_that_differ_are_a_tie() -> None:
    viewed = [_viewed("around £45,000"), _viewed("around £47,000")]
    assert select_values(Decimal("40000"), SNAPSHOT, "GBP", viewed) is None
    assert len(tied_candidates(Decimal("40000"), SNAPSHOT, "GBP", viewed)) == 2


def test_a_later_date_still_wins_with_no_tie() -> None:
    viewed = [_viewed("around £45,000")]
    selected = select_values(Decimal("40000"), SNAPSHOT, "GBP", viewed)
    assert selected is not None and selected.amount == Decimal("45000")
    assert tied_candidates(Decimal("40000"), SNAPSHOT, "GBP", viewed) == []


def test_an_earlier_viewed_figure_still_loses_to_the_snapshot() -> None:
    viewed = [_viewed("around £45,000", day=date(2026, 3, 1))]
    selected = select_values(Decimal("40000"), SNAPSHOT, "GBP", viewed)
    assert selected is not None and selected.amount == Decimal("40000")


def test_candidates_that_agree_on_the_amount_are_not_a_tie_and_the_exact_one_is_used() -> None:
    viewed = [_viewed("around £40,000")]
    selected = select_values(Decimal("40000"), MEETING, "GBP", viewed)
    assert selected is not None
    assert selected.amount == Decimal("40000")
    assert selected.precision == "exact"
    assert tied_candidates(Decimal("40000"), MEETING, "GBP", viewed) == []


def test_the_same_number_in_different_currencies_is_a_tie() -> None:
    viewed = [_viewed("€40,000")]
    assert select_values(Decimal("40000"), MEETING, "GBP", viewed) is None


def test_an_undated_meeting_figure_never_ties_with_a_dated_snapshot() -> None:
    viewed = [_viewed("around £45,000", day=None)]
    selected = select_values(Decimal("40000"), SNAPSHOT, "GBP", viewed)
    assert selected is not None and selected.amount == Decimal("40000")


def test_two_undated_figures_with_an_undated_snapshot_that_differ_are_a_tie() -> None:
    viewed = [_viewed("around £45,000", day=None)]
    assert select_values(Decimal("40000"), None, "GBP", viewed) is None


def test_a_single_candidate_and_no_candidate_are_not_ties() -> None:
    assert tied_candidates(Decimal("40000"), MEETING, "GBP", []) == []
    assert tied_candidates(None, None, "GBP", []) == []


# --- the stage graph -------------------------------------------------------------------------


def _account() -> Account:
    return Account(
        id="X-GIA",
        owners=["A Client"],
        type="General Investment Account",
        platform="Holloway",
        in_scope=True,
    )


def _record(currency: str | None = "GBP") -> AccountRecord:
    return AccountRecord(
        account_id="X-GIA",
        type="General Investment Account",
        owner="Joint",
        status="open",
        value=Decimal("40000"),
        currency=currency,
        valuation_date=MEETING,
    )


def test_a_tie_leaves_the_account_valueless_with_a_conflict_naming_both_figures() -> None:
    accounts, items = _apply_values(
        {"X-GIA": _account()}, {"X-GIA": _record()}, {"X-GIA": [_viewed("around £45,000")]}
    )
    assert accounts["X-GIA"].value is None
    assert accounts["X-GIA"].superseded == []
    (item,) = items
    assert item.kind == "conflict"
    assert item.blocking is False
    assert item.refs == ["X-GIA"]
    assert "£40,000" in item.detail and "c. £45,000" in item.detail
    assert "14 May" in item.detail


def test_a_tie_becomes_a_value_cell_marker_never_a_pick() -> None:
    accounts, _ = _apply_values(
        {"X-GIA": _account()}, {"X-GIA": _record()}, {"X-GIA": [_viewed("around £45,000")]}
    )
    updated, markers, _ = _apply_account_states(list(accounts.values()), {"X-GIA": "GBP"})
    assert updated[0].value is None
    assert [m.key for m in markers] == ["gia_value"]


def test_a_tie_on_an_account_without_a_stated_currency_shows_no_figure() -> None:
    _, items = _apply_values(
        {"X-GIA": _account()}, {"X-GIA": _record(None)}, {"X-GIA": [_viewed("around £45,000")]}
    )
    assert all("UNKNOWN" not in i.detail for i in items)


def test_no_tie_no_conflict() -> None:
    _, items = _apply_values(
        {"X-GIA": _account()},
        {"X-GIA": _record().model_copy(update={"valuation_date": SNAPSHOT})},
        {"X-GIA": [_viewed("around £45,000")]},
    )
    assert [i.kind for i in items] == ["superseded"]
