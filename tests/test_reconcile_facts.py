"""T16: `reconcile/facts.py` builds `Ledger.facts{}` from reconciled data -- the one piece
nothing in reconcile/ built before now (every prior use of `facts{}` was hand-built directly
in a test or a T14/T15 live-check fixture). Tests first (deterministic code, CLAUDE.md).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import Account, Value
from agent_pipeline.reconcile.facts import account_value_fact, action_amount_fact, build_facts

MEETING_DATE = date(2026, 5, 12)


def _value(quote: str, amount: Decimal, source_id: str = "meeting_notes.docx") -> Value:
    return Value(
        amount=amount,
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=MEETING_DATE,
        source_id=source_id,
        quote=quote,
        selected_by="R3",
    )


def test_account_value_fact_id_kind_and_role():
    account = Account(
        id="H-ISA-01",
        owners=["Margaret Hughes"],
        type="Stocks & Shares ISA",
        platform="Holloway",
        in_scope=True,
        value=_value("£52,000", Decimal("52000"), source_id="client_data_db.json"),
    )
    fact = account_value_fact(account)
    assert fact is not None
    assert fact.id == "account.H-ISA-01.value"
    assert fact.kind == "money"
    assert fact.role == "account value"
    assert fact.reportable is True
    assert fact.transaction is False
    assert fact.value is account.value


def test_account_value_fact_description_has_no_digits():
    account = Account(
        id="H-ISA-01",
        owners=["Margaret Hughes"],
        type="Stocks & Shares ISA",
        in_scope=True,
        value=_value("£52,000", Decimal("52000")),
    )
    fact = account_value_fact(account)
    assert fact is not None
    assert not any(ch.isdigit() for ch in fact.description)


def test_account_value_fact_is_none_without_a_selected_value():
    account = Account(
        id="H-ISA-01", owners=["Margaret Hughes"], type="Stocks & Shares ISA", in_scope=True
    )
    assert account_value_fact(account) is None


def test_action_amount_fact_is_a_transaction_never_in_background():
    fact = action_amount_fact("a1", _value("£20,000", Decimal("20000")))
    assert fact.id == "action.a1.amount"
    assert fact.kind == "money"
    assert fact.role == "transaction"
    assert fact.reportable is True
    assert fact.transaction is True
    assert not any(ch.isdigit() for ch in fact.description)


def test_build_facts_keys_by_account_and_action_id():
    accounts = [
        Account(
            id="H-ISA-01",
            owners=["Margaret Hughes"],
            type="Stocks & Shares ISA",
            in_scope=True,
            value=_value("£52,000", Decimal("52000"), source_id="client_data_db.json"),
        ),
        Account(
            id="H-CASH-01",
            owners=["Margaret Hughes"],
            type="Cash Account",
            in_scope=False,
            value=_value("£8,000", Decimal("8000"), source_id="client_data_db.json"),
        ),
    ]
    action_amounts = {"a1": _value("£20,000", Decimal("20000"))}
    facts = build_facts(accounts, action_amounts)
    assert set(facts) == {"account.H-ISA-01.value", "account.H-CASH-01.value", "action.a1.amount"}
    assert facts["action.a1.amount"].transaction is True


def test_build_facts_skips_an_account_with_no_selected_value():
    accounts = [
        Account(id="H-NEW-01", owners=["Margaret Hughes"], type="Stocks & Shares ISA", is_new=True)
    ]
    facts = build_facts(accounts, {})
    assert facts == {}
