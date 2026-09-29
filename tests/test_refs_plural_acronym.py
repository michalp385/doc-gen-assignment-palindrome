"""A plural acronym in an action's account reference matches the account type (tests first).

"Ann's ISAs" names her Stocks & Shares ISA; a bare plural of an ordinary word ("accounts")
never matches every account.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.refs import accounts_matching_reference


def _account(account_id: str, type_: str, owner: str) -> Account:
    return Account(id=account_id, type=type_, owners=[owner], in_scope=True)


ANN_ISA = _account("A-ISA", "Stocks & Shares ISA", "Ann Poe")
BOB_ISA = _account("B-ISA", "Stocks & Shares ISA", "Bob Poe")
GIA = _account("G-1", "General Investment Account", "Ann Poe")
SIPP = _account("S-1", "SIPP", "Ann Poe")


def test_possessive_plural_acronym_matches_that_owners_account() -> None:
    found = accounts_matching_reference("Ann's ISAs", [ANN_ISA, BOB_ISA, GIA])
    assert [a.id for a in found] == ["A-ISA"]


def test_bare_plural_acronym_matches_every_account_of_the_type() -> None:
    found = accounts_matching_reference("both ISAs", [ANN_ISA, BOB_ISA, GIA])
    assert {a.id for a in found} == {"A-ISA", "B-ISA"}


def test_plural_pension_acronym_matches() -> None:
    assert [a.id for a in accounts_matching_reference("both SIPPs", [ANN_ISA, SIPP])] == ["S-1"]


def test_plural_of_an_ordinary_word_matches_nothing() -> None:
    assert accounts_matching_reference("the accounts", [ANN_ISA, GIA, SIPP]) == []
