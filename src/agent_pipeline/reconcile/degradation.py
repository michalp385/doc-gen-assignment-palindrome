"""Section 8.4 degradation: optional inputs that are missing (DESIGN.md sections 3 and 8.4).

A missing optional field never stops a run and is never hidden: the run continues on the
conservative defaults and the review sheet says what was missing. Today: an in-scope account
with no platform recorded (its charges marker says the platform is not stated), and a meeting
record with no date (an undated figure never outranks a dated one, R3). Pure code.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.reconcile.scope_parts import UNRESOLVED_ID_PREFIX


def missing_platform_review_items(accounts: Sequence[Account]) -> list[ReviewItemInput]:
    """One non-blocking degradation item per in-scope account with no platform recorded."""
    return [
        ReviewItemInput(
            kind="degradation",
            blocking=False,
            detail=(
                f"the platform is not stated for the {account.type} ({account.id}); its platform "
                "charge is a marker that says so, and the platform is not named in the report."
            ),
            refs=[account.id],
        )
        for account in accounts
        if account.in_scope
        and not account.is_new
        and not account.id.startswith(UNRESOLVED_ID_PREFIX)
        and not account.platform
    ]


def undated_meeting_review_item(meeting_date: date | None) -> ReviewItemInput | None:
    if meeting_date is not None:
        return None
    return ReviewItemInput(
        kind="degradation",
        blocking=False,
        detail=(
            "the meeting record gives no date, so it is treated as undated: none of its figures "
            "outranks a dated one (R3), and the tax year is not derived from it."
        ),
        refs=[],
    )
