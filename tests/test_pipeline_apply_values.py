"""T19: `_apply_values` wires R3's `select_values`/`superseded_values` together with the
review-sheet item G15 needs -- the account gets its selected value and superseded list,
and any account with a superseded candidate gets a `"superseded"`-kind review item quoting
both the superseded and current values with their dates (SCOPING.md R3, client 02's GIA)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import Account, Value
from agent_pipeline.pipeline import _apply_values
from agent_pipeline.sources.adapters.json_accounts import AccountRecord


def _gia_account() -> Account:
    return Account(
        id="H-GIA-J",
        owners=["David Clarke", "Susan Clarke"],
        type="General Investment Account",
        platform="Holloway",
        in_scope=True,
    )


def _gia_record() -> AccountRecord:
    return AccountRecord(
        account_id="H-GIA-J",
        type="General Investment Account",
        owner="Joint",
        status="open",
        value=Decimal("40000"),
        currency="GBP",
        valuation_date=date(2026, 3, 15),
    )


def _live_value() -> Value:
    return Value(
        amount=Decimal("45000"),
        currency="GBP",
        precision="approximate",
        qualifier="a_little_over",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="a little over £45,000",
        selected_by="",
    )


def test_a_later_viewed_value_supersedes_the_snapshot_with_a_review_item() -> None:
    account = _gia_account()
    accounts, items = _apply_values(
        {account.id: account},
        {account.id: _gia_record()},
        {account.id: [_live_value()]},
    )

    updated = accounts[account.id]
    assert updated.value is not None
    assert updated.value.amount == Decimal("45000")
    assert len(updated.superseded) == 1
    assert updated.superseded[0].amount == Decimal("40000")

    assert len(items) == 1
    assert items[0].kind == "superseded"
    assert items[0].blocking is False
    assert items[0].refs == ["H-GIA-J"]
    for term in ("£40,000", "15 March", "c. £45,000", "14 May"):
        assert term in items[0].detail


def test_no_review_item_when_theres_only_one_candidate() -> None:
    account = _gia_account()
    accounts, items = _apply_values({account.id: account}, {account.id: _gia_record()}, {})

    updated = accounts[account.id]
    assert updated.value is not None
    assert updated.value.amount == Decimal("40000")
    assert updated.superseded == []
    assert items == []


def test_an_account_with_no_matching_record_is_left_untouched() -> None:
    account = _gia_account()
    accounts, items = _apply_values({account.id: account}, {}, {})

    assert accounts[account.id] is account
    assert items == []
