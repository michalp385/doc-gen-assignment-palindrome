"""T20/T21: `_apply_account_states` wires R6/P12's `check_account_states` onto the ledger's
accounts -- a value marker on the account, a withheld (foreign-currency) value cleared so it
can never reach a fact, a closed-in-scope account taken out of scope with a blocking
conflict, and the markers and review items handed back for the ledger."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import Account, Value
from agent_pipeline.pipeline import _apply_account_states


def _value(currency: str = "GBP") -> Value:
    return Value(
        amount=Decimal("18000"),
        currency=currency,
        precision="exact",
        qualifier="exact",
        date=date(2026, 5, 1),
        source_id="client_data_db.json",
        quote="",
        selected_by="R3",
    )


def _account(account_id: str, type_: str, **update: object) -> Account:
    return Account(id=account_id, owners=["A Client"], type=type_, platform="Holloway").model_copy(
        update={"in_scope": True, **update}
    )


def test_untouched_accounts_pass_through_unchanged() -> None:
    account = _account("A-ISA", "Stocks & Shares ISA", value=_value())
    accounts, markers, items = _apply_account_states([account], {"A-ISA": "GBP"})
    assert accounts == [account]
    assert markers == []
    assert items == []


def test_null_in_scope_account_gets_its_value_marker_key_on_the_account() -> None:
    account = _account("A-SIPP", "SIPP")
    accounts, markers, items = _apply_account_states([account], {"A-SIPP": "GBP"})
    (marker,) = markers
    assert accounts[0].value_marker == marker.key == "sipp_value"
    assert accounts[0].in_scope is True
    assert [i.kind for i in items] == ["open_action"]


def test_foreign_currency_value_is_cleared_so_no_fact_can_carry_it() -> None:
    superseded = _value("EUR")
    account = _account(
        "A-GIA",
        "General Investment Account",
        value=_value("EUR"),
        superseded=[superseded],
    )
    accounts, markers, _ = _apply_account_states([account], {"A-GIA": "EUR"})
    assert accounts[0].value is None
    assert accounts[0].superseded == []
    assert accounts[0].value_marker == markers[0].key


def test_closed_in_scope_account_leaves_scope_with_a_blocking_conflict() -> None:
    account = _account("A-OLD", "Cash Account", status="closed", value=_value())
    accounts, markers, items = _apply_account_states([account], {"A-OLD": "GBP"})
    assert accounts[0].in_scope is False
    assert accounts[0].value is None  # R6: a closed account is never given a value
    assert accounts[0].scope_reason is not None and "closed" in accounts[0].scope_reason
    assert markers == []
    assert [(i.kind, i.blocking) for i in items] == [("conflict", True)]


def test_closed_out_of_scope_account_is_ignored_and_never_given_a_value() -> None:
    account = _account("A-OLD", "Cash Account", status="closed", in_scope=False, value=_value())
    accounts, markers, items = _apply_account_states([account], {"A-OLD": "GBP"})
    assert accounts[0].value is None
    assert accounts[0].in_scope is False
    assert markers == []
    assert items == []


def test_out_of_scope_foreign_currency_value_is_withheld_from_the_ledger() -> None:
    account = _account("A-GIA", "General Investment Account", in_scope=False, value=_value("EUR"))
    accounts, markers, items = _apply_account_states([account], {"A-GIA": "EUR"})
    assert accounts[0].value is None
    assert markers == []
    assert items == []


def test_account_order_is_preserved() -> None:
    first = _account("A-1", "Stocks & Shares ISA", value=_value())
    second = _account("A-2", "SIPP")
    accounts, _, _ = _apply_account_states([first, second], {"A-1": "GBP", "A-2": "GBP"})
    assert [a.id for a in accounts] == ["A-1", "A-2"]
