"""P2, P5: an amount the sources leave unspecified is an adviser-review marker (tests first).

Deterministic, from the ledger: no model labels the basis (D1/P1). An agreed funding action
with no amount on an allowance-bearing account, on another in-scope account, or into a new
account is a marker; a portion sold is a marker plus a destination review item. When exactly
one other unspecified amount feeds the new account's balance, that marker's text covers the
balance; otherwise the balance is its own marker.
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.ledger import Account, Action, Value
from agent_pipeline.reconcile.unspecified_amounts import PartialDisposal, build_unspecified_amounts


def _account(
    account_id: str, type_: str, *, owners: list[str] | None = None, is_new: bool = False
) -> Account:
    return Account(
        id=account_id,
        type=type_,
        owners=owners or ["Ann Poe"],
        platform=None if is_new else "Alpha",
        in_scope=True,
        is_new=is_new,
    )


def _action(action_id: str, description: str, refs: list[str], kind: str = "action") -> Action:
    return Action(
        id=action_id,
        description=description,
        kind=kind,  # type: ignore[arg-type]  # the test passes the literal by name
        accounts=refs,
        quote=description,
    )


def _amount(text: str = "£10") -> Value:
    return Value(
        amount=Decimal("650000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=None,
        source_id="m",
        quote=text,
        selected_by="P5",
    )


ISA = _account("I-1", "Stocks & Shares ISA")
GIA = _account("G-1", "General Investment Account")
NEW = _account("new:joint_investment_account", "New joint account", is_new=True)


def _build(actions, *, action_amounts=None, partial=(), disposal_quotes=(), upstream=0, keys=()):
    return build_unspecified_amounts(
        actions,
        action_amounts or {},
        [ISA, GIA, NEW],
        partial_disposals=list(partial),
        disposal_quotes=list(disposal_quotes),
        other_unspecified=upstream,
        taken_keys=set(keys),
        available=_amount(),
    )


def test_allowance_account_funding_without_an_amount_is_an_amount_marker() -> None:
    result = _build([_action("a1", "fund the ISA for the new tax year", ["Stocks & Shares ISA"])])
    assert [m.key for m in result.markers] == ["isa_amounts"]
    assert result.markers[0].section == "recommendations"


def test_using_the_allowance_without_a_funding_verb_is_not_a_marker() -> None:
    result = _build([_action("a1", "use the ISA allowance for the new tax year", ["ISA"])])
    assert result.markers == []


def test_an_action_with_a_stated_amount_is_not_a_marker() -> None:
    action = _action("a1", "fund the ISA", ["Stocks & Shares ISA"])
    assert _build([action], action_amounts={"a1": _amount()}).markers == []


def test_a_non_action_is_never_a_marker() -> None:
    action = _action("a1", "leave the GIA as it is, no top-up", ["GIA"], kind="non_action")
    assert _build([action]).markers == []


def test_adding_to_another_account_is_an_addition_marker_keyed_by_its_type() -> None:
    result = _build([_action("a1", "add to the joint GIA", ["joint GIA"])])
    assert [m.key for m in result.markers] == ["gia_addition_amount"]


def test_the_disposal_sentence_itself_is_not_an_addition() -> None:
    sentence = "we agreed to move part of the GIA into cash and rebalance it"
    action = _action("a1", sentence, ["GIA"])
    assert _build([action], disposal_quotes=[sentence]).markers == []


def test_a_portion_sold_is_a_marker_and_a_destination_review_item() -> None:
    partial = PartialDisposal(account=GIA, reference="the joint GIA", extent="portion")
    result = _build([], partial=[partial])
    assert [m.key for m in result.markers] == ["gia_portion_sold"]
    [item] = result.review_items
    assert item.kind == "ambiguity" and not item.blocking
    assert "portion" in item.detail and "GIA" in item.detail and "£650,000" in item.detail


def test_destination_item_without_an_available_figure_states_no_figure() -> None:
    partial = PartialDisposal(account=GIA, reference="the joint GIA", extent="portion")
    result = build_unspecified_amounts(
        [],
        {},
        [GIA],
        partial_disposals=[partial],
        disposal_quotes=[],
        other_unspecified=0,
        taken_keys=set(),
        available=None,
    )
    [item] = result.review_items
    assert "portion" in item.detail and "£" not in item.detail


def test_new_account_balance_folds_into_a_single_upstream_marker() -> None:
    actions = [
        _action("a1", "fund the ISAs for the new tax year", ["Stocks & Shares ISA"]),
        _action("a2", "open a new jointly-held account for the balance", ["new joint account"]),
    ]
    result = _build(actions)
    assert [m.key for m in result.markers] == ["isa_amounts"]
    assert "balance" in result.markers[0].text and "new account" in result.markers[0].text


def test_new_account_balance_is_its_own_marker_with_several_upstream() -> None:
    actions = [
        _action("a1", "add to the joint GIA", ["joint GIA"]),
        _action(
            "a2", "place the remaining balance into a new jointly-held account", ["new account"]
        ),
    ]
    result = _build(actions, upstream=1)
    assert [m.key for m in result.markers] == ["gia_addition_amount", "new_account_balance"]


def test_a_key_already_taken_is_not_duplicated() -> None:
    result = _build([_action("a1", "fund the ISA", ["Stocks & Shares ISA"])], keys={"isa_amounts"})
    assert result.markers == []


def test_reviewing_investments_is_not_a_funding_action() -> None:
    action = _action("a1", "review the investments held in the ISA", ["Stocks & Shares ISA"])
    assert _build([action]).markers == []


def test_investing_as_a_verb_is_a_funding_action() -> None:
    action = _action("a1", "invest more in the ISA", ["Stocks & Shares ISA"])
    assert [m.key for m in _build([action]).markers] == ["isa_amounts"]


def test_an_action_naming_an_isa_and_a_new_account_keeps_the_isa_marker() -> None:
    action = _action(
        "a1", "fund the ISA and open a new joint account", ["Stocks & Shares ISA", "new account"]
    )
    [marker] = _build([action]).markers
    assert marker.key == "isa_amounts" and "balance" in marker.text


def test_an_unspecified_extent_is_not_described_as_a_portion() -> None:
    partial = PartialDisposal(account=GIA, reference="the joint GIA", extent="unspecified")
    [item] = _build([], partial=[partial]).review_items
    assert "portion" not in item.detail and "not stated" in item.detail


def test_balance_reason_is_truthful_when_nothing_upstream_is_unstated() -> None:
    action = _action("a1", "open a new account for the balance", ["new account"])
    [marker] = _build([action]).markers
    assert marker.key == "new_account_balance"
    assert "depends on" not in marker.reason


def test_a_reference_matching_no_account_makes_no_marker() -> None:
    assert _build([_action("a1", "add to the offshore bond", ["offshore bond"])]).markers == []
