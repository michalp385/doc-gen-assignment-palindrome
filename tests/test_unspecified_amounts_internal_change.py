"""A change made within a wrapper is not a funding action (tests first; hand-written case 10).

"switch the funds held within her ISA to a more cautious fund range" moves no money into
anything: it changes what an account holds. The funding-word list in D24 read the noun "fund" in
it as a verb and added an ISA-amount marker. An action that switches, rebalances, reallocates or
works "within" an account is left alone; a genuine "fund the ISA" still gets its marker.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account, Action
from agent_pipeline.reconcile.unspecified_amounts import build_unspecified_amounts

ISA = Account(id="I-1", type="Stocks & Shares ISA", owners=["A B"], platform="P", in_scope=True)


def _markers(description: str) -> list[str]:
    action = Action(
        id="a1",
        description=description,
        kind="action",
        accounts=["Stocks & Shares ISA"],
        quote=description,
    )
    result = build_unspecified_amounts(
        [action],
        {},
        [ISA],
        partial_disposals=[],
        disposal_quotes=[],
        other_unspecified=0,
        taken_keys=set(),
        available=None,
    )
    return [m.key for m in result.markers]


def test_switching_funds_within_a_wrapper_makes_no_amount_marker() -> None:
    assert _markers("switch the funds held within her ISA to a more cautious fund range") == []


def test_rebalancing_and_reallocating_make_none() -> None:
    assert _markers("rebalance the ISA") == []
    assert _markers("reallocate the holdings in the ISA") == []


def test_a_genuine_funding_action_still_gets_its_marker() -> None:
    assert _markers("fund the ISA for the new tax year") == ["isa_amounts"]
