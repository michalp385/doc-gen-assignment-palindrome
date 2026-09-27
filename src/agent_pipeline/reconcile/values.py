"""R3: which dated value wins for an account.

The most recent dated candidate wins, among the account data and any meeting figure the
meeting record says was actually viewed during the meeting -- a recalled or paperwork
figure, or a statement-image value, never selects (verify_label's conservative default,
T5, already keeps those out of `viewed_observations`). The superseded value and both
dates go to the review sheet; that assembly step lives with reconciliation's caller in M2,
once there is more than one candidate to choose between (client 01 never has one).
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from agent_pipeline.ledger import Value


def select_values(
    db_value: Decimal | None,
    db_date: _date | None,
    currency: str | None,
    viewed_observations: list[Value],
) -> Value | None:
    candidates: list[Value] = []
    if db_value is not None:
        candidates.append(
            Value(
                amount=db_value,
                currency=currency or "GBP",
                precision="exact",
                qualifier="exact",
                date=db_date,
                source_id="client_data_db.json",
                quote="",
                selected_by="R3",
            )
        )
    candidates.extend(viewed_observations)
    if not candidates:
        return None
    return max(candidates, key=lambda v: v.date or _date.min)
