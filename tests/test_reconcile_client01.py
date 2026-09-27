"""Reconciliation for client 01's rules, tests first (T8): R1-R3, R5, R8, P2-P6 basics.

Every trust rule and policy is one function here, cited by name in its own docstring and
tested by name, so a prompt never has to restate a rule (CLAUDE.md). The remaining rules
(R4, R6, R7, R9, R10, P5 in full, P7-P12) arrive tests-first in M2 as clients 02-04 and the
hand-written cases need them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from agent_pipeline.ledger import Account, ExcludedItem, Value
from agent_pipeline.reconcile.amounts import reconcile_amounts
from agent_pipeline.reconcile.limits import check_limits, tax_year_for
from agent_pipeline.reconcile.markers import required_markers
from agent_pipeline.reconcile.money import compute_available
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.reconcile.predicates import evaluate
from agent_pipeline.reconcile.review import ReviewItemInput, build_review_items, marker_review_items
from agent_pipeline.reconcile.scope import resolve_scope
from agent_pipeline.reconcile.sections import Disposal, SectionContext
from agent_pipeline.reconcile.values import select_values
from agent_pipeline.reconcile.wrappers import classify_wrapper
from agent_pipeline.sources.adapters.json_accounts import (
    AccountData,
    AccountRecord,
    Holder,
    read_accounts,
)

CLIENT_01 = read_accounts(Path("data/client_01_clean/client_data_db.json"))


def test_r1_single_owner() -> None:
    result = resolve_ownership(CLIENT_01)
    by_id = {a.id: a for a in result.accounts}
    assert set(by_id) == {"H-ISA-01", "H-CASH-01"}
    assert by_id["H-ISA-01"].owners == ["Margaret Hughes"]
    assert by_id["H-ISA-01"].type == "Stocks & Shares ISA"
    assert by_id["H-CASH-01"].owners == ["Margaret Hughes"]
    assert result.set_aside == []  # client 01's records are all complete


def test_r1_owner_falls_back_to_the_holder_whose_section_contains_the_account() -> None:
    # SCOPING.md section 3: owners come from the `owner` field, or (for a record with no
    # `owner` at all, distinct from "Joint") the holder whose JSON section contains it.
    data = AccountData(
        holders={
            "client": Holder(
                name="Mildred Sowerby",
                accounts=[
                    AccountRecord(
                        account_id="S-ISA-01",
                        type="Stocks & Shares ISA",
                        owner=None,
                        status="open",
                    )
                ],
            )
        }
    )
    result = resolve_ownership(data)
    assert result.set_aside == []
    assert result.accounts[0].owners == ["Mildred Sowerby"]


def test_r1_account_missing_type_is_set_aside_not_guessed() -> None:
    # DESIGN.md section 8.4/134: an account missing an identifying field has no safe basis
    # to include in the table, so it's set aside as a review item instead of defaulting.
    data = AccountData(
        holders={
            "client": Holder(
                name="Mildred Sowerby",
                accounts=[
                    AccountRecord(
                        account_id="S-GIA-01", type=None, owner="Mildred Sowerby", status="open"
                    )
                ],
            )
        }
    )
    result = resolve_ownership(data)
    assert result.accounts == []
    assert len(result.set_aside) == 1
    assert result.set_aside[0].kind == "account_missing_field"
    assert "type" in result.set_aside[0].detail
    assert result.set_aside[0].refs == ["S-GIA-01"]


def test_r1_unrecognised_status_is_set_aside_not_a_crash() -> None:
    # verifier report (T8 checkpoint), finding #2: an unseen client's export could use a
    # status word this pipeline has never met ("suspended"); it must degrade to a review
    # item, never crash and never silently become "open".
    data = AccountData(
        holders={
            "client": Holder(
                name="Mildred Sowerby",
                accounts=[
                    AccountRecord(
                        account_id="S-ISA-01",
                        type="Stocks & Shares ISA",
                        owner="Mildred Sowerby",
                        status="suspended",
                    )
                ],
            )
        }
    )
    result = resolve_ownership(data)  # must not raise
    assert result.accounts == []
    assert len(result.set_aside) == 1
    assert "status" in result.set_aside[0].detail


def test_r2_out_of_scope_account_not_in_table() -> None:
    # The report instruction's "Accounts covered" names only the ISA; the cash account
    # (the source of funds) is a candidate for no scope phrase, so R2 keeps it off the
    # table even though it exists and has a value.
    accounts = resolve_ownership(CLIENT_01).accounts
    result = resolve_scope("Holloway Stocks & Shares ISA", accounts)
    assert result.resolved_ids == ["H-ISA-01"]
    assert "H-CASH-01" not in result.resolved_ids


def test_r8_phrase_resolves_by_type_and_platform() -> None:
    accounts = resolve_ownership(CLIENT_01).accounts
    result = resolve_scope("Holloway Stocks & Shares ISA", accounts)
    assert result.resolved_ids == ["H-ISA-01"]
    assert result.unresolved is False


def test_r8_phrase_with_no_matching_account_is_unresolved() -> None:
    accounts = resolve_ownership(CLIENT_01).accounts
    result = resolve_scope("Holloway Personal Pension", accounts)
    assert result.resolved_ids == []
    assert result.unresolved is True


def test_r8_phrase_matching_more_than_one_account_is_unresolved() -> None:
    # verifier report (T8 checkpoint), finding #4: R8's "matches more than it names" branch
    # -- client 01's own two accounts never collide, so this is built directly.
    accounts = [
        Account(
            id="A-1",
            owners=["Test Person"],
            type="Cash Account",
            platform="Holloway",
            status="open",
        ),
        Account(
            id="A-2",
            owners=["Test Person"],
            type="Cash Account",
            platform="Holloway",
            status="open",
        ),
    ]
    result = resolve_scope("Holloway Cash Account", accounts)
    assert result.resolved_ids == []
    assert result.unresolved is True


def test_r3_snapshot_value_when_no_later_figure() -> None:
    # No meeting-viewed figure exists for the ISA, so the db's own dated value wins.
    value = select_values(
        db_value=Decimal("52000"),
        db_date=date(2026, 4, 30),
        currency="GBP",
        viewed_observations=[],
    )
    assert value is not None
    assert value.amount == Decimal("52000")
    assert value.precision == "exact"
    assert value.qualifier == "exact"
    assert value.date == date(2026, 4, 30)
    assert value.selected_by == "R3"


def test_r3_a_later_viewed_meeting_figure_beats_the_snapshot() -> None:
    # verifier report (T8 checkpoint), finding #3: R3's actual point is the comparison
    # between two dated candidates -- client 01 never has more than one, so this is built
    # directly. A reversed comparison (oldest wins) would pass every other select_values test.
    live_observation = Value(
        amount=Decimal("53500"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 5, 12),
        source_id="meeting_notes.docx",
        quote="pulled it up live: £53,500",
        selected_by="",
    )
    value = select_values(
        db_value=Decimal("52000"),
        db_date=date(2026, 4, 30),
        currency="GBP",
        viewed_observations=[live_observation],
    )
    assert value is not None
    assert value.amount == Decimal("53500")
    assert value.date == date(2026, 5, 12)


def test_r3_an_older_viewed_observation_loses_to_the_newer_snapshot() -> None:
    # The mirror case: the db's own value is dated later than the (superseded) meeting
    # figure, so the snapshot wins -- proves the comparison isn't "meeting always wins".
    stale_observation = Value(
        amount=Decimal("49000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 3, 1),
        source_id="meeting_notes.docx",
        quote="pulled it up live: £49,000",
        selected_by="",
    )
    value = select_values(
        db_value=Decimal("52000"),
        db_date=date(2026, 4, 30),
        currency="GBP",
        viewed_observations=[stale_observation],
    )
    assert value is not None
    assert value.amount == Decimal("52000")
    assert value.date == date(2026, 4, 30)


def test_r5_same_amount_uses_exact() -> None:
    instruction = Value(
        amount=Decimal("20000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=None,
        source_id="report_request.docx",
        quote="Investment amount | GBP 20,000",
        selected_by="",
    )
    meeting = Value(
        amount=Decimal("20000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 5, 12),
        source_id="meeting_notes.docx",
        quote="move £20,000 from the cash account",
        selected_by="",
    )
    result = reconcile_amounts(instruction, meeting)
    assert result.agrees is True
    assert result.amount == Decimal("20000")


def test_r5_different_amounts_is_a_conflict_not_a_guess() -> None:
    instruction = Value(
        amount=Decimal("20000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=None,
        source_id="report_request.docx",
        quote="",
        selected_by="",
    )
    meeting = Value(
        amount=Decimal("25000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 5, 12),
        source_id="meeting_notes.docx",
        quote="",
        selected_by="",
    )
    result = reconcile_amounts(instruction, meeting)
    assert result.agrees is False
    assert result.amount is None


def test_p5_no_money_items_for_an_internal_transfer() -> None:
    # Moving cash into the client's own ISA is not received/committed/proceeds/external
    # money under P5; there is nothing to compute.
    assert compute_available([]) is None


def test_wrapper_classification() -> None:
    assert classify_wrapper("Stocks & Shares ISA").wrapper_class == "tax_exempt"
    assert classify_wrapper("Cash Account").wrapper_class == "cash"
    assert classify_wrapper("Some Product Nobody Has Seen").wrapper_class == "unknown"


def test_tax_year_for_a_date_after_the_april_boundary() -> None:
    assert tax_year_for(date(2026, 5, 12)) == "2026/27"


def test_tax_year_for_a_date_before_the_april_boundary() -> None:
    assert tax_year_for(date(2026, 3, 1)) == "2025/26"


def test_tax_year_for_the_day_before_the_boundary_is_still_the_old_year() -> None:
    # verifier report (T8 checkpoint), finding #5: neither existing test is close enough to
    # the 6 April boundary to catch an off-by-one in it.
    assert tax_year_for(date(2026, 4, 5)) == "2025/26"


def test_tax_year_for_the_boundary_date_itself_is_the_new_year() -> None:
    assert tax_year_for(date(2026, 4, 6)) == "2026/27"


def test_p4_full_allowance_unknown_prior_use_note() -> None:
    # £20,000 into an ISA is exactly the 2026/27 allowance; the sources never say whether
    # Margaret has already subscribed this tax year, so this is a review-sheet note, not a
    # report marker (keeps flagging calibrated, Q6).
    result = check_limits(
        amount=Decimal("20000"),
        allowance_family="isa",
        prior_use="unknown",
        meeting_date=date(2026, 5, 12),
    )
    assert result.marker is False
    assert result.note is True


def test_p4_marker_when_the_amount_exceeds_the_allowance() -> None:
    result = check_limits(
        amount=Decimal("25000"),
        allowance_family="isa",
        prior_use="unknown",
        meeting_date=date(2026, 5, 12),
    )
    assert result.marker is True


def test_p4_marker_when_sources_confirm_prior_use_even_under_the_allowance() -> None:
    # verifier report (T8 checkpoint), finding #6: P4's trigger is "sources show prior use"
    # OR "exceeds the allowance" -- confirmed prior use must marker on its own, regardless
    # of how small the new amount is, since how much room remains is then unknown.
    result = check_limits(
        amount=Decimal("5000"),
        allowance_family="isa",
        prior_use="confirmed",
        meeting_date=date(2026, 5, 12),
    )
    assert result.marker is True
    assert result.note is False


def test_p4_no_note_when_sources_confirm_no_prior_use() -> None:
    # The full-allowance note exists only for genuine ambiguity (Q6 calibration); if the
    # sources affirmatively rule out prior use, a full-allowance subscription is unambiguous.
    result = check_limits(
        amount=Decimal("20000"),
        allowance_family="isa",
        prior_use="denied",
        meeting_date=date(2026, 5, 12),
    )
    assert result.marker is False
    assert result.note is False


def test_p2_charge_markers() -> None:
    markers = required_markers(in_scope_platforms={"Holloway"})
    keys = {m.key for m in markers}
    assert keys == {"platform_charge_holloway", "advice_charge"}
    for m in markers:
        assert m.id == ""  # not yet numbered; number_markers (T6) does that at assembly


def test_g5_no_disposal_no_section() -> None:
    assert evaluate("taxable_disposal", SectionContext(disposals=[])) is False


def test_g5_taxable_disposal_triggers_the_section() -> None:
    ctx = SectionContext(disposals=[Disposal(wrapper_class="taxable")])
    assert evaluate("taxable_disposal", ctx) is True


def test_g5_tax_exempt_switch_never_triggers_the_section() -> None:
    ctx = SectionContext(disposals=[Disposal(wrapper_class="tax_exempt")])
    assert evaluate("taxable_disposal", ctx) is False


def test_section_included_reads_the_ledger_field_a_named_predicate_resolves_to() -> None:
    from agent_pipeline.config import Section
    from agent_pipeline.ledger import Ledger
    from agent_pipeline.reconcile.predicates import section_included

    always = Section(id="s", title="S", use_if="always", template="<<x>>")
    assert section_included(always, Ledger(client="c")) is True

    taxable = Section(
        id="t",
        title="T",
        use_if="Include on disposal.",
        predicate="taxable_disposal",
        template="<<x>>",
    )
    assert section_included(taxable, Ledger(client="c", tax_section=True)) is True
    assert section_included(taxable, Ledger(client="c", tax_section=False)) is False

    unknown = Section(
        id="u", title="U", use_if="always", predicate="not_a_real_predicate", template="<<x>>"
    )
    with pytest.raises(KeyError):
        section_included(unknown, Ledger(client="c"))


def test_p6_aspiration_background_only() -> None:
    # Margaret's gifting mention is an aspiration (P6): allowed at most once, in
    # Background, as not covered by this advice, never in Recommendations.

    item = ExcludedItem.model_validate(
        {
            "id": "e1",
            "class": "aspiration",
            "description": "gifting to her grandchildren",
            "allowed_in": ["background_objectives"],
        }
    )
    assert item.item_class == "aspiration"
    assert item.allowed_in == ["background_objectives"]
    assert "recommendations" not in item.allowed_in


def test_build_review_items_assigns_stable_ids() -> None:
    items = build_review_items(
        [
            ReviewItemInput(kind="p4_note", blocking=False, detail="ISA allowance", refs=[]),
            ReviewItemInput(kind="open_action", blocking=False, detail="confirm charges", refs=[]),
        ]
    )
    assert [item.id for item in items] == ["rv1", "rv2"]
    assert items[0].kind == "p4_note"


def test_marker_review_items_one_row_per_marker() -> None:
    # G15 (SCOPING.md): every report marker needs a matching review-sheet row (P1). Real
    # code, not a test-only stub, must produce it -- this was the M0b-checkpoint known gap.
    markers = required_markers(in_scope_platforms={"Holloway"})
    items = marker_review_items(markers)
    assert [i.refs for i in items] == [[m.key] for m in markers]
    for item in items:
        assert item.kind == "marker_reference"
        assert item.blocking is False

    numbered = build_review_items(items)
    all_refs = {ref for item in numbered for ref in item.refs}
    assert all_refs == {m.key for m in markers}
