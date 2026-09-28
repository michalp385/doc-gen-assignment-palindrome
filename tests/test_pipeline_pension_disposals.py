"""T20/T21: the stage graph's wiring for P4 pension contributions and P7 disposals.

- `_pension_markers`: an agreed action naming an in-scope pension account always yields the
  contribution-amounts marker and a P4 note, whether or not the sources state an amount.
- The ISA-style limit path (`_limit_markers`, `_limit_review_items`) never handles pensions:
  `check_limits` would treat a stated pension amount as an ISA-shaped allowance question.
- `_classify_disposals`: a disposal carries its account id and wrapper class (a bond
  encashment is "bond", never "taxable"), and one that matches no single account is an
  "unknown" wrapper -- a possible taxable disposal pending confirmation (G5 case b) -- never
  silently dropped.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.schemas import Disposal, LabelEvidence, Quote
from agent_pipeline.ledger import Account, Action, Value
from agent_pipeline.pipeline import (
    _classify_disposals,
    _limit_markers,
    _limit_review_items,
    _pension_markers,
)

MEETING_DATE = date(2026, 5, 20)
_EVIDENCE = LabelEvidence(paragraph_id="p1", text="in full")


def _account(
    account_id: str, type_: str, owner: str = "James Whitmore", **update: object
) -> Account:
    return Account(
        id=account_id, owners=[owner], type=type_, platform="Brightwell", in_scope=True
    ).model_copy(update=update)


def _value(amount: str) -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 4, 30),
        source_id="client_data_db.json",
        quote="",
        selected_by="R3",
    )


def _disposal(reference: str, extent: str = "full") -> Disposal:
    return Disposal.model_validate(
        {
            "account_reference": reference,
            "quote": Quote(paragraph_id="p1", text=f"sell the {reference}"),
            "extent": extent,
            "extent_evidence": _EVIDENCE,
        }
    )


# --- P4 pensions ---------------------------------------------------------------------------


def test_an_action_with_no_amount_naming_a_sipp_yields_the_marker_and_a_note() -> None:
    sipp = _account("B4-SIPP-J", "SIPP")
    action = Action(id="a1", description="contribute to the SIPP", accounts=["SIPP"])
    markers, items = _pension_markers([action], [sipp])
    assert [m.key for m in markers] == ["sipp_contribution_amounts"]
    assert [(i.kind, i.refs) for i in items] == [("p4_note", ["B4-SIPP-J"])]


def test_no_pension_action_no_pension_marker() -> None:
    isa = _account("H-ISA-J", "Stocks & Shares ISA")
    action = Action(id="a1", description="top up", accounts=["Stocks & Shares ISA"])
    assert _pension_markers([action], [isa]) == ([], [])


def test_a_stated_pension_amount_does_not_also_take_the_isa_style_limit_path() -> None:
    sipp = _account("B4-SIPP-J", "SIPP")
    action = Action(id="a1", description="contribute", accounts=["SIPP"])
    amounts = {"a1": _value("30000")}
    assert _limit_markers([action], amounts, [sipp], MEETING_DATE, []) == []
    assert _limit_review_items([action], amounts, [sipp], MEETING_DATE, []) == []


# --- P7 disposals --------------------------------------------------------------------------


def test_a_bond_encashment_is_a_bond_disposal_carrying_its_account_id() -> None:
    bond = _account("M4-BOND-J", "Offshore Investment Bond", value=_value("180000"))
    disposals, _, _ = _classify_disposals(
        [_disposal("Offshore Investment Bond")], [], [bond], "meeting_notes.docx"
    )
    assert [(d.wrapper_class, d.account_id) for d in disposals] == [("bond", "M4-BOND-J")]


def test_a_taxable_disposal_carries_its_account_id() -> None:
    gia = _account("H4-GIA-HJ", "General Investment Account", value=_value("255000"))
    disposals, _, _ = _classify_disposals(
        [_disposal("General Investment Account", "portion")], [], [gia], "meeting_notes.docx"
    )
    assert [(d.wrapper_class, d.account_id) for d in disposals] == [("taxable", "H4-GIA-HJ")]


def test_a_disposal_matching_no_account_is_an_unknown_wrapper_never_dropped() -> None:
    isa = _account("H-ISA-J", "Stocks & Shares ISA", value=_value("85000"))
    disposals, money_items, proceeds = _classify_disposals(
        [_disposal("the mystery holding")], [], [isa], "meeting_notes.docx"
    )
    assert [(d.wrapper_class, d.account_id) for d in disposals] == [("unknown", "")]
    assert money_items == []
    assert proceeds == {}


def test_a_disposal_matching_two_accounts_is_an_unknown_wrapper_never_a_guess() -> None:
    a = _account("H-GIA-1", "General Investment Account", value=_value("1000"))
    b = _account("B-GIA-2", "General Investment Account", "Someone Else", value=_value("2000"))
    disposals, _, _ = _classify_disposals(
        [_disposal("General Investment Account")], [], [a, b], "meeting_notes.docx"
    )
    assert [d.wrapper_class for d in disposals] == ["unknown"]
