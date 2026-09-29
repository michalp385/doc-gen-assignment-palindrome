"""R10: several meeting records (SCOPING section 3.1 rule 10).

The latest-dated record governs decisions (actions, disposals, money, open items, the
introduction's facts); earlier ones contribute dated values only, under rule 3. An undated
record is the earliest of all, so it never outranks a dated one, and records sharing the latest
date fall back to input order. One record is the ordinary case and changes nothing. Pure code.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from agent_pipeline.reconcile.review import ReviewItemInput


def govern_meeting_records(dates: Sequence[date | None]) -> tuple[int, list[int]]:
    """(index of the governing record, indexes of the earlier ones, oldest first)."""
    order = sorted(range(len(dates)), key=lambda i: (dates[i] or date.min, i))
    return order[-1], order[:-1]


def _when(day: date | None) -> str:
    return f"{day.day} {day:%B} {day.year}" if day is not None else "undated"


def several_records_review_item(
    names: Sequence[str], dates: Sequence[date | None], governing: int
) -> ReviewItemInput | None:
    if len(names) <= 1:
        return None
    earlier = ", ".join(
        f"{names[i]} ({_when(dates[i])})" for i in range(len(names)) if i != governing
    )
    return ReviewItemInput(
        kind="degradation",
        blocking=False,
        detail=(
            f"there are {len(names)} meeting records; the latest, {names[governing]} "
            f"({_when(dates[governing])}), governs decisions. Earlier: {earlier} -- they "
            "contribute dated figures only (R3, R10)."
        ),
        refs=[],
    )
