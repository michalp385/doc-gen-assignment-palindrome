"""R5: exact instruction figure vs. approximate meeting figure for the same amount.

Use the exact one only if the two figures state the same amount; any difference is a
conflict under R4 for the adviser to settle, never resolved by picking one silently. This
module only reports agreement; raising the R4 conflict is reconciliation's caller's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from agent_pipeline.ledger import Value


@dataclass(frozen=True)
class AmountReconciliation:
    amount: Decimal | None
    agrees: bool


def reconcile_amounts(instruction: Value, meeting: Value) -> AmountReconciliation:
    if instruction.amount == meeting.amount:
        return AmountReconciliation(amount=instruction.amount, agrees=True)
    return AmountReconciliation(amount=None, agrees=False)
