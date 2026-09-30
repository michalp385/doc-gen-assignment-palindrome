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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from agent_pipeline.extract.schemas import LimitSignal
from agent_pipeline.ledger import Account, Action, Marker, Value, render_table
from agent_pipeline.reconcile.marker_text import accounts_phrase, each_holder_phrase
from agent_pipeline.reconcile.refs import accounts_matching_reference
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.reconcile.wrappers import classify_wrapper, type_slug

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
    if allowance_family == "pension":
        # P4: pension limits depend on personal circumstances, earlier contributions,
        # tapering and carry-forward, so a pension amount is always a marker and the
        # pipeline never attempts the calculation, whatever the amount or prior use.
        return LimitCheck(
            marker=True,
            note=False,
            reason="pension contribution amounts are always adviser-review markers",
        )
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


def limit_marker(
    allowance_family: str, account_ids: list[str], accounts: Sequence[Account] = ()
) -> Marker:
    """P2, P4 (T19): built once per allowance family a breach or confirmed prior use is
    detected for, never once per account -- multiple accounts share the same allowance
    question (e.g. both of client 02's ISAs). Never states a figure: the allowance figure
    is P4's internal screening input, not report text. Given the accounts, the text names the
    ones the question is about (holder, type and platform)."""
    wanted = set(account_ids)
    named = accounts_phrase(
        (a for a in accounts if a.id in wanted), [o for a in accounts for o in a.owners]
    )
    subject = f" for {named}" if named else ""
    return Marker(
        id="",
        key=f"{allowance_family}_amounts",
        text=(
            f"{allowance_family.upper()} top-up amounts{subject} within the remaining "
            "allowances, and where any excess goes"
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


def pension_contribution_accounts(actions: list[Action], accounts: list[Account]) -> list[Account]:
    """P4 (T21, client 04's "SIPP contributions for both, sized within allowances"): every
    in-scope pension-family account an agreed action names, each once, in the order first
    named. No amount is needed -- a pension contribution is a marker whether or not the
    sources state a figure. An agreed non-action never selects one (nothing is contributed),
    and a reference matching several pensions selects all of them rather than none, since
    dropping an ambiguous one would silently lose its marker."""
    in_scope = [a for a in accounts if a.in_scope]
    selected: dict[str, Account] = {}
    for action in actions:
        if action.kind == "non_action":
            continue
        for reference in action.accounts:
            for account in accounts_matching_reference(reference, in_scope):
                if classify_wrapper(account.type).allowance_family == "pension":
                    selected.setdefault(account.id, account)
    return list(selected.values())


def pension_contribution_markers(accounts: list[Account]) -> list[Marker]:
    """One marker per distinct pension type, keyed by the type's own wording
    (`sipp_contribution_amounts`), so it generalises to any pension type in
    `config/account_types.json`. Never states a figure."""
    markers: dict[str, Marker] = {}
    for account in accounts:
        key = f"{type_slug(account.type)}_contribution_amounts"
        if key not in markers:
            holders = [
                owner
                for other in accounts
                if type_slug(other.type) == type_slug(account.type)
                for owner in other.owners
            ]
            markers[key] = Marker(
                id="",
                key=key,
                text=f"{account.type} contribution amounts {each_holder_phrase(holders)}".strip(),
                reason="pension contribution amounts are always adviser-review markers (P4); "
                "never estimated",
                section="recommendations",
            )
    return list(markers.values())


def pension_review_item(accounts: list[Account]) -> ReviewItemInput | None:
    """P4: the review-sheet context for `pension_contribution_markers`. States no limit."""
    if not accounts:
        return None
    return ReviewItemInput(
        kind="p4_note",
        blocking=False,
        detail=(
            "Pension contribution amounts are adviser-review markers: pension limits depend "
            "on personal circumstances, earlier contributions, tapering and carry-forward, "
            "so no figure is stated."
        ),
        refs=[a.id for a in accounts],
    )
