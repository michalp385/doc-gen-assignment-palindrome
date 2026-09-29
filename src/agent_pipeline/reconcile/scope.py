"""R2, R8: which accounts a report instruction's scope phrase covers.

DESIGN.md section 5's own function table: `resolve_scope` "runs the scope checks (§4.3) on
the model's proposed mapping, in code" -- `extract/instruction.py`'s `propose_scope` (T10)
already asks a model for a `candidate_account_ids` mapping, since a phrase naming several
accounts in free language (T19, e.g. "the ISAs held jointly by the two account holders and
the joint GIA") doesn't literally contain any one account's type wording as a substring the
way a single-account phrase naming its exact type wording does. Code's job is never to
re-derive that language judgment -- it only checks the proposal isn't hallucinated (every
candidate id must be a real account) and never guesses when nothing real was proposed.

`candidate_account_ids=None` (no model proposal reached this call -- a degraded extraction,
or a caller that hasn't been given one) falls back to the original phrase/type/platform
substring match, unchanged from before T19: exactly one match resolves it; zero or more
than one is unresolved (R8's own "resolves to nothing" / "matches more than it names").
That fallback is the *only* path that still needs an account's type or platform wording to
literally appear in the phrase -- once a real candidate list exists, resolving to several
accounts is the expected, valid outcome for a phrase that names several things, not R8's
ambiguity case (which is about an accidental substring collision, not genuine plurality).

TODO(M2): the plan's T8 interface line names a third fallback-path check, matching an
owning holder's name in the phrase (needed once two same-type, same-platform accounts held
by different people can collide under the *substring* fallback specifically). No client has
that shape yet -- doing so without a real example to test against risks a heuristic that
matches the wrong owner's name inside unrelated text (verifier report, T8 checkpoint,
finding #8).
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


def resolve_scope(
    phrase: str, accounts: list[Account], candidate_account_ids: list[str] | None = None
) -> ScopeResult:
    if candidate_account_ids is not None:
        known_ids = {a.id for a in accounts}
        # Existence is the only check code can make on a language judgment it didn't make
        # itself -- a hallucinated id is dropped, never trusted; deduped, order kept.
        seen: set[str] = set()
        verified = [
            aid
            for aid in candidate_account_ids
            if aid in known_ids and not (aid in seen or seen.add(aid))
        ]
        if verified:
            return ScopeResult(phrase=phrase, resolved_ids=verified, unresolved=False)
        # The proposal placed nothing real. Code's own exact match still stands: it needs no
        # language judgment, and a missing optional field (section 8.4) must not stop a run.

    matches = [a.id for a in accounts if _phrase_matches(phrase, a)]
    if len(matches) == 1:
        return ScopeResult(phrase=phrase, resolved_ids=matches, unresolved=False)
    # Zero matches (R8: "resolves to nothing") or more than one (R8: "matches more than it
    # names") are both flagged, never guessed.
    return ScopeResult(phrase=phrase, resolved_ids=[], unresolved=True)
