"""Currency rendering leaks (verifier checkpoint on the missing-currency change), tests first.

A stated currency is normalised (`gbp` is GBP, so it renders as sterling and is not withheld),
and a value that will be withheld for its currency never reaches the review sheet as an
unlabelled figure ("UNKNOWN 18,000") -- the account's `currency` review item covers it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import Account, Value, render_table
from agent_pipeline.pipeline import _apply_values
from agent_pipeline.reconcile.values import select_values
from agent_pipeline.sources.adapters.json_accounts import AccountRecord


def test_a_lowercase_gbp_is_normalised_and_renders_as_sterling() -> None:
    value = select_values(Decimal("18000"), date(2026, 4, 30), " gbp ", [])
    assert value is not None
    assert value.currency == "GBP"
    assert render_table(value) == "£18,000"


def _account() -> Account:
    return Account(
        id="X-GIA",
        owners=["A Client"],
        type="General Investment Account",
        platform="Holloway",
        in_scope=True,
    )


def _record(currency: str | None) -> AccountRecord:
    return AccountRecord(
        account_id="X-GIA",
        type="General Investment Account",
        owner="Joint",
        status="open",
        value=Decimal("18000"),
        currency=currency,
        valuation_date=date(2026, 3, 15),
    )


def _live() -> Value:
    return Value(
        amount=Decimal("21000"),
        currency="GBP",
        precision="approximate",
        qualifier="around",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="around £21,000",
        selected_by="R3",
    )


def test_no_superseded_item_shows_a_value_with_an_unstated_currency() -> None:
    _, items = _apply_values({"X-GIA": _account()}, {"X-GIA": _record(None)}, {"X-GIA": [_live()]})
    assert all("UNKNOWN" not in item.detail for item in items)
    assert [i.kind for i in items] == []


def test_a_gbp_account_still_gets_its_superseded_item() -> None:
    _, items = _apply_values({"X-GIA": _account()}, {"X-GIA": _record("GBP")}, {"X-GIA": [_live()]})
    assert [i.kind for i in items] == ["superseded"]
    assert "£18,000" in items[0].detail
