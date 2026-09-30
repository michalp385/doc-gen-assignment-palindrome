"""Marker descriptions are built in code from the ledger so each names what it concerns (the
account and platform, the holders, the exact charges), with no figure in the text. The key of
every marker is unchanged: G14 matches on key, and there is one marker per key."""

from __future__ import annotations

import re

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.limits import limit_marker, pension_contribution_markers
from agent_pipeline.reconcile.marker_text import (
    account_phrase,
    each_holder_phrase,
    holders_phrase,
    join_natural,
)
from agent_pipeline.reconcile.markers import cgt_marker, required_markers
from agent_pipeline.reconcile.new_accounts import NewAccountMention, build_new_accounts
from agent_pipeline.reconcile.sections import Disposal


def _acct(id_: str, owners: list[str], type_: str, platform: str | None = "Holloway") -> Account:
    return Account(id=id_, owners=owners, type=type_, platform=platform, in_scope=True)


JOINT_GIA = _acct("g1", ["James Whitmore", "Caroline Whitmore"], "General Investment Account")
JAMES_SIPP = _acct("s1", ["James Whitmore"], "SIPP", "Brightwell")
CAROLINE_SIPP = _acct("s2", ["Caroline Whitmore"], "SIPP", "Brightwell")


def test_join_natural() -> None:
    assert join_natural([]) == ""
    assert join_natural(["A"]) == "A"
    assert join_natural(["A", "B"]) == "A and B"
    assert join_natural(["A", "B", "C"]) == "A, B and C"


def test_holders_use_first_names_unless_two_holders_share_one() -> None:
    assert holders_phrase(["James Whitmore", "Caroline Whitmore"]) == "James and Caroline"
    assert holders_phrase(["James Whitmore", "James Ashby"]) == "James Whitmore and James Ashby"
    assert holders_phrase(["James Whitmore", "James Whitmore"]) == "James"


def test_each_holder_phrase() -> None:
    assert each_holder_phrase(["James Whitmore"]) == "for James"
    assert (
        each_holder_phrase(["James Whitmore", "Caroline Whitmore"])
        == "for James and for Caroline, each"
    )


def test_account_phrase_names_joint_type_and_platform() -> None:
    assert account_phrase(JOINT_GIA) == "the joint General Investment Account, Holloway"
    assert account_phrase(JAMES_SIPP) == "James's SIPP, Brightwell"


def test_account_phrase_says_when_the_platform_is_missing() -> None:
    assert (
        account_phrase(_acct("x", ["Ann Lee"], "Cash Account", None))
        == "Ann's Cash Account, platform not stated"
    )


def test_cgt_marker_names_the_disposed_account_and_keeps_its_key() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "g1")], [JOINT_GIA, JAMES_SIPP])

    assert marker.key == "cgt"
    assert marker.text == (
        "capital gains tax on the disposal of the joint General Investment Account, Holloway"
    )


def test_cgt_marker_lists_every_taxable_disposal_in_one_marker() -> None:
    other = _acct("g2", ["Ann Lee"], "General Investment Account", "Brightwell")

    markers = cgt_marker([Disposal("taxable", "g1"), Disposal("taxable", "g2")], [JOINT_GIA, other])

    assert len(markers) == 1
    assert "the joint General Investment Account, Holloway" in markers[0].text
    assert "Ann's General Investment Account, Brightwell" in markers[0].text


def test_cgt_marker_falls_back_when_the_account_is_unknown() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "")], [JOINT_GIA])

    assert marker.text == "capital gains tax on the disposal"


def test_cgt_marker_possible_disposal_keeps_its_caveat_and_names_the_account() -> None:
    (marker,) = cgt_marker([Disposal("unknown", "g1")], [JOINT_GIA])

    assert marker.text.startswith("capital gains tax on the possible disposal of the joint")
    assert "pending confirmation of the account's tax treatment" in marker.text


def test_advice_charge_marker_names_the_platforms_it_covers() -> None:
    markers = {m.key: m for m in required_markers({"Holloway", "Brightwell"})}

    assert markers["advice_charge"].text == (
        "ongoing advice charge rate for the accounts on Brightwell and Holloway"
    )
    assert markers["platform_charge_holloway"].text == "ongoing platform charge rate, Holloway"


