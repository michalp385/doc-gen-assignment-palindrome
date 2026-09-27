"""P5: money available now, in code, never a model estimate.

Available now is received minus committed, computed only when there is received money to
begin with -- moving cash between a client's own existing accounts (client 01's ISA
top-up) is not received/committed/proceeds/external money under P5 at all, so there is
nothing to compute. Proceeds, external money and the full P5 classification arrive in M2
with client 02's disposal and client 04's business-sale proceeds.
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.ledger import MoneyItem


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
