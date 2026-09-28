"""T19: `_classify_disposals`/`_apply_proceeds_to_actions` -- P5's proceeds rule wired at
the pipeline layer: a full disposal with a stated destination counts its own R3-selected
value as proceeds, and funds a matching agreed action's fact with that same value, never a
separately re-extracted figure (client 02's GIA)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.schemas import Disposal, LabelEvidence, MoneyItem, Quote
from agent_pipeline.ledger import Account, Action, Value
from agent_pipeline.pipeline import _apply_proceeds_to_actions, _classify_disposals

_EVIDENCE = LabelEvidence(paragraph_id="p1", text="in full")


def _gia_value() -> Value:
    return Value(
        amount=Decimal("45000"),
        currency="GBP",
        precision="approximate",
        qualifier="a_little_over",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="a little over £45,000",
        selected_by="R3",
    )


def _gia_account() -> Account:
    return Account(
        id="H-GIA-J",
        owners=["David Clarke", "Susan Clarke"],
        type="General Investment Account",
        platform="Holloway",
        in_scope=True,
        value=_gia_value(),
    )


def _full_disposal() -> Disposal:
    return Disposal(
        account_reference="General Investment Account",
        quote=Quote(paragraph_id="p1", text="disinvest the joint GIA in full"),
        extent="full",
        extent_evidence=_EVIDENCE,
    )


def _proceeds_money_item() -> MoneyItem:
    return MoneyItem(
        money_class="proceeds",
        purpose="to top up both ISAs",
        class_evidence=_EVIDENCE,
    )


def test_full_disposal_with_a_stated_destination_is_counted_as_proceeds() -> None:
    account = _gia_account()
    disposals, money_items, proceeds_by_account = _classify_disposals(
        [_full_disposal()], [_proceeds_money_item()], [account], "meeting_notes.docx"
    )

    assert [d.wrapper_class for d in disposals] == ["taxable"]
    assert len(money_items) == 1
    assert money_items[0].counted is True
    assert money_items[0].amount == account.value
    assert proceeds_by_account == {"H-GIA-J": account.value}


def test_no_proceeds_money_item_means_destination_unclear_and_not_counted() -> None:
    account = _gia_account()
    _, money_items, proceeds_by_account = _classify_disposals(
        [_full_disposal()], [], [account], "meeting_notes.docx"
    )

    assert money_items[0].counted is False
    assert proceeds_by_account == {}


def test_proceeds_fund_the_matching_actions_fact_not_a_reextracted_quote() -> None:
    account = _gia_account()
    gia_value = _gia_value()
    action = Action(
        id="a1",
        description="disinvest the GIA and top up both ISAs",
        accounts=["General Investment Account", "Stocks & Shares ISA"],
    )
    action_amounts: dict[str, Value] = {}

    _apply_proceeds_to_actions([action], action_amounts, [account], {"H-GIA-J": gia_value})

    assert action_amounts == {"a1": gia_value}


def test_an_action_with_its_own_amount_already_is_never_overwritten() -> None:
    account = _gia_account()
    existing = Value(
        amount=Decimal("20000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=None,
        source_id="meeting_notes.docx",
        quote="£20,000",
        selected_by="action_amount",
    )
    action = Action(id="a1", description="top up the ISA", accounts=["Stocks & Shares ISA"])
    action_amounts = {"a1": existing}

    _apply_proceeds_to_actions([action], action_amounts, [account], {"H-GIA-J": _gia_value()})

    assert action_amounts == {"a1": existing}
