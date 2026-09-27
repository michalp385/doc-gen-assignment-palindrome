"""R2, R8: which accounts a report instruction's scope phrase covers.

A phrase is matched in code against each candidate account's own type and platform
wording -- never guessed. Exactly one match resolves the phrase; zero or more than one is
unresolved and must never be silently guessed (R8). A model may eventually *propose* a
mapping (DESIGN.md section 4.3); this function is the check that decides whether to trust
it, run here directly on the phrase text since M0b has no model stage yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_pipeline.ledger import Account


@dataclass(frozen=True)
class ScopeResult:
    phrase: str
    resolved_ids: list[str] = field(default_factory=list)
    unresolved: bool = False


def _phrase_matches(phrase: str, account: Account) -> bool:
    lowered = phrase.lower()
    if account.type and account.type.lower() not in lowered:
        return False
    if account.platform and account.platform.lower() not in lowered:
        return False
    return True


def resolve_scope(phrase: str, accounts: list[Account]) -> ScopeResult:
    matches = [a.id for a in accounts if _phrase_matches(phrase, a)]
    if len(matches) == 1:
        return ScopeResult(phrase=phrase, resolved_ids=matches, unresolved=False)
    # Zero matches (R8: "resolves to nothing") or more than one (R8: "matches more than it
    # names") are both flagged, never guessed.
    return ScopeResult(phrase=phrase, resolved_ids=[], unresolved=True)
