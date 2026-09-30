"""Two different holders can share a first name. Wording that uses first names must then use full
names, and a directive that names only a shared first name must not be applied to whichever holder
happens to come first: it is a review item, like any person the account data cannot resolve."""

from __future__ import annotations

from agent_pipeline.extract.guidance import (
    RawDirective,
    RawGuidanceProposal,
    extract_directives,
)
from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.marker_text import accounts_phrase


def _isa(id_: str, owner: str) -> Account:
    return Account(
        id=id_, owners=[owner], type="Stocks & Shares ISA", platform="Northgate", in_scope=True
    )


def test_two_holders_with_one_first_name_are_told_apart_in_an_account_phrase() -> None:
    phrase = accounts_phrase([_isa("a", "John Smith"), _isa("b", "John Brown")])

    assert "John Smith's Stocks & Shares ISA, Northgate" in phrase
    assert "John Brown's Stocks & Shares ISA, Northgate" in phrase


def test_distinct_first_names_still_read_as_first_names() -> None:
    phrase = accounts_phrase([_isa("a", "John Smith"), _isa("b", "Mary Brown")])

    assert phrase == "John's Stocks & Shares ISA, Northgate; Mary's Stocks & Shares ISA, Northgate"


GUIDANCE = (
    "General notes.\n\nTreat the money's origin with appropriate sensitivity for this client.\n"
)
EVIDENCE = "Treat the money's origin with appropriate sensitivity for this client."


class _Model:
    def __init__(self, *directives: RawDirective) -> None:
        self.directives = list(directives)

    def propose(self, guidance_text: str, people: list[str], sections: list[str]):
        return RawGuidanceProposal(directives=self.directives)


def _directive(person: str) -> RawDirective:
    return RawDirective(
        sections=["background_objectives"],
        instruction="Describe the source of the new money gently and briefly.",
        person=person,
        evidence=EVIDENCE,
    )


def test_a_directive_naming_a_shared_first_name_is_not_applied_to_either_holder() -> None:
    result = extract_directives(
        GUIDANCE,
        ["John Smith", "John Brown"],
        ["background_objectives"],
        _Model(_directive("John")),
    )

    assert result.directives == []
    (item,) = result.review_items
    assert item.kind == "ambiguity" and item.blocking is False
    assert "more than one holder" in item.detail


def test_a_full_name_still_resolves_when_first_names_are_shared() -> None:
    result = extract_directives(
        GUIDANCE,
        ["John Smith", "John Brown"],
        ["background_objectives"],
        _Model(_directive("John Brown")),
    )

    (directive,) = result.directives
    assert directive.person == "John Brown"
