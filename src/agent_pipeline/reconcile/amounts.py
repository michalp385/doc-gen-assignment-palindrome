"""R5: exact instruction figure vs. approximate meeting figure for the same amount.

Use the exact one only if the two figures state the same amount; any difference is a
conflict under R4 for the adviser to settle, never resolved by picking one silently, and no
tolerance is assumed. `reconcile_amounts` (T8) only reports agreement; `resolve_amount`
builds on it and produces what the caller needs: the value to use when the figures agree, or,
when they don't, a blocking conflict review item and an amount marker (SCOPING.md P2: an
amount the sources disagree on is an adviser-review marker, not a pick).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.ledger import Marker, Value, render_prose
from agent_pipeline.reconcile.review import ReviewItemInput


@dataclass(frozen=True)
class AmountReconciliation:
    amount: Decimal | None
    agrees: bool


def reconcile_amounts(instruction: Value, meeting: Value) -> AmountReconciliation:
    if instruction.amount == meeting.amount:
        return AmountReconciliation(amount=instruction.amount, agrees=True)
    return AmountReconciliation(amount=None, agrees=False)


_FIGURE_RE = re.compile(r"(?:[£€$]\s?|\b(?:GBP|EUR|USD)\s+)\d[\d,]*(?:\.\d+)?[kKmM]?")
_QUALIFIER_WINDOW = 20


def instruction_figures(text: str, source_id: str) -> list[Value]:
    """R5: the exact money figures in a report-instruction field's text, which can be compound
    ("GBP 5,000 inheritance plus the full account value"). A figure preceded by a
    qualifier ("around", "c.") is not exact and is left out. Each is parsed in code from the
    text itself (D9), never from a model's structured value."""
    figures: list[Value] = []
    previous_end = 0
    for match in _FIGURE_RE.finditer(text):
        window = text[max(previous_end, match.start() - _QUALIFIER_WINDOW) : match.end()]
        previous_end = match.end()
        parsed = parse_amount(window)
        if parsed is None or parsed.precision != "exact":
            continue
        figures.append(
            Value(
                amount=parsed.amount,
                currency=parsed.currency,
                precision="exact",
                qualifier="exact",
                date=None,
                source_id=source_id,
                quote=match.group(0).strip(),
                selected_by="R5",
            )
        )
    return figures


def prefer_exact_instruction_figure(meeting: Value, instruction: list[Value]) -> Value:
    """R5 (SCOPING section 3.1 rule 5): an approximate meeting figure is replaced by the
    instruction's exact figure only when both state the same amount in the same currency.
    Otherwise the meeting's figure stands; a genuine difference is R4's conflict, raised by
    `resolve_amount`, which is not wired into the stage graph yet."""
    if meeting.precision == "exact":
        return meeting
    for figure in instruction:
        if figure.amount == meeting.amount and figure.currency == meeting.currency:
            return figure
    return meeting


@dataclass(frozen=True)
class AmountResolution:
    value: Value | None
    conflict: ReviewItemInput | None = None
    marker: Marker | None = None


def _quoted(value: Value) -> str:
    return value.quote or render_prose(value)


def resolve_amount(instruction: Value, meeting: Value, *, label: str) -> AmountResolution:
    """R5, R4. Agreement means the same stated amount in the same currency (the same number
    in two currencies is not the same amount). Then the exact figure is used -- the
    instruction's if it is exact, otherwise the meeting's if that is, otherwise the
    instruction's, which confirms the meeting. Otherwise there is no value: a blocking
    conflict quoting both figures and an amount marker keyed `<label>_conflict`."""
    agrees = (
        reconcile_amounts(instruction, meeting).agrees and instruction.currency == meeting.currency
    )
    if agrees:
        if instruction.precision == "exact" or meeting.precision != "exact":
            return AmountResolution(value=instruction)
        return AmountResolution(value=meeting)
    description = label.replace("_", " ")
    return AmountResolution(
        value=None,
        conflict=ReviewItemInput(
            kind="conflict",
            blocking=True,
            detail=(
                f"{description}: the report instruction says {_quoted(instruction)} "
                f"({instruction.source_id}) but the meeting record says {_quoted(meeting)} "
                f"({meeting.source_id}); the adviser must settle which is right."
            ),
            refs=[],
        ),
        marker=Marker(
            id="",
            key=f"{label}_conflict",
            text=f"{description}: the report instruction and the meeting record differ",
            reason="R5: the stated amounts differ; no tolerance is assumed",
            section="recommendations",
        ),
    )
