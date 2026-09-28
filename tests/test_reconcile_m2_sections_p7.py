"""P7 and G5 (case b), tests first (T20/T21): which disposals trigger the Tax Implications
section and its CGT marker, and where a bond encashment goes instead.

A disposal from a `taxable` account -> Tax section and a CGT marker. `tax_exempt` switches
(inside an ISA or SIPP) never create a section. A bond encashment never creates a CGT
section either: it gets a "chargeable-event gain to be assessed" marker in Recommendations.
A disposal from an `unknown` wrapper is a possible taxable disposal pending confirmation
(DESIGN.md section 5.1, G5 case b): the Tax section is included with a CGT marker, plus a
review item. CGT amounts are never estimated -- only markers.
"""

from __future__ import annotations

from agent_pipeline.reconcile.markers import bond_marker, cgt_marker
from agent_pipeline.reconcile.sections import (
    Disposal,
    SectionContext,
    taxable_disposal,
    unknown_wrapper_review_items,
)
from agent_pipeline.reconcile.wrappers import classify_wrapper


def _included(*wrapper_classes: str, conflict: bool = False) -> bool:
    ctx = SectionContext(
        disposals=[Disposal(wrapper_class=w) for w in wrapper_classes], disposal_conflict=conflict
    )
    return taxable_disposal(ctx)


def test_a_taxable_disposal_includes_the_tax_section() -> None:
    assert _included("taxable") is True


def test_a_tax_exempt_switch_never_includes_it() -> None:
    assert _included("tax_exempt") is False


def test_a_bond_encashment_alone_never_includes_it() -> None:
    assert _included("bond") is False


def test_a_cash_withdrawal_alone_never_includes_it() -> None:
    assert _included("cash") is False


def test_no_disposal_no_section() -> None:
    assert _included() is False


def test_an_unknown_wrapper_disposal_includes_it_pending_confirmation() -> None:
    assert _included("unknown") is True


def test_a_bond_encashment_beside_a_taxable_disposal_still_includes_it() -> None:
    assert _included("bond", "taxable") is True


def test_a_conflict_about_a_disposal_includes_it() -> None:
    assert _included(conflict=True) is True


def test_an_unrecognised_type_classifies_as_unknown_never_a_guess() -> None:
    assert classify_wrapper("Junior ISA").wrapper_class == "unknown"


# --- CGT marker ----------------------------------------------------------------------------


def test_cgt_marker_for_an_unknown_wrapper_says_the_disposal_is_only_possible() -> None:
    (marker,) = cgt_marker([Disposal(wrapper_class="unknown")])
    assert marker.key == "cgt"
    assert "possible" in marker.text
    assert not any(ch.isdigit() for ch in marker.text)


def test_cgt_marker_for_a_taxable_disposal_is_not_hedged() -> None:
    (marker,) = cgt_marker([Disposal(wrapper_class="taxable")])
    assert "possible" not in marker.text


def test_a_taxable_and_an_unknown_disposal_together_share_one_unhedged_marker() -> None:
    markers = cgt_marker([Disposal(wrapper_class="unknown"), Disposal(wrapper_class="taxable")])
    assert [m.key for m in markers] == ["cgt"]
    assert "possible" not in markers[0].text


def test_a_bond_or_exempt_disposal_gets_no_cgt_marker() -> None:
    assert cgt_marker([Disposal(wrapper_class="bond")]) == []
    assert cgt_marker([Disposal(wrapper_class="tax_exempt")]) == []


# --- bond encashment marker ----------------------------------------------------------------


def test_a_bond_encashment_gets_a_chargeable_gain_marker_in_recommendations() -> None:
    (marker,) = bond_marker([Disposal(wrapper_class="bond")])
    assert marker.key == "bond_chargeable_gain"
    assert marker.section == "recommendations"
    assert "chargeable" in marker.text
    assert not any(ch.isdigit() for ch in marker.text)


def test_two_bond_encashments_share_one_marker() -> None:
    markers = bond_marker([Disposal(wrapper_class="bond"), Disposal(wrapper_class="bond")])
    assert len(markers) == 1


def test_no_bond_encashment_no_bond_marker() -> None:
    assert bond_marker([Disposal(wrapper_class="taxable")]) == []
    assert bond_marker([]) == []


# --- unknown wrapper review items ----------------------------------------------------------


def test_an_unknown_wrapper_disposal_gets_a_review_item_naming_the_account() -> None:
    (item,) = unknown_wrapper_review_items(
        [Disposal(wrapper_class="unknown", account_id="X-JISA-1")]
    )
    assert item.kind == "ambiguity"
    assert item.blocking is False
    assert item.refs == ["X-JISA-1"]
    assert "pending confirmation" in item.detail


def test_an_unresolved_disposal_reference_gets_a_review_item_without_an_account() -> None:
    (item,) = unknown_wrapper_review_items([Disposal(wrapper_class="unknown")])
    assert item.refs == []
    assert "could not be matched" in item.detail


def test_known_wrapper_disposals_get_no_unknown_wrapper_item() -> None:
    disposals = [
        Disposal(wrapper_class="taxable", account_id="A"),
        Disposal(wrapper_class="bond", account_id="B"),
        Disposal(wrapper_class="tax_exempt", account_id="C"),
    ]
    assert unknown_wrapper_review_items(disposals) == []


def test_existing_disposal_construction_still_works_without_an_account_id() -> None:
    assert Disposal(wrapper_class="taxable").account_id == ""
