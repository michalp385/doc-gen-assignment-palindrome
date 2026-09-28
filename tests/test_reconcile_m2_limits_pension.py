"""P4 for pensions, tests first (T20/T21): pension contribution amounts are always adviser-
review markers -- the pipeline never attempts a tax calculation, because pension limits depend
on personal circumstances, earlier contributions, tapering and carry-forward -- whether or not
the sources state an amount (client 04: "SIPP contributions for both, sized within
allowances", no figure at all).

The marker key names the account's own type wording ("sipp_contribution_amounts"), so it
generalises to "Personal Pension" and any other pension type in `config/account_types.json`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from agent_pipeline.ledger import Account, Action
from agent_pipeline.reconcile.limits import (
    PriorUse,
    check_limits,
    pension_contribution_accounts,
    pension_contribution_markers,
    pension_review_item,
)

MEETING_DATE = date(2026, 5, 20)


def _account(
    account_id: str,
    type_: str,
    *,
    in_scope: bool = True,
    owner: str = "James Whitmore",
) -> Account:
    return Account(
        id=account_id, owners=[owner], type=type_, platform="Brightwell", in_scope=in_scope
    )


def _action(action_id: str, *refs: str, kind: Literal["action", "non_action"] = "action") -> Action:
    return Action(id=action_id, description="contribute", accounts=list(refs), kind=kind)


def test_a_pension_amount_is_always_a_marker_whatever_the_amount_or_prior_use() -> None:
    prior_uses: list[PriorUse] = ["confirmed", "denied", "unknown"]
    for prior_use in prior_uses:
        result = check_limits(Decimal("1"), "pension", prior_use, MEETING_DATE)
        assert result.marker is True
        assert "pension" in result.reason


def test_the_isa_rules_are_unchanged_by_the_pension_rule() -> None:
    assert check_limits(Decimal("20000"), "isa", "unknown", MEETING_DATE).marker is False


def test_an_action_naming_an_in_scope_sipp_selects_it_with_no_amount_needed() -> None:
    sipp = _account("B4-SIPP-J", "SIPP")
    accounts = pension_contribution_accounts([_action("a1", "SIPP")], [sipp])
    assert [a.id for a in accounts] == ["B4-SIPP-J"]


def test_both_partners_sipps_are_selected_from_one_action() -> None:
    james = _account("B4-SIPP-J", "SIPP", owner="James Whitmore")
    caroline = _account("B4-SIPP-C", "SIPP", owner="Caroline Whitmore")
    accounts = pension_contribution_accounts(
        [_action("a1", "James's SIPP", "Caroline's SIPP")], [james, caroline]
    )
    assert {a.id for a in accounts} == {"B4-SIPP-J", "B4-SIPP-C"}


def test_an_ambiguous_reference_selects_every_matching_pension_never_none() -> None:
    # "the SIPPs" names both partners' accounts: neither is dropped for being ambiguous
    james = _account("B4-SIPP-J", "SIPP", owner="James Whitmore")
    caroline = _account("B4-SIPP-C", "SIPP", owner="Caroline Whitmore")
    accounts = pension_contribution_accounts([_action("a1", "SIPP")], [james, caroline])
    assert {a.id for a in accounts} == {"B4-SIPP-J", "B4-SIPP-C"}


def test_an_out_of_scope_pension_is_never_selected() -> None:
    sipp = _account("B4-SIPP-J", "SIPP", in_scope=False)
    assert pension_contribution_accounts([_action("a1", "SIPP")], [sipp]) == []


def test_an_agreed_non_action_never_selects_a_pension() -> None:
    sipp = _account("B4-SIPP-J", "SIPP")
    assert pension_contribution_accounts([_action("a1", "SIPP", kind="non_action")], [sipp]) == []


def test_a_non_pension_account_is_never_selected() -> None:
    isa = _account("H-ISA-J", "Stocks & Shares ISA")
    assert pension_contribution_accounts([_action("a1", "Stocks & Shares ISA")], [isa]) == []


def test_an_account_named_by_two_actions_is_selected_once() -> None:
    sipp = _account("B4-SIPP-J", "SIPP")
    accounts = pension_contribution_accounts([_action("a1", "SIPP"), _action("a2", "SIPP")], [sipp])
    assert len(accounts) == 1


def test_one_marker_per_pension_type_named_after_the_type() -> None:
    james = _account("B4-SIPP-J", "SIPP", owner="James Whitmore")
    caroline = _account("B4-SIPP-C", "SIPP", owner="Caroline Whitmore")
    (marker,) = pension_contribution_markers([james, caroline])
    assert marker.key == "sipp_contribution_amounts"
    assert marker.section == "recommendations"
    assert "SIPP" in marker.text
    assert not any(ch.isdigit() for ch in marker.text)


def test_two_pension_types_get_two_markers() -> None:
    markers = pension_contribution_markers(
        [_account("A", "SIPP"), _account("B", "Personal Pension")]
    )
    assert [m.key for m in markers] == [
        "sipp_contribution_amounts",
        "personal_pension_contribution_amounts",
    ]


def test_no_pension_accounts_no_markers() -> None:
    assert pension_contribution_markers([]) == []


def test_the_review_item_names_the_accounts_and_never_states_a_limit() -> None:
    james = _account("B4-SIPP-J", "SIPP")
    caroline = _account("B4-SIPP-C", "SIPP", owner="Caroline Whitmore")
    item = pension_review_item([james, caroline])
    assert item is not None
    assert item.kind == "p4_note"
    assert item.blocking is False
    assert item.refs == ["B4-SIPP-J", "B4-SIPP-C"]
    assert not any(ch.isdigit() for ch in item.detail)
    assert "carry-forward" in item.detail


def test_no_pension_accounts_no_review_item() -> None:
    assert pension_review_item([]) is None
