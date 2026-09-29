"""R5 (SCOPING section 3.1 rule 5) for money items (tests first).

Where the report instruction gives an exact figure and the meeting an approximate one for the
same amount, the exact figure is used, but only if the approximate figure's stated amount is
the same ("around 120,000" and "GBP 120,000"). The instruction's amount field can be compound
text ("GBP 120,000 inheritance plus the full joint GIA value"), so the exact figures are read
out of it in code. Any difference is left as the meeting's own figure here; raising it as an
R4 conflict is `resolve_amount`'s job, not wired yet.
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.extract.schemas import LabelEvidence, Quote
from agent_pipeline.extract.schemas import MoneyItem as ExtractedMoneyItem
from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.amounts import instruction_figures, prefer_exact_instruction_figure
from agent_pipeline.reconcile.money import build_money_items


def _meeting_value(amount: str = "120000", precision: str = "approximate") -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision=precision,  # type: ignore[arg-type]  # the test passes the literal by name
        qualifier="around" if precision == "approximate" else "exact",
        date=None,
        source_id="meeting.docx",
        quote="around £120,000",
        selected_by="P5",
    )


def test_exact_figures_are_read_out_of_a_compound_amount_field() -> None:
    [figure] = instruction_figures("GBP 120,000 inheritance plus the full joint GIA value", "req")
    assert figure.amount == Decimal("120000")
    assert figure.currency == "GBP" and figure.precision == "exact"
    assert figure.source_id == "req" and figure.selected_by == "R5"


def test_a_qualified_figure_in_the_field_is_not_exact() -> None:
    assert instruction_figures("around £50,000 into the ISA", "req") == []


def test_two_figures_are_both_read_and_qualifiers_do_not_leak() -> None:
    figures = instruction_figures("£10,000 now and around £20,000 later", "req")
    assert [f.amount for f in figures] == [Decimal("10000")]


def test_the_same_amount_prefers_the_instructions_exact_figure() -> None:
    [figure] = instruction_figures("GBP 120,000 inheritance", "req")
    chosen = prefer_exact_instruction_figure(_meeting_value(), [figure])
    assert chosen.precision == "exact" and chosen.source_id == "req"


def test_a_different_amount_keeps_the_meetings_figure() -> None:
    [figure] = instruction_figures("GBP 150,000 inheritance", "req")
    meeting = _meeting_value()
    assert prefer_exact_instruction_figure(meeting, [figure]) == meeting


def test_an_exact_meeting_figure_is_kept() -> None:
    [figure] = instruction_figures("GBP 120,000", "req")
    meeting = _meeting_value(precision="exact")
    assert prefer_exact_instruction_figure(meeting, [figure]) == meeting


def test_a_different_currency_is_not_the_same_amount() -> None:
    [figure] = instruction_figures("EUR 120,000", "req")
    meeting = _meeting_value()
    assert prefer_exact_instruction_figure(meeting, [figure]) == meeting


def test_received_money_takes_the_exact_instruction_figure() -> None:
    item = ExtractedMoneyItem(
        purpose="inheritance",
        amount=Quote(paragraph_id="p1", text="around £120,000"),
        money_class="received",
        class_evidence=LabelEvidence(paragraph_id="p1", text="has received"),
    )
    instruction = instruction_figures("GBP 120,000 inheritance", "req")
    [built] = build_money_items([item], "meeting.docx", 1, instruction_figures=instruction).items
    assert built.amount is not None
    assert built.amount.precision == "exact" and built.amount.amount == Decimal("120000")


def test_without_instruction_figures_money_is_unchanged() -> None:
    item = ExtractedMoneyItem(
        purpose="inheritance",
        amount=Quote(paragraph_id="p1", text="around £120,000"),
        money_class="received",
        class_evidence=LabelEvidence(paragraph_id="p1", text="has received"),
    )
    [built] = build_money_items([item], "meeting.docx", 1).items
    assert built.amount is not None and built.amount.precision == "approximate"
