"""R5 (with R4), tests first (T20/T21): an exact instruction figure against an approximate
meeting figure for the same amount.

Use the exact one only if the approximate figure's stated amount is the same ("around
£120,000" and "GBP 120,000"). Any difference is a conflict under R4 for the adviser to settle:
no tolerance is assumed, and the amount becomes a marker rather than picking either.

`reconcile_amounts` (T8) only reports agreement; `resolve_amount` builds on it and produces
the value to use, or the conflict review item and marker (hand-written case 8's shape).
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.amounts import reconcile_amounts, resolve_amount


def _value(text: str, source_id: str) -> Value:
    parsed = parse_amount(text)
    assert parsed is not None
    return Value(
        amount=parsed.amount,
        currency=parsed.currency,
        precision=parsed.precision,
        qualifier=parsed.qualifier,
        date=None,
        source_id=source_id,
        quote=text,
        selected_by="R5",
    )


def test_same_stated_amount_uses_the_exact_instruction_figure() -> None:
    # client 03: the instruction says GBP 120,000, the meeting says around £120,000
    resolution = resolve_amount(
        _value("GBP 120,000", "report_request.docx"),
        _value("around £120,000", "meeting_notes.docx"),
        label="inheritance",
    )
    assert resolution.value is not None
    assert resolution.value.amount == Decimal("120000")
    assert resolution.value.precision == "exact"
    assert resolution.value.source_id == "report_request.docx"
    assert resolution.conflict is None
    assert resolution.marker is None


def test_same_amount_with_the_exact_figure_in_the_meeting_uses_that_one() -> None:
    resolution = resolve_amount(
        _value("around £120,000", "report_request.docx"),
        _value("£120,000", "meeting_notes.docx"),
        label="inheritance",
    )
    assert resolution.value is not None
    assert resolution.value.precision == "exact"
    assert resolution.value.source_id == "meeting_notes.docx"


def test_two_approximate_figures_for_the_same_amount_keep_the_instruction_one() -> None:
    resolution = resolve_amount(
        _value("around £120,000", "report_request.docx"),
        _value("a little over £120,000", "meeting_notes.docx"),
        label="inheritance",
    )
    assert resolution.value is not None
    assert resolution.value.source_id == "report_request.docx"
    assert resolution.conflict is None


def test_any_difference_is_a_conflict_no_tolerance_assumed() -> None:
    # case 8: the instruction says GBP 12,000, the meeting says around £15,000
    resolution = resolve_amount(
        _value("GBP 12,000", "report_request.docx"),
        _value("around £15,000", "meeting_notes.docx"),
        label="topup_amount",
    )
    assert resolution.value is None
    assert resolution.conflict is not None
    assert resolution.conflict.kind == "conflict"
    assert resolution.conflict.blocking is True
    assert "GBP 12,000" in resolution.conflict.detail
    assert "around £15,000" in resolution.conflict.detail


def test_a_one_pound_difference_is_still_a_conflict() -> None:
    resolution = resolve_amount(
        _value("£120,000", "report_request.docx"),
        _value("around £120,001", "meeting_notes.docx"),
        label="inheritance",
    )
    assert resolution.value is None
    assert resolution.conflict is not None


def test_a_conflict_becomes_an_amount_marker_never_a_picked_figure() -> None:
    resolution = resolve_amount(
        _value("GBP 12,000", "report_request.docx"),
        _value("around £15,000", "meeting_notes.docx"),
        label="topup_amount",
    )
    assert resolution.marker is not None
    assert resolution.marker.key == "topup_amount_conflict"
    assert not any(ch.isdigit() for ch in resolution.marker.text)


def test_the_same_number_in_different_currencies_is_a_conflict() -> None:
    resolution = resolve_amount(
        _value("€120,000", "report_request.docx"),
        _value("around £120,000", "meeting_notes.docx"),
        label="inheritance",
    )
    assert resolution.value is None
    assert resolution.conflict is not None


def test_reconcile_amounts_still_reports_agreement_only() -> None:
    # the T8 function is unchanged; resolve_amount builds on it
    a = _value("GBP 120,000", "report_request.docx")
    b = _value("around £120,000", "meeting_notes.docx")
    assert reconcile_amounts(a, b).agrees is True
