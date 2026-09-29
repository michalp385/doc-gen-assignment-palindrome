"""R5 wired into the pipeline (tests first; hand-written case 08).

SCOPING rule 5: where the report instruction gives an exact figure and the meeting an
approximate one for the same amount, use the exact one only if they state the same amount; any
difference is a conflict for the adviser to settle -- a blocking item and an amount marker, and
no figure at all reaches the report, since neither is known to be right.

The comparison is made only when it is unambiguous: the instruction states exactly one exact
figure and exactly one agreed action states an amount. Anything else is left alone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from agent_pipeline.ledger import Account, Action, Value
from agent_pipeline.pipeline import _reconcile_instruction_amount


def _value(amount: str, precision: str, quote: str, source: str) -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision=precision,  # type: ignore[arg-type]  # the test passes the literal by name
        qualifier="exact" if precision == "exact" else "around",
        date=None,
        source_id=source,
        quote=quote,
        selected_by="R5",
    )


INSTRUCTION = _value("12000", "exact", "GBP 12,000", "report_request.docx")
ISA = Account(
    id="V-ISA", type="Stocks & Shares ISA", owners=["V H"], platform="Alpha", in_scope=True
)
CASH = Account(id="V-CASH", type="Cash Account", owners=["V H"], platform="Alpha")
GIA = Account(
    id="V-GIA", type="General Investment Account", owners=["V H"], platform="Alpha", in_scope=True
)


def _action(
    action_id: str = "a1",
    accounts: tuple[str, ...] = ("Stocks & Shares ISA",),
    kind: Literal["action", "non_action"] = "action",
) -> Action:
    return Action(
        id=action_id,
        description="move money",
        kind=kind,
        accounts=list(accounts),
        quote="move money",
    )


def test_a_different_amount_is_a_blocking_conflict_with_a_marker_and_no_figure() -> None:
    meeting = _value("15000", "approximate", "around £15,000", "meeting_notes.docx")
    amounts = {"a1": meeting}
    markers, items = _reconcile_instruction_amount(
        [_action(accounts=("Stocks & Shares ISA", "cash account"))],
        amounts,
        [ISA, CASH],
        [INSTRUCTION],
    )
    assert amounts == {}  # neither figure reaches the report
    [marker] = markers
    assert marker.key == "topup_amount_conflict" and marker.section == "recommendations"
    [item] = items
    assert item.kind == "conflict" and item.blocking
    assert "GBP 12,000" in item.detail and "around £15,000" in item.detail


def test_a_conflict_on_a_non_allowance_account_is_keyed_generically() -> None:
    meeting = _value("15000", "approximate", "around £15,000", "meeting_notes.docx")
    markers, _ = _reconcile_instruction_amount(
        [_action(accounts=("General Investment Account",))], {"a1": meeting}, [GIA], [INSTRUCTION]
    )
    assert [m.key for m in markers] == ["investment_amount_conflict"]


def test_the_same_amount_uses_the_exact_figure_and_raises_nothing() -> None:
    meeting = _value("12000", "approximate", "around £12,000", "meeting_notes.docx")
    amounts = {"a1": meeting}
    markers, items = _reconcile_instruction_amount([_action()], amounts, [ISA], [INSTRUCTION])
    assert (markers, items) == ([], [])
    assert amounts["a1"].precision == "exact" and amounts["a1"].quote == "GBP 12,000"


def test_two_equal_exact_figures_leave_the_meetings_own_value_untouched() -> None:
    """Nothing to reconcile: keep the meeting's Value (its quote and source) as extracted."""
    meeting = _value("12000", "exact", "£12,000", "meeting_notes.docx")
    amounts = {"a1": meeting}
    assert _reconcile_instruction_amount([_action()], amounts, [ISA], [INSTRUCTION]) == ([], [])
    assert amounts["a1"] is meeting


def test_no_instruction_figure_leaves_everything_alone() -> None:
    meeting = _value("15000", "approximate", "around £15,000", "meeting_notes.docx")
    amounts = {"a1": meeting}
    assert _reconcile_instruction_amount([_action()], amounts, [ISA], []) == ([], [])
    assert amounts == {"a1": meeting}


def test_two_instruction_figures_are_not_compared() -> None:
    meeting = _value("15000", "approximate", "around £15,000", "meeting_notes.docx")
    other = _value("500", "exact", "GBP 500", "report_request.docx")
    amounts = {"a1": meeting}
    assert _reconcile_instruction_amount([_action()], amounts, [ISA], [INSTRUCTION, other]) == (
        [],
        [],
    )
    assert amounts == {"a1": meeting}


def test_two_actions_with_amounts_are_not_compared() -> None:
    meeting = _value("15000", "approximate", "around £15,000", "meeting_notes.docx")
    amounts = {"a1": meeting, "a2": meeting}
    assert _reconcile_instruction_amount(
        [_action("a1"), _action("a2")], amounts, [ISA], [INSTRUCTION]
    ) == ([], [])


def test_an_action_without_an_amount_or_a_non_action_is_ignored() -> None:
    assert _reconcile_instruction_amount([_action()], {}, [ISA], [INSTRUCTION]) == ([], [])
    meeting = _value("15000", "approximate", "around £15,000", "meeting_notes.docx")
    assert _reconcile_instruction_amount(
        [_action(kind="non_action")], {"a1": meeting}, [ISA], [INSTRUCTION]
    ) == ([], [])
