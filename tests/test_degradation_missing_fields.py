"""Section 8.4 degradation for missing optional fields (tests first; hand-written case 18).

A missing optional account field or an undated meeting record never stops a run and is never
hidden: the run continues on the conservative defaults and the review sheet says what was
missing. A missing platform makes the charges marker say so (DESIGN section 3, json_accounts), and
an in-scope account with no platform gets its own degradation item. An undated meeting never
outranks a dated figure (R3), and the sheet says the meeting is undated.
"""

from __future__ import annotations

from datetime import date

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.degradation import (
    missing_platform_review_items,
    undated_meeting_review_item,
)
from agent_pipeline.reconcile.markers import required_markers


def _isa(platform: str | None) -> Account:
    return Account(
        id="S-ISA-01",
        type="Stocks & Shares ISA",
        owners=["M S"],
        platform=platform,
        in_scope=True,
    )


def test_an_in_scope_account_without_a_platform_gets_a_charges_marker_that_says_so() -> None:
    markers = required_markers(set(), no_platform_types=["Stocks & Shares ISA"])
    assert [m.key for m in markers] == ["platform_charge_unknown_platform", "advice_charge"]
    assert "not stated" in markers[0].text and "ISA" not in markers[0].text
    assert markers[0].section == "fees_charges"


def test_platforms_stated_and_missing_both_get_a_marker_and_one_unknown_marker_per_run() -> None:
    markers = required_markers({"Holloway"}, no_platform_types=["Cash ISA", "Stocks & Shares ISA"])
    keys = [m.key for m in markers]
    assert keys == ["platform_charge_holloway", "platform_charge_unknown_platform", "advice_charge"]
    assert "not stated" in markers[1].text


def test_no_missing_platform_changes_nothing() -> None:
    assert [m.key for m in required_markers({"Holloway"}, no_platform_types=[])] == [
        "platform_charge_holloway",
        "advice_charge",
    ]
    assert [m.key for m in required_markers({"Holloway"})] == [
        "platform_charge_holloway",
        "advice_charge",
    ]


def test_a_degradation_item_per_in_scope_account_with_no_platform() -> None:
    items = missing_platform_review_items([_isa(None), _isa("Holloway")])
    [item] = items
    assert item.kind == "degradation" and not item.blocking
    assert "platform" in item.detail and "not stated" in item.detail
    assert "Stocks & Shares ISA" in item.detail


def test_out_of_scope_accounts_without_a_platform_are_not_reported() -> None:
    out = _isa(None).model_copy(update={"in_scope": False})
    assert missing_platform_review_items([out]) == []


def test_an_undated_meeting_is_a_degradation_item() -> None:
    item = undated_meeting_review_item(None)
    assert item is not None and item.kind == "degradation" and not item.blocking
    for word in ("date", "meeting", "undated"):
        assert word in item.detail


def test_a_dated_meeting_needs_no_item() -> None:
    assert undated_meeting_review_item(date(2026, 5, 1)) is None
