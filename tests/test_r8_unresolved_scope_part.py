"""R8: a part of the scope phrase that resolves to nothing (tests first; hand-written case 11).

SCOPING R8/P9: a scope phrase that names an account type no account of which exists is never
guessed and never silently dropped: it becomes a placeholder table row (`unresolved:<slug>`) with
a value-cell marker, and a blocking scope item naming the instruction field and the phrase. A
part that names a type the client does hold, resolved or not, is the model's mapping to make, not
this rule's. And when the model proposes no account at all for a phrase that code alone can match
exactly, code's own match stands, so a missing optional field does not stop the run (section 8.4).
"""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.scope import resolve_scope
from agent_pipeline.reconcile.scope_parts import (
    UNRESOLVED_ID_PREFIX,
    build_unresolved_scope,
    unresolved_scope_parts,
)

PHRASE = "Holloway Stocks & Shares ISA and Patricia's Personal Pension"
HOLDERS = ["Patricia Nolan"]


def _isa(platform: str | None = "Holloway") -> Account:
    return Account(
        id="L-ISA-01", type="Stocks & Shares ISA", owners=["Patricia Nolan"], platform=platform
    )


def test_a_part_naming_a_type_the_client_does_not_hold_is_unresolved() -> None:
    [part] = unresolved_scope_parts(PHRASE, [_isa()], HOLDERS)
    assert part.phrase == "Patricia's Personal Pension"
    assert part.type_text == "Personal Pension"
    assert part.owners == ["Patricia Nolan"]


def test_a_type_the_client_holds_is_not_this_rules_concern() -> None:
    held = Account(id="P-1", type="Personal Pension", owners=["Patricia Nolan"], in_scope=False)
    assert unresolved_scope_parts(PHRASE, [_isa(), held], HOLDERS) == []


def test_parts_that_name_no_account_type_are_ignored() -> None:
    assert unresolved_scope_parts("David's and Susan's Stocks & Shares ISAs", [_isa()], []) == []


def test_a_type_word_must_stand_alone_not_inside_another_word() -> None:
    assert unresolved_scope_parts("the SIPPs and the ISA", [_isa()], []) == []


def test_the_placeholder_row_marker_and_blocking_item() -> None:
    [part] = unresolved_scope_parts(PHRASE, [_isa()], HOLDERS)
    built = build_unresolved_scope([part], "Accounts covered")
    [account] = built.accounts
    assert account.id == f"{UNRESOLVED_ID_PREFIX}personal_pension" and account.in_scope
    assert account.type == "Personal Pension" and account.owners == ["Patricia Nolan"]
    assert account.value is None and account.value_marker == "scope_unresolved_personal_pension"
    [marker] = built.markers
    assert marker.key == "scope_unresolved_personal_pension" and marker.section == "account_table"
    assert "Patricia's Personal Pension" in marker.text
    [item] = built.review_items
    assert item.kind == "scope_flag" and item.blocking
    assert "Personal Pension" in item.detail and "Accounts covered" in item.detail


def test_no_unresolved_parts_builds_nothing() -> None:
    built = build_unresolved_scope([], "Accounts covered")
    assert (built.accounts, built.markers, built.review_items) == ([], [], [])


def test_an_empty_model_proposal_falls_back_to_code_s_own_exact_match() -> None:
    cash = Account(id="S-CASH-01", type="Cash Account", owners=["M S"], platform="Holloway")
    result = resolve_scope("Holloway Stocks & Shares ISA", [_isa(platform=None), cash], ["bogus"])
    assert result.resolved_ids == ["L-ISA-01"] and not result.unresolved


def test_a_proposal_that_verifies_is_still_taken_as_is() -> None:
    cash = Account(id="S-CASH-01", type="Cash Account", owners=["M S"], platform="Holloway")
    result = resolve_scope("anything", [_isa(), cash], ["S-CASH-01"])
    assert result.resolved_ids == ["S-CASH-01"]


def test_no_proposal_and_no_exact_match_is_still_unresolved() -> None:
    assert resolve_scope("Holloway Personal Pension", [_isa()], ["bogus"]).unresolved
