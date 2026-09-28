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

from agent_pipeline.extract.schemas import LimitSignal
from agent_pipeline.ledger import Marker, Value, render_table
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


_PRIOR_USE_INDICATORS = ("already", "part-funded", "part funded", "used up", "so far this year")


def resolve_prior_use(signals: list[LimitSignal], allowance_family: str) -> PriorUse:
    """P4 (T19, client 02's "already part-funded"): a verified `limit_signals` quote
    confirms prior use only when it names the allowance family *and* reads as an existing-
    use statement, never on family-name presence alone -- client 01's own cached extraction
    (`cache/llm/20/20a44c38...json`) has a genuine `limit_signals` entry, "would like to use
    this year's ISA allowance", for the top-up being agreed *today*, not any earlier use; a
    bare family-substring match would misclassify it as confirmed prior use and wrongly
    marker client 01 (exactly the "early version...silently swallowed" regression this
    module's own history already records, T17 checkpoint, for the opposite failure mode).
    `_PRIOR_USE_INDICATORS` is general vocabulary distinguishing "already/part-funded/used
    up" from forward-looking "would like to/plan to", not client data. Sources silent on it
    stay "unknown" (never guessed "denied" -- nothing here ever produces "denied": that
    reading needs a signal explicitly ruling prior use out, which no client has yet,
    DESIGN.md section 4.2's conservative-default principle applied to a three-way label)."""
    for signal in signals:
        text = signal.text.text.lower()
        if allowance_family.lower() in text and any(ind in text for ind in _PRIOR_USE_INDICATORS):
            return "confirmed"
    return "unknown"


def limit_marker(allowance_family: str, account_ids: list[str]) -> Marker:
    """P2, P4 (T19): built once per allowance family a breach or confirmed prior use is
    detected for, never once per account -- multiple accounts share the same allowance
    question (e.g. both of client 02's ISAs). Never states a figure: the allowance figure
    is P4's internal screening input, not report text."""
    return Marker(
        id="",
        key=f"{allowance_family}_amounts",
        text=(
            f"{allowance_family.upper()} top-up amounts within the remaining allowances, "
            "and where any excess goes"
        ),
        reason="a possible allowance breach or confirmed prior use (P4); never estimated",
        section="recommendations",
    )


def limit_review_item(
    amount: Value,
    allowance_family: str,
    prior_use: PriorUse,
    meeting_date: date,
    account_ids: list[str],
) -> ReviewItemInput | None:
    """P4 (DESIGN.md section 6): every `check_limits` flag gets a review-sheet row so the
    adviser has context either way -- the unstated-prior-use note (unchanged), and (T19) a
    genuine breach or confirmed prior use, which additionally gets a report marker
    (`limit_marker`, the caller's job, once per allowance family). Neither case ever states
    a figure: the plan's own top-up amount is never precise enough to quote once split
    across destinations, and the allowance figure itself is P4's screening input only."""
    result = check_limits(amount.amount, allowance_family, prior_use, meeting_date)
    if result.note:
        return ReviewItemInput(
            kind="p4_note",
            blocking=False,
            detail=(
                f"The {render_table(amount)} top-up uses this tax year's full "
                f"{allowance_family.upper()} allowance; prior use this tax year is unstated."
            ),
            refs=account_ids,
        )
    if result.marker:
        return ReviewItemInput(
            kind="p4_note",
            blocking=False,
            detail=(
                f"Possible {allowance_family.upper()} allowance breach: {result.reason}. "
                "The adviser must confirm how much each account can take and where any "
                "excess goes."
            ),
            refs=account_ids,
        )
    return None
