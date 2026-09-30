"""A disposal that matched no account (`account_id == ""`) is still a disposal the adviser must
price for CGT. The marker names the accounts it can, and says so when another disposal cannot be
named, rather than dropping it: the old generic wording covered every disposal, so a named-only
marker would read as covering less."""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.markers import cgt_marker
from agent_pipeline.reconcile.sections import Disposal

GIA = Account(
    id="g1",
    owners=["Ann Lee", "Ben Lee"],
    type="General Investment Account",
    platform="Holloway",
    in_scope=True,
)


def test_a_taxable_disposal_with_no_account_is_still_covered_beside_a_named_one() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "g1"), Disposal("taxable", "")], [GIA])

    assert "the joint General Investment Account, Holloway" in marker.text
    assert "any other disposal in this advice" in marker.text


def test_a_possible_disposal_with_no_account_is_still_covered_beside_a_named_one() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "g1"), Disposal("unknown", "")], [GIA])

    assert "any other disposal in this advice" in marker.text


def test_a_disposal_naming_an_account_not_in_the_ledger_counts_as_unnamed() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "g1"), Disposal("taxable", "zz")], [GIA])

    assert "any other disposal in this advice" in marker.text


def test_nothing_is_added_when_every_disposal_is_named() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "g1")], [GIA])

    assert "any other disposal" not in marker.text
