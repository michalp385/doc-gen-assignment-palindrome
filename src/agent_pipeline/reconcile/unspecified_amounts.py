"""P2, P5: an amount the sources leave unspecified but the report needs is a marker.

Built in code from the ledger; no model labels the basis (D1/P1). Three sources of an
unspecified amount, each keyed by the account type's own wording so it generalises:

- an agreed funding action with no amount on an allowance-bearing account
  (`<family>_amounts`) or on another in-scope account (`<type>_addition_amount`);
- a disposal of a portion, or of an extent the note does not state (`<type>_portion_sold`),
  which also raises a destination review item unless the sources say where the money goes;
- the balance placed into a new account (`new_account_balance`). When exactly one other
  unspecified amount feeds it, that marker's text covers the balance; otherwise the balance is
  its own marker.

Pension contribution amounts and the available-now marker are built elsewhere; the caller
passes how many such markers exist (`other_unspecified`) so the balance rule can count them.
Pure code, no model call.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field

from agent_pipeline.ledger import Account, Action, Marker, Value, render_prose
from agent_pipeline.reconcile.new_accounts import scope_names_new_account
from agent_pipeline.reconcile.refs import accounts_matching_reference
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.reconcile.wrappers import classify_wrapper, type_slug

_NEVER_ESTIMATED = "never estimated (CLAUDE.md non-negotiable)"

# An agreed action that puts money into an account. An action without one of these words
# ("use the allowance", "review", "rebalance") is not a funding action, so no amount is
# missing from it. Errs towards a marker, which fails safe, over silence.
_FUNDING_VERB_RE = re.compile(
    r"\b(add|adding|top[- ]?up|contribut\w*|pay(?:ing)? in|invest(?:ing|ed)?|fund(?:ing|ed)?|"
    r"deposit\w*|subscri\w*|"
    r"place|put|transfer\w*|move|moving)\b",
    re.IGNORECASE,
)
# A change made within an account, not money moved into one: switching, rebalancing,
# reallocating, or anything done "within" a wrapper. Not a funding action even when it
# mentions funds.
_INTERNAL_CHANGE_RE = re.compile(
    r"\b(?:switch\w*|rebalanc\w*|reallocat\w*|within\s+(?:\S+\s+){0,3}?(?:isa|sipp|gia|account|wrapper|portfolio|pension|bond)s?)\b",
    re.IGNORECASE,
)
_BALANCE_TEXT = " and the resulting balance for the new account"


@dataclass(frozen=True)
class PartialDisposal:
    """A matched disposal whose extent is a portion, or is not stated."""

    account: Account
    reference: str  # the note's own wording for the account, e.g. what the model quoted
    extent: str


@dataclass
class UnspecifiedResult:
    markers: list[Marker] = field(default_factory=list)
    review_items: list[ReviewItemInput] = field(default_factory=list)


def _unique_key(stem: str, taken: set[str]) -> str:
    key, n = stem, 2
    while key in taken:
        key, n = f"{stem}_{n}", n + 1
    taken.add(key)
    return key


def is_funding_action(action: Action) -> bool:
    if _INTERNAL_CHANGE_RE.search(action.description):
        return False
    return _FUNDING_VERB_RE.search(action.description) is not None


def _names_new_account(action: Action) -> bool:
    return any(scope_names_new_account(text) for text in (action.description, *action.accounts))


def _overlaps_a_disposal(action: Action, disposal_quotes: list[str]) -> bool:
    text = (action.quote or action.description).strip()
    return any(text in quote or quote in text for quote in disposal_quotes if quote.strip())


def _marker(key: str, text: str, reason: str) -> Marker:
    return Marker(id="", key=key, text=text, reason=reason, section="recommendations")


def build_unspecified_amounts(
    actions: list[Action],
    action_amounts: dict[str, Value],
    accounts: list[Account],
    *,
    partial_disposals: list[PartialDisposal],
    disposal_quotes: list[str],
    other_unspecified: int,
    taken_keys: set[str],
    available: Value | None,
    skip_action_ids: Collection[str] = frozenset(),
) -> UnspecifiedResult:
    """`taken_keys` are marker keys already built (updated in place), so a key is never
    duplicated. `other_unspecified` counts unspecified amounts built elsewhere (pension
    contribution amounts, the available-now marker) that also feed a new account's balance."""
    in_scope = [a for a in accounts if a.in_scope and not a.is_new]
    has_new_account = any(a.in_scope and a.is_new for a in accounts)
    result = UnspecifiedResult()
    own_upstream: list[Marker] = []
    allowance_markers: dict[str, Marker] = {}
    balance_wanted = False

    for action in actions:
        if action.kind != "action" or action.id in action_amounts:
            continue
        if action.id in skip_action_ids:
            continue  # its amount is already a marker for another reason (R5 conflict)
        if _overlaps_a_disposal(action, disposal_quotes):
            continue
        # An agreed action naming a new account with no amount leaves its opening balance
        # unstated, whether or not it says "fund" ("open a new account for the balance").
        if _names_new_account(action) and has_new_account:
            balance_wanted = True
        if not is_funding_action(action):
            continue
        matched: dict[str, Account] = {}
        for reference in action.accounts:
            for account in accounts_matching_reference(reference, in_scope):
                matched.setdefault(account.id, account)
        for account in matched.values():
            family = classify_wrapper(account.type).allowance_family
            if family == "pension":
                continue  # a pension amount is always a marker, built by limits.py (P4)
            if family is not None:
                key = f"{family}_amounts"
                if key in taken_keys or key in allowance_markers:
                    continue
                marker = _marker(
                    key,
                    f"{family.upper()} top-up amounts",
                    f"the {family.upper()} amounts are not stated in the sources (P2); "
                    f"{_NEVER_ESTIMATED}",
                )
                taken_keys.add(key)
                allowance_markers[key] = marker
            else:
                key = _unique_key(f"{type_slug(account.type)}_addition_amount", taken_keys)
                marker = _marker(
                    key,
                    f"the amount added to the {account.type}"
                    + (f" ({account.platform})" if account.platform else ""),
                    f"the amount to add is not stated in the sources (P2); {_NEVER_ESTIMATED}",
                )
            own_upstream.append(marker)

    for disposal in partial_disposals:
        account = disposal.account
        key = _unique_key(f"{type_slug(account.type)}_portion_sold", taken_keys)
        where = f" ({account.platform})" if account.platform else ""
        own_upstream.append(
            _marker(
                key,
                f"the portion of the {account.type}{where} sold",
                "the portion sold is not stated in the sources (P5); " + _NEVER_ESTIMATED,
            )
        )
        # P5: a portion sold has neither a known amount nor a known destination, whatever
        # the note says about where sale money goes in general.
        money = (
            f" or join the {render_prose(available)} available to invest"
            if available is not None
            else ""
        )
        stated = (
            f"Only a portion of {disposal.reference} is sold"
            if disposal.extent == "portion"
            else f"How much of {disposal.reference} is sold is not stated"
        )
        result.review_items.append(
            ReviewItemInput(
                kind="ambiguity",
                blocking=False,
                detail=(
                    f"{stated}, and the sources do not say whether the proceeds stay in "
                    f"it{money}; confirm the amount and where the money goes."
                ),
                refs=[account.id],
            )
        )

    if balance_wanted:
        if len(own_upstream) == 1 and other_unspecified == 0:
            only = own_upstream[0]
            own_upstream[0] = only.model_copy(update={"text": only.text + _BALANCE_TEXT})
        else:
            key = _unique_key("new_account_balance", taken_keys)
            own_upstream.append(
                _marker(
                    key,
                    "the balance placed into the new account",
                    (
                        "the balance depends on amounts the sources leave unspecified (P5); "
                        if own_upstream or other_unspecified
                        else "the balance is not stated in the sources (P5); "
                    )
                    + _NEVER_ESTIMATED,
                )
            )

    result.markers = own_upstream
    return result
