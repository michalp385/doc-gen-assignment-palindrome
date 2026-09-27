"""P4: general UK allowance figures, used only to detect a possible breach.

The report never quotes a rule figure the sources don't give; a figure here only decides
whether to raise a marker or a review-sheet note. Rule figures live in
config/tax_rules.json, keyed by tax year, and the tax year comes from the meeting date
(the 6 April boundary), never from a metadata-only fallback date.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

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
    prior_use_known: bool,
    meeting_date: date,
) -> LimitCheck:
    year = tax_year_for(meeting_date)
    allowance = _ALLOWANCES.get(allowance_family, {}).get(year)

    if allowance is None:
        return LimitCheck(
            marker=True, note=False, reason=f"no {allowance_family} allowance on file for {year}"
        )
    if amount > allowance:
        return LimitCheck(marker=True, note=False, reason="the planned total exceeds the allowance")
    if amount == allowance and not prior_use_known:
        return LimitCheck(
            marker=False,
            note=True,
            reason="full-allowance subscription; prior use this tax year is unstated",
        )
    return LimitCheck(marker=False, note=False, reason="")
