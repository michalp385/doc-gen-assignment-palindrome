"""Matches a free-text account reference (a meeting extraction's `account_reference`,
`accounts_referenced` or a scope phrase's fallback path) to a real account, in code (T19).

A reference and an account's own type wording can be a substring of *either*: a short
canonical reference ("Stocks & Shares ISA") is a substring of a longer possessive one
("their Stocks & Shares ISA"), but a long descriptive reference ("the jointly-held General
Investment Account on the platform") contains the short canonical type text as *its own*
substring instead -- checking only one direction missed real cases in both this codebase's
history (verifier report, T8 checkpoint, finding #8, about a different ambiguity) and a
live run against client 02 (T19 checkpoint: neither direction alone matched a possessive
ISA reference or the GIA's own long-form mention).

A standard industry abbreviation ("GIA") never appears as a substring of its canonical type
text in either direction at all, so `wrappers.type_aliases` is checked as a whole word (not
a raw substring: a short alias could otherwise spuriously match inside an unrelated longer
word, the same risk `values.py::match_image_row` already guards against for owner names).
"""

from __future__ import annotations

import re

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.wrappers import type_aliases

# Words every account type shares; they say nothing about which type is meant.
_GENERIC_TYPE_WORDS = {"investment", "account", "the", "and", "of"}


def account_matches_reference(reference: str, account: Account) -> bool:
    ref = reference.lower()
    account_type = account.type.lower()
    if account_type in ref or ref in account_type:
        return True
    ref_words = set(re.findall(r"[a-z']+", ref))
    if any(alias.lower() in ref_words for alias in type_aliases(account.type)):
        return True
    # A plural of an acronym the type itself spells in capitals ("ISAs" for "Stocks & Shares
    # ISA"); never a plural of an ordinary word, which would match every account.
    acronyms = re.findall(r"\b[A-Z]{3,}\b", account.type)
    if any(f"{acronym.lower()}s" in ref_words for acronym in acronyms):
        return True
    # A reference that drops a generic word of the type ("offshore bond" for "Offshore
    # Investment Bond"): every distinctive word of a type that has at least two. A type
    # with one ("General Investment Account") is left to the whole-wording rule above.
    distinctive = [w for w in re.findall(r"[a-z']+", account_type) if w not in _GENERIC_TYPE_WORDS]
    return len(distinctive) >= 2 and all(w in ref_words for w in distinctive)


def accounts_matching_reference(reference: str, accounts: list[Account]) -> list[Account]:
    """Two same-type accounts (client 02's two ISAs, one per co-holder) both match a
    type-only check, however the reference phrases it (a possessive owner reference or the
    bare type alone) -- type wording alone can never tell them apart, since neither
    account's own `type` encodes who owns it. Narrowed by owner's first name as a whole
    word in the reference, same convention `values.py::match_image_row` already uses for
    the identical ambiguity on statement-image rows (T19 checkpoint: without this, a
    possessive reference matched *both* ISAs, so neither ever resolved to exactly one --
    P4's limit check silently never ran for either)."""
    matches = [a for a in accounts if account_matches_reference(reference, a)]
    if len(matches) <= 1:
        return matches
    # A platform named in the reference narrows two same-type accounts on different
    # platforms; whole-word match, and only when it narrows at all.
    lowered = reference.lower()
    by_platform = [
        a
        for a in matches
        if a.platform
        and re.search(rf"(?<![a-z0-9]){re.escape(a.platform.lower())}(?![a-z0-9])", lowered)
    ]
    if by_platform and len(by_platform) < len(matches):
        matches = by_platform
        if len(matches) == 1:
            return matches
    # No apostrophe in the character class: a possessive ("Name's") must tokenise to the
    # plain name, not "name's" as one glued word that never equals an owner's own name.
    ref_words = set(re.findall(r"[a-z]+", lowered))
    by_owner = [a for a in matches if any(o.split()[0].lower() in ref_words for o in a.owners)]
    return by_owner if len(by_owner) == 1 else matches
