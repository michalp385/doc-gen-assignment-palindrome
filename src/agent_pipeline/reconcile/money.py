"""P5: money available now, and disposal proceeds, in code, never a model estimate.

Available now is received minus committed, computed only when there is received money to
begin with -- moving cash between a client's own existing accounts (client 01's ISA
top-up) is not received/committed/proceeds/external money under P5 at all, so there is
nothing to compute. `classify_money` (T19, client 02's GIA disposal) is the proceeds half:
a disposal's proceeds count toward the plan's funding only when both the amount sold and
its destination are known -- at the value R3 (`reconcile/values.py`) already selected for
that account, never a separately-extracted figure, and rendered with P5's qualifiers via
the selected `Value`'s own precision/qualifier (never rounded). A portion sold, or an
unclear destination, is a marker instead: the caller (`pipeline.py`) never has an amount to
put in a `Fact`, so it can't reach the writer.

TODO(T21): SCOPING.md section 4, P5, is explicit that "if a commitment has no stated
amount, the available amount becomes a marker: a guessed amount is never subtracted."
Neither client 01 nor client 02 has an amount-less commitment, so `compute_available` has
no real case to exercise; an amount-less `received` or `committed` item is silently
excluded from the sum below rather than forcing that marker. Fix this when client 04's
business-sale proceeds (T21) give a real amount-less case to test against, not blind
(verifier report, T8 checkpoint, finding #9).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from agent_pipeline.ledger import MoneyItem, Value


def compute_available(money_items: list[MoneyItem]) -> Decimal | None:
    received_items = [m for m in money_items if m.money_class == "received"]
    if not received_items:
        return None
    received = sum((m.amount.amount for m in received_items if m.amount is not None), Decimal(0))
    committed = sum(
        (m.amount.amount for m in money_items if m.money_class == "committed" and m.amount),
        Decimal(0),
    )
    return received - committed


@dataclass(frozen=True)
class ProceedsClassification:
    counted: bool
    amount: Value | None
    reason: str


def classify_money(
    disposal_value: Value,
    extent: Literal["full", "portion", "unspecified"],
    destination_known: bool,
) -> ProceedsClassification:
    """P5's proceeds rule: counted only when the disposal is `full` (a stated `portion`
    amount is a future widening -- no client has one yet) and the destination is known.
    Otherwise a marker, never a guessed or partial figure."""
    if extent != "full":
        return ProceedsClassification(
            counted=False, amount=None, reason=f"disposal extent is {extent!r}, not full"
        )
    if not destination_known:
        return ProceedsClassification(
            counted=False, amount=None, reason="the destination of the proceeds is unclear"
        )
    return ProceedsClassification(counted=True, amount=disposal_value, reason="")
