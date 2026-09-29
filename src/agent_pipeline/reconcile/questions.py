"""Open questions for the investigation agent (D14, DESIGN.md section 5.2).

Reconciliation opens a question only where more evidence could change the outcome under the
rules, so a client whose mentions all resolve never reaches the model. Today that is one kind:
`account_link`, a *singular* meeting mention that identifies two or more in-scope accounts by
type, platform or holder wording ("her other account on that platform"). Not a question:

- a plural or all-account reference ("both ISAs", "their ISAs", "the first and second ISAs");
- a mention that identifies one account, or none, or that names nothing an account has;
- a mention whose candidates include at most one in-scope account (a link to an account
  outside scope cannot change the report).

A question records the candidates code's own checks leave, and the accounts other mentions
already pin down (`claimed_ids`): elimination by those is one of the checks that decides an
answer (section 5.2 step 3). Pure code, no model call.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.refs import account_matches_reference

# A reference to every matching account, not to one of them.
_ALL_RE = re.compile(
    r"\b(?:both|all|their|each|every|and|two|three|four|five|several)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class OpenQuestion:
    id: str
    kind: str  # "account_link"
    mention: str
    candidate_ids: tuple[str, ...]
    claimed_ids: tuple[str, ...]
    in_scope_ids: tuple[str, ...]  # the candidates that appear in the report


def _open_accounts(accounts: Sequence[Account]) -> list[Account]:
    """Open, existing accounts, each once (a joint account is listed under both holders)."""
    seen: dict[str, Account] = {}
    for account in accounts:
        if account.status == "open" and not account.is_new:
            seen.setdefault(account.id, account)
    return list(seen.values())


def _named(words: set[str], mention: str) -> set[str]:
    return {w for w in words if re.search(rf"\b{re.escape(w)}\b", mention, re.IGNORECASE)}


def _names_acronym(words: set[str], account: Account) -> bool:
    """A bare acronym the account's type spells in capitals ("ISA", "SIPP"), singular or plural.
    `account_matches_reference` needs the whole type text, so "her ISA" would match nothing and
    every other account would stay a candidate."""
    acronyms = re.findall(r"\b[A-Z]{3,}\b", account.type)
    return any(a.lower() in words or f"{a.lower()}s" in words for a in acronyms)


def mention_candidates(mention: str, accounts: Sequence[Account]) -> list[Account]:
    """The open accounts a mention could mean. Each thing the mention names narrows the set:
    an account type, a platform, a holder's first name. A mention naming none of them
    identifies nothing, so it has no candidates."""
    pool = _open_accounts(accounts)
    narrowed = False

    words = set(re.findall(r"[a-z']+", mention.lower()))
    # A specific type phrase beats a bare acronym: "her Cash ISA" names the Cash ISA and
    # must not widen to every ISA.
    by_type = [a for a in pool if account_matches_reference(mention, a)] or [
        a for a in pool if _names_acronym(words, a)
    ]
    if by_type:
        pool, narrowed = by_type, True

    platforms = _named({a.platform.lower() for a in pool if a.platform}, mention.lower())
    if platforms:
        pool = [a for a in pool if a.platform and a.platform.lower() in platforms]
        narrowed = True

    first_names = {o.split()[0] for a in pool for o in a.owners if o.split()}
    holders = _named(first_names, mention)
    if holders:
        pool = [a for a in pool if any(o.split() and o.split()[0] in holders for o in a.owners)]
        narrowed = True

    return pool if narrowed else []


def _distinct(mentions: Sequence[str]) -> list[str]:
    """The mentions once each, in order (whitespace and case aside): the extraction can list one
    phrase twice, and a repeat is not a second question."""
    seen: set[str] = set()
    kept: list[str] = []
    for mention in mentions:
        key = re.sub(r"\s+", " ", mention).strip().lower()
        if key and key not in seen:
            seen.add(key)
            kept.append(mention.strip())
    return kept


def open_questions(mentions: Sequence[str], accounts: Sequence[Account]) -> list[OpenQuestion]:
    """The questions the rules leave open, in order of appearance (all the same class today,
    so the design's ordering by what a question could change does not yet apply)."""
    singular = [m for m in _distinct(mentions) if not _ALL_RE.search(m)]
    candidates = {m: [a.id for a in mention_candidates(m, accounts)] for m in singular}
    in_scope = {a.id for a in accounts if a.in_scope}
    claimed = {ids[0] for ids in candidates.values() if len(ids) == 1}

    questions: list[OpenQuestion] = []
    for mention in singular:
        ids = candidates[mention]
        if sum(1 for i in ids if i in in_scope) < 2:
            continue
        questions.append(
            OpenQuestion(
                id=f"q{len(questions) + 1}",
                kind="account_link",
                mention=mention,
                candidate_ids=tuple(ids),
                claimed_ids=tuple(sorted(claimed & set(ids))),
                in_scope_ids=tuple(i for i in ids if i in in_scope),
            )
        )
    return questions
