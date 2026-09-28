"""T17 verifier checkpoint: `_limit_review_items` must only match in-scope accounts -- an
earlier version matched every account regardless of scope, which could attach a P4 note to
an account absent from the report's own table, or let an out-of-scope account silently steal
the match from an in-scope one with the same type wording."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import Account, Action, Value
from agent_pipeline.pipeline import _limit_review_items

MEETING_DATE = date(2026, 5, 12)


def _isa_account(account_id: str, *, in_scope: bool) -> Account:
    return Account(
        id=account_id,
        owners=["Margaret Hughes"],
        type="Stocks & Shares ISA",
        platform="Holloway",
        in_scope=in_scope,
    )


def _top_up_action(account_ref: str) -> tuple[Action, dict[str, Value]]:
    action = Action(id="a1", description="top up", accounts=[account_ref])
    amount = Value(
        amount=Decimal("20000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=None,
        source_id="meeting_notes.docx",
        quote="£20,000",
        selected_by="action_amount",
    )
    return action, {action.id: amount}


def test_an_in_scope_account_gets_the_note() -> None:
    action, amounts = _top_up_action("Stocks & Shares ISA")
    account = _isa_account("H-ISA-01", in_scope=True)

    items = _limit_review_items([action], amounts, [account], MEETING_DATE)

    assert len(items) == 1
    assert items[0].refs == ["H-ISA-01"]


def test_an_out_of_scope_only_match_gets_no_note() -> None:
    action, amounts = _top_up_action("Stocks & Shares ISA")
    account = _isa_account("H-ISA-02", in_scope=False)

    items = _limit_review_items([action], amounts, [account], MEETING_DATE)

    assert items == []


def test_an_out_of_scope_account_never_steals_the_match_from_an_in_scope_one() -> None:
    action, amounts = _top_up_action("Stocks & Shares ISA")
    in_scope = _isa_account("H-ISA-01", in_scope=True)
    out_of_scope = _isa_account("H-ISA-02", in_scope=False)  # same type wording

    items = _limit_review_items([action], amounts, [in_scope, out_of_scope], MEETING_DATE)

    assert len(items) == 1
    assert items[0].refs == ["H-ISA-01"]


def test_two_in_scope_accounts_with_the_same_wording_stay_ambiguous_and_unnoted() -> None:
    action, amounts = _top_up_action("Stocks & Shares ISA")
    first = _isa_account("H-ISA-01", in_scope=True)
    second = _isa_account("H-ISA-02", in_scope=True)

    items = _limit_review_items([action], amounts, [first, second], MEETING_DATE)

    assert items == []
