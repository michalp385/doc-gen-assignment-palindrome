"""Fixes from the independent review of the hand-written-case rules (tests first).

Each test pins a misfire the review found on a held-out shape:
- R8 must recognise wording variants of an account type the client does hold, and must not split
  "Stocks and Shares" in two;
- R4's marker must reach the report even when no tax section is included;
- an R5 conflict's dropped amount must not be refilled by the proceeds step;
- R5 compares only a funding action against the instruction's amount;
- a stated proceeds amount is attributed only to a single, sole disposal, and is checked for
  currency and size;
- an R9 disagreement blocks only for an account the report covers;
- "within" excludes a change made inside an account, not a subscription within an allowance.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.schemas import LabelEvidence, MoneyItem, Quote
from agent_pipeline.ledger import Account, Action, Value
from agent_pipeline.pipeline import (
    _apply_proceeds_to_actions,
    _apply_values,
    _reconcile_instruction_amount,
)
from agent_pipeline.reconcile.decisions import check_selling_decision
from agent_pipeline.reconcile.meetings import govern_meeting_records
from agent_pipeline.reconcile.money import attributable_stated_amount
from agent_pipeline.reconcile.scope_parts import unresolved_scope_parts
from agent_pipeline.reconcile.unspecified_amounts import build_unspecified_amounts
from agent_pipeline.sources.adapters.json_accounts import AccountRecord


def _acct(type_: str, account_id: str = "A-1") -> Account:
    return Account(id=account_id, type=type_, owners=["P N"], platform="H", in_scope=True)


def _value(amount: str, currency: str = "GBP", precision: str = "exact") -> Value:
    return Value(
        amount=Decimal(amount),
        currency=currency,
        precision=precision,  # type: ignore[arg-type]  # the test passes the literal by name
        qualifier="exact" if precision == "exact" else "around",
        date=None,
        source_id="m",
        quote="q",
        selected_by="P5",
    )


# --- M1: R8 wording variants -----------------------------------------------------------------


def test_r8_recognises_wording_variants_of_a_type_the_client_holds() -> None:
    cases = [
        ("Stocks and Shares ISA", "Holloway Stocks & Shares ISA"),
        ("GIA", "the General Investment Account"),
        ("Personal Pension Plan", "her Personal Pension"),
        ("Self-Invested Personal Pension (SIPP)", "his SIPP"),
    ]
    for held, phrase in cases:
        assert unresolved_scope_parts(phrase, [_acct(held)], ["P N"]) == [], (held, phrase)


def test_r8_does_not_split_stocks_and_shares_in_two() -> None:
    parts = unresolved_scope_parts(
        "Holloway Stocks and Shares ISA and her Personal Pension",
        [_acct("Stocks & Shares ISA")],
        [],
    )
    assert [p.type_text for p in parts] == ["Personal Pension"]


def test_r8_still_flags_a_type_the_client_really_does_not_hold() -> None:
    [part] = unresolved_scope_parts("her Personal Pension", [_acct("Stocks & Shares ISA")], [])
    assert part.type_text == "Personal Pension"


# --- M2: R4's marker must reach the report --------------------------------------------------


def test_the_selling_marker_is_placed_in_recommendations_which_always_exists() -> None:
    result = check_selling_decision(
        "Selling existing investments?", "No", ["We agreed to sell it."]
    )
    assert result.marker is not None and result.marker.section == "recommendations"


# --- M3: an R5 conflict's dropped amount is not refilled -------------------------------------


def test_a_skipped_action_is_not_refilled_from_proceeds() -> None:
    isa = _acct("Stocks & Shares ISA", "I-1")
    gia = _acct("General Investment Account", "G-1")
    action = Action(
        id="a1",
        description="sell the GIA and top up the ISA",
        kind="action",
        accounts=["General Investment Account", "Stocks & Shares ISA"],
        quote="q",
    )
    proceeds = {"G-1": _value("40000")}
    amounts: dict[str, Value] = {}
    assert (
        _apply_proceeds_to_actions([action], amounts, [isa, gia], proceeds, skip_ids={"a1"})
        == set()
    )
    assert amounts == {}
    assert _apply_proceeds_to_actions([action], amounts, [isa, gia], proceeds) == {"a1"}


# --- M4: R5 compares a funding action only ---------------------------------------------------


def test_r5_ignores_an_action_that_is_not_funding() -> None:
    action = Action(
        id="a1",
        description="review the ISA",
        kind="action",
        accounts=["Stocks & Shares ISA"],
        quote="q",
    )
    amounts = {"a1": _value("15000", precision="approximate")}
    result = _reconcile_instruction_amount(
        [action], amounts, [_acct("Stocks & Shares ISA")], [_value("12000")]
    )
    assert result == ([], []) and "a1" in amounts


# --- A1/A2: a stated proceeds amount ---------------------------------------------------------


def _proceeds_item(text: str) -> MoneyItem:
    return MoneyItem(
        money_class="proceeds",
        purpose="sale",
        amount=Quote(paragraph_id="p1", text=text),
        class_evidence=LabelEvidence(paragraph_id="p1", text="proceeds"),
    )


def test_a_stated_amount_needs_exactly_one_matched_disposal_and_none_unmatched() -> None:
    items = [_proceeds_item("£10,000")]
    kw = {"account_value": _value("60000")}
    assert (
        attributable_stated_amount(items, "m", matched_disposals=1, unmatched=0, **kw) is not None
    )
    assert attributable_stated_amount(items, "m", matched_disposals=2, unmatched=0, **kw) is None
    assert attributable_stated_amount(items, "m", matched_disposals=1, unmatched=1, **kw) is None
    assert attributable_stated_amount(items, "m", matched_disposals=0, unmatched=0, **kw) is None


def test_a_stated_amount_must_be_sterling_and_no_larger_than_the_account() -> None:
    kw = {"matched_disposals": 1, "unmatched": 0}
    assert (
        attributable_stated_amount(
            [_proceeds_item("€10,000")], "m", account_value=_value("60000"), **kw
        )
        is None
    )
    assert (
        attributable_stated_amount(
            [_proceeds_item("£90,000")], "m", account_value=_value("60000"), **kw
        )
        is None
    )
    assert (
        attributable_stated_amount([_proceeds_item("£10,000")], "m", account_value=None, **kw)
        is not None
    )


# --- A3: R9 blocks only for an account the report covers --------------------------------------


def _record(value: str) -> AccountRecord:
    return AccountRecord(
        account_id="J-1",
        type="General Investment Account",
        owner="Joint",
        status="open",
        value=Decimal(value),
        currency="GBP",
        valuation_date=date(2026, 4, 15),
    )


def test_an_out_of_scope_joint_disagreement_does_not_block() -> None:
    out = Account(id="J-1", type="General Investment Account", owners=["A", "B"], in_scope=False)
    _, items = _apply_values({"J-1": out}, {"J-1": _record("1")}, {}, {"J-1": [_record("2")]})
    [item] = items
    assert item.kind == "conflict" and not item.blocking


# --- A4: "within" -----------------------------------------------------------------------------


def _markers(description: str) -> list[str]:
    isa = _acct("Stocks & Shares ISA", "I-1")
    action = Action(
        id="a1",
        description=description,
        kind="action",
        accounts=["Stocks & Shares ISA"],
        quote=description,
    )
    return [
        m.key
        for m in build_unspecified_amounts(
            [action],
            {},
            [isa],
            partial_disposals=[],
            disposal_quotes=[],
            other_unspecified=0,
            taken_keys=set(),
            available=None,
        ).markers
    ]


def test_a_subscription_within_an_allowance_is_still_a_funding_action() -> None:
    assert _markers("subscribe to the ISA within this year's allowance") == ["isa_amounts"]
    assert _markers("fund the ISA within the tax year") == ["isa_amounts"]


def test_a_change_within_an_account_is_still_not_funding() -> None:
    assert _markers("switch the funds within the ISA") == []
    assert _markers("move holdings within her ISA") == []


# --- A5: R10 same-date tie --------------------------------------------------------------------


def test_two_records_on_the_latest_date_fall_back_to_input_order() -> None:
    day = date(2026, 5, 1)
    assert govern_meeting_records([date(2026, 4, 1), day, day]) == (2, [0, 1])
