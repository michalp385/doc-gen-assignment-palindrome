"""A reference that drops a generic word of an account type still matches it (tests first; case 10).

"the Meridian offshore bond" names an "Offshore Investment Bond": the type's distinctive words
(here "offshore" and "bond") are all there, and only the generic "Investment" is missing. A type
with a single distinctive word ("General Investment Account", "Cash Account") is left to the
existing whole-wording rule, or the word alone would match every loose mention.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.refs import accounts_matching_reference


def _account(account_id: str, type_: str) -> Account:
    return Account(id=account_id, type=type_, owners=["A B"], platform="P", in_scope=True)


OFFSHORE = _account("B-OFF", "Offshore Investment Bond")
ONSHORE = _account("B-ON", "Onshore Investment Bond")
GIA = _account("G-1", "General Investment Account")
ISA = _account("I-1", "Stocks & Shares ISA")


def test_a_reference_dropping_a_generic_word_matches_the_type() -> None:
    found = accounts_matching_reference("the Meridian offshore bond", [OFFSHORE, ONSHORE, GIA])
    assert [a.id for a in found] == ["B-OFF"]


def test_the_other_bond_is_told_apart_by_its_distinctive_word() -> None:
    assert [a.id for a in accounts_matching_reference("her onshore bond", [OFFSHORE, ONSHORE])] == [
        "B-ON"
    ]


def test_one_distinctive_word_is_not_enough() -> None:
    assert accounts_matching_reference("the general update", [GIA]) == []
    assert accounts_matching_reference("his bond", [OFFSHORE, ONSHORE]) == []


def test_the_whole_type_wording_still_matches_as_before() -> None:
    assert [a.id for a in accounts_matching_reference("Stocks & Shares ISA", [ISA, GIA])] == ["I-1"]


def test_all_distinctive_words_are_required() -> None:
    assert accounts_matching_reference("her shares", [ISA]) == []
