"""R6, P12: an account with no value, a closed account, or a value not in GBP.

R6 (SCOPING.md section 3.1): "missing, null or closed: never given a value". A closed account
outside scope is ignored; a closed account inside scope is a conflict to flag, never silently
dropped (blocking -- the report's scope names an account that is no longer open). An open
account with no value is never given one: inside scope the value cell is a marker and the
review sheet records it; outside scope it goes to the review sheet only.

P12: a value not in GBP is never converted -- the value cell is a marker and the review sheet
records it; the value is withheld from the ledger whether or not the account is in scope, so
it can never reach a fact as if it were sterling. A missing or blank `currency` is not-GBP too
(DESIGN.md section 3.3): a number with no stated unit has no safe reading, and a held-out
client whose records omit the field must not have its values rendered as sterling.

Runs once per account, after `resolve_scope` (which sets `in_scope`) and `_apply_values`
(which sets `value`); the caller (`pipeline.py`) applies the result to the ledger. Pure code,
no model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_pipeline.ledger import Account, Marker
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.reconcile.wrappers import type_slug

_NEVER_ESTIMATED = "never estimated or converted (CLAUDE.md non-negotiable)"


@dataclass(frozen=True)
class AccountState:
    in_table: bool
    value_marker: Marker | None = None
    # The account's value must not reach the ledger's facts (a closed account is never given
    # one, R6; a foreign-currency figure would otherwise render as if it were sterling,
    # P12); the caller clears `Account.value` and `Account.superseded`.
    withhold_value: bool = False
    review_items: list[ReviewItemInput] = field(default_factory=list)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _label(account: Account) -> str:
    owners = " & ".join(account.owners)
    return f"{owners}'s {account.type}" if owners else account.type


def _where(account: Account) -> str:
    return f"{account.type} ({account.platform})" if account.platform else account.type


def _unique_key(stem: str, taken: set[str]) -> str:
    key, n = stem, 2
    while key in taken:
        key, n = f"{stem}_{n}", n + 1
    taken.add(key)
    return key


def _is_not_gbp(currency: str | None) -> bool:
    return currency is None or currency.strip().upper() != "GBP"


def _closed_state(account: Account) -> AccountState:
    # R6: a closed account is never given a value, in scope or not.
    if not account.in_scope:
        return AccountState(in_table=False, withhold_value=True)
    return AccountState(
        in_table=False,
        withhold_value=True,
        review_items=[
            ReviewItemInput(
                kind="conflict",
                blocking=True,
                detail=(
                    f"{_where(account)} is closed in the account data but the report "
                    "instruction's scope names it; confirm which is right before anything "
                    "is finalised."
                ),
                refs=[account.id],
            )
        ],
    )


def _null_value_state(account: Account, taken: set[str]) -> AccountState:
    if not account.in_scope:
        return AccountState(
            in_table=False,
            review_items=[
                ReviewItemInput(
                    kind="out_of_scope_no_value",
                    blocking=False,
                    detail=f"{_where(account)} is out of scope and has no value on record.",
                    refs=[account.id],
                )
            ],
        )
    marker = Marker(
        id="",
        key=_unique_key(f"{type_slug(account.type)}_value", taken),
        text=f"current value of {_label(account)}",
        reason=f"no value in the account data (R6); {_NEVER_ESTIMATED}",
        section="account_table",
    )
    return AccountState(
        in_table=True,
        value_marker=marker,
        review_items=[
            ReviewItemInput(
                kind="open_action",
                blocking=False,
                detail=(
                    f"{_where(account)} has no value in the account data; the adviser must "
                    "confirm the value (the table's value cell is a marker)."
                ),
                refs=[account.id],
            )
        ],
    )


def _foreign_currency_state(
    account: Account, currency: str | None, taken: set[str]
) -> AccountState:
    code = (currency or "").strip().upper()
    marker = Marker(
        id="",
        key=_unique_key(f"{type_slug(account.type)}_currency_{_slug(code) or 'unknown'}", taken),
        text=f"sterling value of {_label(account)}, "
        + (f"held in {code}" if code else "currency not stated"),
        reason=f"value is not in GBP (P12); {_NEVER_ESTIMATED}",
        section="account_table",
    )
    return AccountState(
        in_table=True,
        value_marker=marker,
        withhold_value=True,
        review_items=[
            ReviewItemInput(
                kind="currency",
                blocking=False,
                detail=(
                    f"{_where(account)}: the account data's currency is "
                    f"{code or 'not stated'}, not GBP; the value is not converted and the "
                    "table's value cell is a marker."
                ),
                refs=[account.id],
            )
        ],
    )


def check_account_states(
    accounts: list[Account], currency_by_id: dict[str, str | None]
) -> dict[str, AccountState]:
    """One `AccountState` per account, keyed by id. `currency_by_id` is the account data's
    own, possibly-missing `currency` field; a missing or blank one is not-GBP. Marker keys
    are unique across the call, so two same-type accounts never share one."""
    taken: set[str] = set()
    states: dict[str, AccountState] = {}
    for account in accounts:
        # An account absent from the map is a missing currency, hence not-GBP: withheld and
        # marked, never assumed to be sterling. Do not "simplify" this to a GBP default.
        currency = currency_by_id.get(account.id)
        if account.is_new:
            # An account the advice opens is shown as "To be opened" (P9): it has no value
            # to be missing, so it never gets R6's no-value marker.
            states[account.id] = AccountState(in_table=True)
        elif account.status == "closed":
            states[account.id] = _closed_state(account)
        elif account.value is None:
            states[account.id] = _null_value_state(account, taken)
        elif _is_not_gbp(currency):
            if account.in_scope:
                states[account.id] = _foreign_currency_state(account, currency, taken)
            else:
                # No value cell exists to hold a marker and nothing is reported, but the
                # foreign figure is still withheld from the ledger's facts.
                states[account.id] = AccountState(in_table=False, withhold_value=True)
        else:
            states[account.id] = AccountState(in_table=account.in_scope)
    return states
