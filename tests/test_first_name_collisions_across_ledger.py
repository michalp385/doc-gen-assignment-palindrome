"""Two holders who share a first name must not be merged or blurred anywhere a phrase names one.

The first fix only looked inside one phrase: a CGT marker naming a single account said "Sam's
General Investment Account" although the ledger has a Sam Jones and a Sam Brown, and the scope
description grouped their two ISAs into "Sam's two Stocks & Shares ISAs", giving one person both."""

from __future__ import annotations

from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.reconcile.marker_text import accounts_phrase
from agent_pipeline.reconcile.markers import cgt_marker
from agent_pipeline.reconcile.sections import Disposal
from agent_pipeline.write.plan import _describe_scope


def _acct(id_: str, type_: str, owner: str) -> Account:
    return Account(id=id_, type=type_, owners=[owner], platform="Holloway", in_scope=True)


JONES_GIA = _acct("g1", "General Investment Account", "Sam Jones")
BROWN_GIA = _acct("g2", "General Investment Account", "Sam Brown")


def test_a_phrase_uses_a_full_name_for_a_first_name_the_ledger_shares() -> None:
    phrase = accounts_phrase([JONES_GIA], holders=["Sam Jones", "Sam Brown"])

    assert phrase == "Sam Jones's General Investment Account, Holloway"


def test_the_cgt_marker_uses_the_whole_ledger_to_tell_holders_apart() -> None:
    (marker,) = cgt_marker([Disposal("taxable", "g1")], [JONES_GIA, BROWN_GIA])

    assert "Sam Jones's General Investment Account, Holloway" in marker.text


def test_a_unique_first_name_is_still_a_first_name() -> None:
    phrase = accounts_phrase([JONES_GIA], holders=["Sam Jones", "Mary Brown"])

    assert phrase == "Sam's General Investment Account, Holloway"


def test_the_scope_description_keeps_two_holders_with_one_first_name_apart() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _acct("i1", "Stocks & Shares ISA", "Sam Jones"),
            _acct("i2", "Stocks & Shares ISA", "Sam Brown"),
        ],
    )

    text = _describe_scope(ledger)

    assert "Sam Jones's Stocks & Shares ISA" in text
    assert "Sam Brown's Stocks & Shares ISA" in text
    assert "two" not in text
