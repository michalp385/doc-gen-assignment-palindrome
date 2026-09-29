"""R1, P9, P2: an account the advice creates.

A new account is not in the account data. R1: it must be in the report instruction's scope; one
mentioned only in the meeting record is a conflict for the review sheet, never a table row. P9:
it shows in the table as "To be opened", its type in a general wording ("New joint account",
"New account"), its platform, unstated, going to the review sheet. P2: its charges are a marker.

Built in code from verified mentions. The model only says that a new account was agreed and
whether it is joint (and, if not, whose); the owners come from the account data's holders, the
id, type, marker and review items from here. Pure code, no model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_pipeline.ledger import Account, Marker
from agent_pipeline.reconcile.review import ReviewItemInput

# A built account's id is synthetic (no id exists in the data); never shown to a client.
SYNTHETIC_ID_PREFIX = "new:"
# What the client-facing table shows in the account cell of a built account.
NEW_ACCOUNT_LABEL = "To be opened"
_NEVER_ESTIMATED = "never estimated (CLAUDE.md non-negotiable)"
_SCOPE_NEW_ACCOUNT_RE = re.compile(r"\bnew\b(?:\s+[a-z-]+){0,3}?\s+account\b", re.IGNORECASE)


@dataclass(frozen=True)
class NewAccountMention:
    """A verified meeting mention of an account the plan opens."""

    quote: str
    joint: bool
    owner_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewAccountResult:
    accounts: list[Account] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    review_items: list[ReviewItemInput] = field(default_factory=list)


def scope_names_new_account(scope_phrase: str) -> bool:
    """Whether the report instruction's scope phrase names an account to be opened
    ("... and a new joint account"). Whole-word: "Newcastle" is not "new"."""
    return _SCOPE_NEW_ACCOUNT_RE.search(scope_phrase) is not None


def _resolve_owner(reference: str, holders: list[str]) -> str | None:
    """A holder named by full name or first name, whole-word and case-insensitive."""
    wanted = reference.strip().lower()
    for holder in holders:
        if wanted == holder.lower() or wanted == holder.split()[0].lower():
            return holder
    return None


def build_new_accounts(
    mentions: list[NewAccountMention], scope_phrase: str, holders: list[str]
) -> NewAccountResult:
    if not mentions:
        return NewAccountResult()
    if not scope_names_new_account(scope_phrase):
        return NewAccountResult(
            review_items=[
                ReviewItemInput(
                    kind="conflict",
                    blocking=False,
                    detail=(
                        "the meeting record mentions a new account, but the report "
                        "instruction's scope does not name one; no new account is shown."
                    ),
                    refs=[],
                )
            ]
        )

    unique_holders = list(dict.fromkeys(holders))
    accounts: list[Account] = []
    review_items: list[ReviewItemInput] = []
    seen: set[tuple[bool, tuple[str, ...]]] = set()
    slug_counts: dict[str, int] = {}
    kinds: list[bool] = []  # joint flags in order of first appearance

    for mention in mentions:
        if mention.joint:
            owners = unique_holders
        else:
            references = list(mention.owner_references) or (
                unique_holders if len(unique_holders) == 1 else []
            )
            resolved = [_resolve_owner(r, unique_holders) for r in references]
            if not references or any(owner is None for owner in resolved):
                review_items.append(
                    ReviewItemInput(
                        kind="ambiguity",
                        blocking=False,
                        detail=(
                            "a new account is agreed but its owner cannot be resolved to a "
                            f"holder ({', '.join(references) or 'none named'}); it is not shown."
                        ),
                        refs=[],
                    )
                )
                continue
            owners = [o for o in resolved if o is not None]
        key = (mention.joint, tuple(owners))
        if key in seen:
            continue
        seen.add(key)
        if mention.joint not in kinds:
            kinds.append(mention.joint)
        base = "joint_investment_account" if mention.joint else "investment_account"
        slug_counts[base] = slug_counts.get(base, 0) + 1
        slug = base if slug_counts[base] == 1 else f"{base}_{slug_counts[base]}"
        account_type = "New joint account" if mention.joint else "New account"
        accounts.append(
            Account(
                id=f"{SYNTHETIC_ID_PREFIX}{slug}",
                owners=list(owners),
                type=account_type,
                platform=None,
                in_scope=True,
                is_new=True,
                value=None,
            )
        )
        review_items.append(
            ReviewItemInput(
                kind="scope_flag",
                blocking=False,
                detail=(
                    f"{account_type.lower()}: its type and platform are not stated in the "
                    "sources; confirm both."
                ),
                refs=[f"{SYNTHETIC_ID_PREFIX}{slug}"],
            )
        )

    markers = [
        Marker(
            id="",
            key="new_account_charges" if position == 0 else f"new_account_charges_{position + 1}",
            text="charges on the new joint account" if joint else "charges on the new account",
            reason=_NEVER_ESTIMATED,
            section="fees_charges",
        )
        for position, joint in enumerate(kinds)
    ]
    return NewAccountResult(accounts=accounts, markers=markers, review_items=review_items)
