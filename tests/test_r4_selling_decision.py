"""R4: the report instruction's "selling existing investments" against the meeting (tests first;
hand-written case 07).

DESIGN `reconcile_decisions`: a mismatch between the instruction's decision and the disposals the
meeting records is a conflict for the review sheet, never settled silently, and a selling
mismatch is G5 case b: a possible taxable disposal pending confirmation. So the conflict is
blocking, quotes both sides, and comes with a marker. When the instruction says yes but the
meeting records no sale, a possible disposal is added so the tax section is not omitted.
"""

from __future__ import annotations

from agent_pipeline.reconcile.decisions import check_selling_decision

LABEL = "Selling existing investments?"
SALE = "We agreed to sell £10,000 of the General Investment Account."


def test_no_in_the_instruction_but_a_sale_in_the_meeting_is_a_blocking_conflict() -> None:
    result = check_selling_decision(LABEL, "No", [SALE])
    assert result.marker is not None and result.marker.key == "disposal_pending_confirmation"
    assert result.marker.section == "recommendations"  # always present; the tax section may not be
    item = result.review_item
    assert item is not None and item.kind == "conflict" and item.blocking
    assert "Selling existing investments? | No" in item.detail
    assert "sell £10,000" in item.detail
    assert not result.add_possible_disposal  # the recorded sale already brings in the tax section


def test_yes_in_the_instruction_but_no_sale_in_the_meeting_adds_a_possible_disposal() -> None:
    result = check_selling_decision(LABEL, "Yes", [])
    assert result.marker is not None and result.review_item is not None
    assert (
        result.review_item.blocking
        and "Selling existing investments? | Yes" in result.review_item.detail
    )
    assert result.add_possible_disposal


def test_agreement_raises_nothing() -> None:
    for value, quotes in (("Yes", [SALE]), ("No", []), ("Yes (partial rebalance)", [SALE])):
        result = check_selling_decision(LABEL, value, quotes)
        assert (result.marker, result.review_item, result.add_possible_disposal) == (
            None,
            None,
            False,
        ), value


def test_a_value_that_is_neither_yes_nor_no_is_left_alone() -> None:
    for value in ("TBC", "", "maybe"):
        assert check_selling_decision(LABEL, value, [SALE]).review_item is None, value
        assert check_selling_decision(LABEL, value, []).review_item is None, value


def test_partial_counts_as_selling() -> None:
    assert check_selling_decision(LABEL, "Partial", [SALE]).review_item is None
    assert check_selling_decision(LABEL, "Partial", []).review_item is not None


def test_several_sales_are_all_quoted() -> None:
    result = check_selling_decision(LABEL, "No", [SALE, "We will also sell the bond."])
    assert result.review_item is not None
    assert "sell £10,000" in result.review_item.detail
    assert "sell the bond" in result.review_item.detail
