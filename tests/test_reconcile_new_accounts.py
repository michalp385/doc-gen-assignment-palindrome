"""New accounts the advice creates (R1, P9, P2), tests first.

An account the plan opens is not in the account data. R1: a new account must be in the report
instruction's scope; one mentioned only in the meeting record is a conflict for the review sheet.
P9: it shows in the table as "To be opened", with the report instruction's wording for its type
(a general "New joint account" / "New account" here), and its platform, if unstated, goes to
the review sheet. P2: its charges are a marker. Built in code from verified mentions; the model
only says a new account was agreed and whether it is joint.
"""

from __future__ import annotations

from agent_pipeline.reconcile.new_accounts import (
    NewAccountMention,
    build_new_accounts,
    scope_names_new_account,
)

HOLDERS = ["Robert Fletcher", "Jean Fletcher"]
JOINT = NewAccountMention(quote="open a new jointly-held investment account", joint=True)


# --- the scope phrase ------------------------------------------------------------------------


def test_a_scope_phrase_naming_a_new_account_is_recognised() -> None:
    for phrase in (
        "Holloway ISAs (Robert and Jean), the joint GIA, and a new joint account",
        "the ISAs plus a new joint account for the proceeds",
        "Holloway ISAs and a new investment account",
        "A NEW JOINT ACCOUNT",
    ):
        assert scope_names_new_account(phrase), phrase


def test_a_scope_phrase_without_one_is_not() -> None:
    for phrase in (
        "Holloway ISAs (David and Susan) and the joint GIA",
        "the Newcastle branch account",
        "renewal of the existing account",
        "",
    ):
        assert not scope_names_new_account(phrase), phrase


# --- building the account --------------------------------------------------------------------


def test_a_joint_new_account_is_owned_by_every_holder_and_to_be_opened() -> None:
    result = build_new_accounts([JOINT], "the ISAs and a new joint account", HOLDERS)
    (account,) = result.accounts
    assert account.id == "new:joint_investment_account"
    assert account.owners == HOLDERS
    assert account.type == "New joint account"
    assert account.is_new is True
    assert account.in_scope is True
    assert account.value is None
    assert account.platform is None


def test_the_charges_marker_and_the_type_and_platform_review_item_are_built() -> None:
    result = build_new_accounts([JOINT], "the ISAs and a new joint account", HOLDERS)
    (marker,) = result.markers
    assert marker.key == "new_account_charges"
    assert marker.text == "charges on the new joint account"
    assert marker.section == "fees_charges"
    assert not any(ch.isdigit() for ch in marker.text)
    (item,) = result.review_items
    assert item.kind == "scope_flag"
    assert item.blocking is False
    for word in ("new", "joint", "account"):
        assert word in item.detail
    assert item.refs == ["new:joint_investment_account"]


def test_a_single_holder_new_account_is_owned_by_the_holder_named() -> None:
    mention = NewAccountMention(
        quote="open a new investment account for Jean", joint=False, owner_references=("Jean",)
    )
    result = build_new_accounts([mention], "the ISAs and a new account", HOLDERS)
    (account,) = result.accounts
    assert account.owners == ["Jean Fletcher"]
    assert account.type == "New account"
    assert account.id == "new:investment_account"
    assert result.markers[0].text == "charges on the new account"


def test_a_single_holder_account_whose_owner_cannot_be_resolved_is_flagged_not_built() -> None:
    mention = NewAccountMention(quote="a new account", joint=False, owner_references=("Someone",))
    result = build_new_accounts([mention], "the ISAs and a new account", HOLDERS)
    assert result.accounts == []
    assert [i.kind for i in result.review_items] == ["ambiguity"]


def test_the_same_new_account_mentioned_twice_is_built_once() -> None:
    again = NewAccountMention(quote="the new joint investment account for the balance", joint=True)
    result = build_new_accounts([JOINT, again], "and a new joint account", HOLDERS)
    assert len(result.accounts) == 1
    assert len(result.markers) == 1


def test_two_different_new_accounts_get_distinct_ids_and_one_charges_marker_each_kind() -> None:
    single = NewAccountMention(
        quote="a new account for Robert", joint=False, owner_references=("Robert",)
    )
    result = build_new_accounts(
        [JOINT, single], "and a new joint account and a new account", HOLDERS
    )
    assert {a.id for a in result.accounts} == {
        "new:joint_investment_account",
        "new:investment_account",
    }
    assert {m.key for m in result.markers} == {"new_account_charges", "new_account_charges_2"}


# --- R1: not in the scope ---------------------------------------------------------------------


def test_a_new_account_the_scope_does_not_name_is_a_conflict_and_not_built() -> None:
    result = build_new_accounts([JOINT], "the Holloway ISAs and the joint GIA", HOLDERS)
    assert result.accounts == []
    assert result.markers == []
    (item,) = result.review_items
    assert item.kind == "conflict"
    assert item.blocking is False
    assert "scope" in item.detail


def test_no_mentions_builds_nothing_and_says_nothing() -> None:
    result = build_new_accounts([], "the ISAs and a new joint account", HOLDERS)
    assert (result.accounts, result.markers, result.review_items) == ([], [], [])
