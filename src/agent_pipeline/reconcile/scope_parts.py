"""R8: a part of the scope phrase that resolves to nothing (SCOPING R8, P9, DESIGN.md 4.3).

The model maps the report instruction's scope phrase to accounts, and can drop a part it cannot
place. A part that names an account type of which the client holds no account at all is never
guessed and never silently dropped: it gets a placeholder table row (`unresolved:<slug>`) with a
value-cell marker, and a blocking scope item naming the instruction field and the phrase. A part
that names a type the client does hold is the mapping's business, not this rule's, and a part that
names no account type is left alone. The type vocabulary is `config/account_types.json`, general
wording only. Pure code, no model call.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from agent_pipeline.ledger import Account, Marker
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.reconcile.wrappers import type_aliases, type_slug

UNRESOLVED_ID_PREFIX = "unresolved:"

_TYPES_PATH = Path("config/account_types.json")
_PART_SPLIT = re.compile(r"\band\b|[,;]", re.IGNORECASE)


def _known_types() -> list[str]:
    raw = json.loads(_TYPES_PATH.read_text(encoding="utf-8"))
    return list(raw["wrappers"])


_KNOWN_TYPES = _known_types()


@dataclass(frozen=True)
class UnresolvedScopePart:
    phrase: str  # the part as written, e.g. "<holder>'s Personal Pension"
    type_text: str  # the account type it names
    owners: list[str] = field(default_factory=list)


@dataclass
class UnresolvedScope:
    accounts: list[Account] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    review_items: list[ReviewItemInput] = field(default_factory=list)


_FILLER = {"and", "the", "of"}


def _tokens(text: str) -> set[str]:
    cleaned = text.lower().replace("&", " ").replace("-", " ")
    return {w for w in re.findall(r"[a-z0-9]+", cleaned) if w not in _FILLER}


def _holds(type_text: str, account_type: str) -> bool:
    """Whether an account's own type wording is the named type: the same words in any order
    ("Stocks and Shares ISA" for "Stocks & Shares ISA"), a fuller name that contains them
    ("Personal Pension Plan", "Self-Invested Personal Pension (SIPP)"), or its standard
    abbreviation ("GIA"). Wording variants of a type the client holds must never read as a
    type the client does not."""
    if account_type.lower() == type_text.lower():
        return True
    if any(alias.lower() == account_type.lower() for alias in type_aliases(type_text)):
        return True
    wanted = _tokens(type_text)
    return bool(wanted) and wanted <= _tokens(account_type)


def _protect_known_types(phrase: str) -> str:
    """ "Stocks and Shares ISA" is one type: write it as the config's "Stocks & Shares ISA"
    before the phrase is split on "and"."""
    for type_text in _KNOWN_TYPES:
        if "&" in type_text:
            variant = re.escape(type_text.replace("&", "and"))
            phrase = re.sub(variant, type_text, phrase, flags=re.IGNORECASE)
    return phrase


def _names(part: str, type_text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(type_text)}(?!\w)", part, re.IGNORECASE) is not None


def unresolved_scope_parts(
    phrase: str, accounts: Sequence[Account], holders: Sequence[str]
) -> list[UnresolvedScopePart]:
    """The parts of `phrase` naming an account type that no account in `accounts` (the
    client's whole account data, in scope or not) has."""
    held = [a.type for a in accounts]
    found: list[UnresolvedScopePart] = []
    for part in _PART_SPLIT.split(_protect_known_types(phrase)):
        part = part.strip()
        for type_text in _KNOWN_TYPES:
            if _names(part, type_text) and not any(_holds(type_text, h) for h in held):
                owners = [h for h in holders if _names(part, h.split()[0])] if holders else []
                found.append(UnresolvedScopePart(part, type_text, owners))
    return found


def build_unresolved_scope(
    parts: Sequence[UnresolvedScopePart], field_label: str
) -> UnresolvedScope:
    built = UnresolvedScope()
    for part in parts:
        slug = type_slug(part.type_text)
        key = f"scope_unresolved_{slug}"
        built.accounts.append(
            Account(
                id=f"{UNRESOLVED_ID_PREFIX}{slug}",
                owners=list(part.owners),
                type=part.type_text,
                in_scope=True,
                scope_reason="named in the report instruction's scope but matches no account (R8)",
                value_marker=key,
            )
        )
        built.markers.append(
            Marker(
                id="",
                key=key,
                text=f'which account(s) are meant by "{part.phrase}" in the report instruction',
                reason="R8: the scope phrase names an account that resolves to nothing",
                section="account_table",
            )
        )
        built.review_items.append(
            ReviewItemInput(
                kind="scope_flag",
                blocking=True,
                detail=(
                    f'the report instruction\'s "{field_label}" field names "{part.phrase}", '
                    f"but the account data has no {part.type_text}; confirm what is meant "
                    "before anything is finalised."
                ),
                refs=[f"{UNRESOLVED_ID_PREFIX}{slug}"],
            )
        )
    return built
