"""T19: `account_matches_reference` -- a free-text account reference and an account's own
type wording can be a substring of either (a short canonical reference of a longer
descriptive one, or vice versa), and a standard abbreviation ("GIA") that appears in
neither direction is checked as a whole word via `config/account_types.json`'s aliases.
Discovered against client 02's real extraction (live run, T19 checkpoint): neither a
single-direction substring check nor a bare-substring alias check covered its real
references ("David's Stocks & Shares ISA", "jointly-held General Investment Account on the
Holloway platform", "joint GIA")."""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.refs import account_matches_reference, accounts_matching_reference


def _gia() -> Account:
    return Account(
        id="H-GIA-J",
        owners=["David Clarke", "Susan Clarke"],
        type="General Investment Account",
        platform="Holloway",
    )


def _isa(owner: str, account_id: str) -> Account:
    return Account(id=account_id, owners=[owner], type="Stocks & Shares ISA", platform="Holloway")


def test_a_short_canonical_reference_matches_a_longer_descriptive_type() -> None:
    assert account_matches_reference("Stocks & Shares ISA", _isa("David Clarke", "H-ISA-D"))


def test_a_longer_possessive_reference_matches_the_short_canonical_type() -> None:
    assert account_matches_reference("David's Stocks & Shares ISA", _isa("David Clarke", "H-ISA-D"))


def test_a_long_descriptive_reference_containing_the_type_text_matches() -> None:
    account = _gia()
    assert account_matches_reference(
        "jointly-held General Investment Account on the Holloway platform", account
    )


def test_a_standard_abbreviation_matches_via_the_alias_list() -> None:
    assert account_matches_reference("joint GIA", _gia())
    assert account_matches_reference("the GIA", _gia())


def test_an_alias_is_matched_as_a_whole_word_not_a_raw_substring() -> None:
    # A short alias could otherwise spuriously match inside an unrelated longer word.
    assert account_matches_reference("regia", _gia()) is False


def test_an_unrelated_reference_matches_nothing() -> None:
    assert account_matches_reference("the cash account", _gia()) is False


def test_accounts_matching_reference_filters_a_list() -> None:
    accounts = [_gia(), _isa("David Clarke", "H-ISA-D"), _isa("Susan Clarke", "H-ISA-S")]
    assert [a.id for a in accounts_matching_reference("the joint GIA", accounts)] == ["H-GIA-J"]
    assert {a.id for a in accounts_matching_reference("Stocks & Shares ISA", accounts)} == {
        "H-ISA-D",
        "H-ISA-S",
    }


def test_a_possessive_reference_narrows_two_same_type_accounts_by_owner() -> None:
    # T19 checkpoint: without owner narrowing, "David's Stocks & Shares ISA" matched *both*
    # ISAs (type alone can't tell them apart), so it never resolved to exactly one -- P4's
    # limit check silently never ran for either ISA in a real live run.
    accounts = [_isa("David Clarke", "H-ISA-D"), _isa("Susan Clarke", "H-ISA-S")]
    assert [a.id for a in accounts_matching_reference("David's Stocks & Shares ISA", accounts)] == [
        "H-ISA-D"
    ]
    assert [a.id for a in accounts_matching_reference("Susan's Stocks & Shares ISA", accounts)] == [
        "H-ISA-S"
    ]


def test_a_reference_naming_no_owner_stays_ambiguous_across_same_type_accounts() -> None:
    accounts = [_isa("David Clarke", "H-ISA-D"), _isa("Susan Clarke", "H-ISA-S")]
    assert {a.id for a in accounts_matching_reference("Stocks & Shares ISA", accounts)} == {
        "H-ISA-D",
        "H-ISA-S",
    }