def test_advice_charge_marker_with_no_platform_at_all_says_so() -> None:
    markers = {m.key: m for m in required_markers(set(), ["SIPP"])}

    assert markers["advice_charge"].text == (
        "ongoing advice charge rate for any account whose platform is not stated"
    )


def test_advice_charge_marker_also_covers_an_account_with_no_platform() -> None:
    markers = {m.key: m for m in required_markers({"Holloway"}, ["SIPP"])}

    assert markers["advice_charge"].text == (
        "ongoing advice charge rate for the accounts on Holloway and "
        "any account whose platform is not stated"
    )


def test_advice_charge_marker_with_nothing_to_name_keeps_the_plain_wording() -> None:
    markers = {m.key: m for m in required_markers(set())}

    assert markers["advice_charge"].text == "ongoing advice charge rate"


def test_cgt_marker_names_a_possible_disposal_that_shares_it() -> None:
    other = _acct("g2", ["Ann Lee"], "General Investment Account", "Brightwell")

    (marker,) = cgt_marker(
        [Disposal("taxable", "g1"), Disposal("unknown", "g2")], [JOINT_GIA, other]
    )

    assert "the joint General Investment Account, Holloway" in marker.text
    assert "possible disposal of Ann's General Investment Account, Brightwell" in marker.text
    assert "pending confirmation of its tax treatment" in marker.text


def test_several_single_new_accounts_are_not_read_as_one_joint_account() -> None:
    result = build_new_accounts(
        [
            NewAccountMention(
                quote="a new account for Ann", joint=False, owner_references=("Ann",)
            ),
            NewAccountMention(
                quote="a new account for Ben", joint=False, owner_references=("Ben",)
            ),
        ],
        "the ISAs and a new account",
        ["Ann Lee", "Ben Lee"],
    )

    (marker,) = result.markers
    assert marker.text == (
        "platform charge and advice charge rates for the new accounts, held by Ann and "
        "held by Ben (platform not stated)"
    )


def test_pension_marker_names_each_holder() -> None:
    (marker,) = pension_contribution_markers([JAMES_SIPP, CAROLINE_SIPP])

    assert marker.key == "sipp_contribution_amounts"
    assert marker.text == "SIPP contribution amounts for James and for Caroline, each"


def test_pension_marker_with_one_holder() -> None:
    (marker,) = pension_contribution_markers([JAMES_SIPP])

    assert marker.text == "SIPP contribution amounts for James"


def test_allowance_marker_names_the_holders_and_accounts() -> None:
    david = _acct("i1", ["David Clarke"], "Stocks & Shares ISA")
    susan = _acct("i2", ["Susan Clarke"], "Stocks & Shares ISA")

    marker = limit_marker("isa", ["i1", "i2"], [david, susan, JOINT_GIA])

    assert marker.key == "isa_amounts"
    assert "David's Stocks & Shares ISA, Holloway" in marker.text
    assert "Susan's Stocks & Shares ISA, Holloway" in marker.text
    assert "remaining allowances" in marker.text
    assert "where any excess goes" in marker.text


def test_allowance_marker_without_accounts_keeps_its_old_wording() -> None:
    assert limit_marker("isa", ["i1"]).text == (
        "ISA top-up amounts within the remaining allowances, and where any excess goes"
    )


def test_new_account_marker_names_both_charges_and_says_the_platform_is_missing() -> None:
    result = build_new_accounts(
        [NewAccountMention(quote="a new joint account", joint=True)],
        "the ISAs and a new joint account",
        ["James Whitmore", "Caroline Whitmore"],
    )

    (marker,) = result.markers
    assert marker.key == "new_account_charges"
    assert marker.text == (
        "platform charge and advice charge rates for the new joint account held by "
        "James and Caroline (platform not stated)"
    )


def test_no_marker_text_carries_a_figure() -> None:
    texts = [
        m.text
        for m in [
            *required_markers({"Holloway"}, ["SIPP"]),
            *cgt_marker([Disposal("taxable", "g1")], [JOINT_GIA]),
            *pension_contribution_markers([JAMES_SIPP, CAROLINE_SIPP]),
            limit_marker("isa", ["g1"], [JOINT_GIA]),
        ]
    ]

    assert not any(re.search(r"\d|£|%", t) for t in texts)
