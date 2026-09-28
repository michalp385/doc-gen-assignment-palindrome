"""P4: general UK allowance figures, used only to detect a possible breach.

The report never quotes a rule figure the sources don't give; a figure here only decides
whether to raise a marker or a review-sheet note. Rule figures live in
config/tax_rules.json, keyed by tax year, and the tax year comes from the meeting date
(the 6 April boundary), never from a metadata-only fallback date.

P4's trigger is two independent conditions -- confirmed prior use of the allowance ("already
part-funded"), or the planned total exceeding the rule figure -- plus a third, narrower,
non-marker case: a full-allowance amount with prior use merely *unstated*. A bare
`prior_use: bool` can't tell "sources confirm it happened" apart from "sources are silent",
so it silently missed the first condition (verifier report, T8 checkpoint, finding #6);
`prior_use` is a three-way signal instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from agent_pipeline.ledger import Value, render_table
from agent_pipeline.reconcile.review import ReviewItemInput

PriorUse = Literal["confirmed", "denied", "unknown"]

CONFIG_PATH = Path("config/tax_rules.json")


def _load_allowances() -> dict[str, dict[str, Decimal]]:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    families = {k: v for k, v in raw.items() if not k.startswith("_")}
    return {
        family: {year: Decimal(str(amount)) for year, amount in years.items()}
        for family, years in families.items()
    }


_ALLOWANCES = _load_allowances()


def tax_year_for(meeting_date: date) -> str:
    """The UK tax year (6 April boundary) a date falls in, e.g. '2026/27'."""
    boundary = date(meeting_date.year, 4, 6)
    start_year = meeting_date.year if meeting_date >= boundary else meeting_date.year - 1
    return f"{start_year}/{str(start_year + 1)[-2:]}"


@dataclass(frozen=True)
class LimitCheck:
    marker: bool
    note: bool
    reason: str


def check_limits(
    amount: Decimal,
    allowance_family: str,
    prior_use: PriorUse,
    meeting_date: date,
) -> LimitCheck:
    year = tax_year_for(meeting_date)
    allowance = _ALLOWANCES.get(allowance_family, {}).get(year)

    if allowance is None:
        return LimitCheck(
            marker=True, note=False, reason=f"no {allowance_family} allowance on file for {year}"
        )
    if prior_use == "confirmed":
        return LimitCheck(
            marker=True,
            note=False,
            reason="the sources show prior use of the allowance this tax year",
        )
    if amount > allowance:
        return LimitCheck(marker=True, note=False, reason="the planned total exceeds the allowance")
    if amount == allowance and prior_use == "unknown":
        return LimitCheck(
            marker=False,
            note=True,
            reason="full-allowance subscription; prior use this tax year is unstated",
        )
    return LimitCheck(marker=False, note=False, reason="")


def limit_review_item(
    amount: Value,
    allowance_family: str,
    prior_use: PriorUse,
    meeting_date: date,
    account_id: str,
) -> ReviewItemInput | None:
    """P4's note case only (DESIGN.md section 6): a full-allowance subscription whose prior
    use this tax year the sources don't state. `check_limits`' marker case (a breach, or
    confirmed prior use) needs report-marker wiring -- `ledger.markers`, a writer-facing
    token, a place in the template -- not built until T20 widens P4 with client 03's real
    breach cases; this only ever returns the review-sheet note, never a marker, so a breach
    reaches no review item at all yet (a known, deliberate gap, not silently dropped: T20's
    own plan entry is where it closes)."""
    result = check_limits(amount.amount, allowance_family, prior_use, meeting_date)
    if not result.note:
        return None
    return ReviewItemInput(
        kind="p4_note",
        blocking=False,
        detail=(
            f"The {render_table(amount)} top-up uses this tax year's full "
            f"{allowance_family.upper()} allowance; prior use this tax year is unstated."
        ),
        refs=[account_id],
    )
