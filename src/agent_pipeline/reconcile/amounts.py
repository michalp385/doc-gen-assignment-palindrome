"""R5: exact instruction figure vs. approximate meeting figure for the same amount.

Use the exact one only if the two figures state the same amount; any difference is a
conflict under R4 for the adviser to settle, never resolved by picking one silently, and no
tolerance is assumed. `reconcile_amounts` (T8) only reports agreement; `resolve_amount`
builds on it and produces what the caller needs: the value to use when the figures agree, or,
when they don't, a blocking conflict review item and an amount marker (SCOPING.md P2: an
amount the sources disagree on is an adviser-review marker, not a pick).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
