"""Reconciliation for client 02's rules, tests first (T19): R9 (joint owners, copies
agreeing/disagreeing), R3 (a later viewed value supersedes the snapshot), P5 (proceeds
counted only with amount and destination known), P4 (a confirmed prior-use signal triggers
a marker, not just the unknown-prior-use note), P7/G5 (the CGT marker).

Client 01's rules (R1-R3, R5, R8, P2-P6 basics) stay in test_reconcile_client01.py; this
file only covers what client 02 newly exercises.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.limits import limit_marker, resolve_prior_use
from agent_pipeline.reconcile.markers import cgt_marker
from agent_pipeline.reconcile.money import classify_money
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.reconcile.scope import resolve_scope
from agent_pipeline.reconcile.sections import Disposal
from agent_pipeline.reconcile.values import select_values, superseded_values
from agent_pipeline.sources.adapters.json_accounts import (
    AccountData,
    AccountRecord,
    Holder,
    read_accounts,
)

CLIENT_02 = read_accounts(Path("data/client_02_medium/client_data_db.json"))


def test_r9_joint_account_owners_resolved_from_both_holders() -> None:
    result = resolve_ownership(CLIENT_02)
    by_id = {a.id: a for a in result.accounts}
    assert set(by_id) == {"H-ISA-D", "H-GIA-J", "H-ISA-S"}
    assert by_id["H-GIA-J"].owners == ["David Clarke", "Susan Clarke"]


def test_r9_single_owner_accounts_unaffected() -> None:
    result = resolve_ownership(CLIENT_02)
    by_id = {a.id: a for a in result.accounts}
    assert by_id["H-ISA-D"].owners == ["David Clarke"]
    assert by_id["H-ISA-S"].owners == ["Susan Clarke"]


def test_r9_joint_account_appears_once_not_twice() -> None:
    result = resolve_ownership(CLIENT_02)
    ids = [a.id for a in result.accounts]
    assert ids.count("H-GIA-J") == 1


def test_r9_agreeing_copies_raise_no_conflict() -> None:
    # Client 02's own two H-GIA-J copies carry the same value and date.
    result = resolve_ownership(CLIENT_02)
    assert result.conflicts == []


def test_r9_disagreeing_copies_are_flagged_not_silently_picked() -> None:
    data = AccountData(
        holders={
            "client": Holder(
                name="Alan Reed",
                accounts=[
                    AccountRecord(
                        account_id="H-GIA-J",
                        type="General Investment Account",
                        owner="Joint",
                        status="open",
                        value=Decimal("40000"),
                        valuation_date=date(2026, 3, 15),
                    )
                ],
            ),
            "partner": Holder(
                name="Jane Reed",
                accounts=[
                    AccountRecord(
                        account_id="H-GIA-J",
                        type="General Investment Account",
                        owner="Joint",
                        status="open",
                        value=Decimal("41500"),
                        valuation_date=date(2026, 3, 15),
                    )
                ],
            ),
        }
    )
    result = resolve_ownership(data)
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "joint_value_conflict"
    assert result.conflicts[0].refs == ["H-GIA-J"]
    # Ownership itself still resolves (first-write-wins keeps the account in the table);
    # only the value disagreement is flagged, matching R9's own wording.
    by_id = {a.id: a for a in result.accounts}
    assert by_id["H-GIA-J"].owners == ["Alan Reed", "Jane Reed"]


def test_r3_live_viewed_value_supersedes_the_snapshot() -> None:
    live = Value(
        amount=Decimal("45000"),
        currency="GBP",
        precision="approximate",
        qualifier="a_little_over",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="a little over £45,000",
        selected_by="",
    )
    selected = select_values(
        db_value=Decimal("40000"),
        db_date=date(2026, 3, 15),
        currency="GBP",
        viewed_observations=[live],
    )
    assert selected is not None
    assert selected.amount == Decimal("45000")
    assert selected.qualifier == "a_little_over"

    superseded = superseded_values(
        db_value=Decimal("40000"),
        db_date=date(2026, 3, 15),
        currency="GBP",
        viewed_observations=[live],
        selected=selected,
    )
    assert len(superseded) == 1
    assert superseded[0].amount == Decimal("40000")
    assert superseded[0].date == date(2026, 3, 15)


def test_r3_no_superseded_values_when_only_one_candidate() -> None:
    selected = select_values(
        db_value=Decimal("61000"), db_date=date(2026, 4, 30), currency="GBP", viewed_observations=[]
    )
    assert selected is not None
    superseded = superseded_values(
        db_value=Decimal("61000"),
        db_date=date(2026, 4, 30),
        currency="GBP",
        viewed_observations=[],
        selected=selected,
    )
    assert superseded == []


def test_p5_full_disposal_with_known_destination_counts_as_proceeds() -> None:
    gia_value = Value(
        amount=Decimal("45000"),
        currency="GBP",
        precision="approximate",
        qualifier="a_little_over",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="a little over £45,000",
        selected_by="R3",
    )
    result = classify_money(disposal_value=gia_value, extent="full", destination_known=True)
    assert result.counted is True
    assert result.amount == gia_value


def test_p5_unclear_destination_is_a_marker_not_counted() -> None:
    gia_value = Value(
        amount=Decimal("45000"),
        currency="GBP",
        precision="approximate",
        qualifier="a_little_over",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="a little over £45,000",
        selected_by="R3",
    )
    result = classify_money(disposal_value=gia_value, extent="full", destination_known=False)
    assert result.counted is False


def test_p5_partial_disposal_is_a_marker_not_counted() -> None:
    gia_value = Value(
        amount=Decimal("45000"),
        currency="GBP",
        precision="approximate",
        qualifier="a_little_over",
        date=date(2026, 5, 14),
        source_id="meeting_notes.docx",
        quote="a little over £45,000",
        selected_by="R3",
    )
    result = classify_money(disposal_value=gia_value, extent="portion", destination_known=True)
    assert result.counted is False


def test_p4_confirmed_signal_resolves_prior_use() -> None:
    from agent_pipeline.extract.schemas import LimitSignal as ExtractedLimitSignal
    from agent_pipeline.extract.schemas import Quote

    signal = ExtractedLimitSignal(
        text=Quote(
            paragraph_id="p1",
            text="Both ISAs are already part-funded for the year",
        )
    )
    assert resolve_prior_use([signal], "isa") == "confirmed"
    assert resolve_prior_use([signal], "pension") == "unknown"
    assert resolve_prior_use([], "isa") == "unknown"


def test_p4_a_todays_top_up_mention_is_not_confirmed_prior_use() -> None:
    # Regression: client 01's own cached meeting extraction has a real `limit_signals`
    # entry for this exact sentence -- it names the ISA allowance but describes the top-up
    # being agreed today, not an earlier use. A bare family-name match would wrongly
    # confirm prior use and marker client 01 (the T17-checkpoint regression this module's
    # docstring records, mirrored here for the opposite direction).
    from agent_pipeline.extract.schemas import LimitSignal as ExtractedLimitSignal
    from agent_pipeline.extract.schemas import Quote

    signal = ExtractedLimitSignal(
        text=Quote(paragraph_id="p4", text="would like to use this year's ISA allowance")
    )
    assert resolve_prior_use([signal], "isa") == "unknown"


def test_p4_limit_marker_key_and_no_figure_in_text() -> None:
    marker = limit_marker("isa", account_ids=["H-ISA-D", "H-ISA-S"])
    assert marker is not None
    assert marker.key == "isa_amounts"
    assert not any(ch.isdigit() for ch in marker.text)


def test_p7_cgt_marker_for_a_taxable_disposal() -> None:
    markers = cgt_marker([Disposal(wrapper_class="taxable")])
    assert [m.key for m in markers] == ["cgt"]
    assert not any(ch.isdigit() for ch in markers[0].text)


def test_p7_no_cgt_marker_without_a_taxable_disposal() -> None:
    assert cgt_marker([Disposal(wrapper_class="tax_exempt")]) == []
    assert cgt_marker([]) == []


def test_r8_a_model_proposed_mapping_can_resolve_several_accounts_at_once() -> None:
    # Client 02's own scope phrase names three accounts in free language ("Holloway ISAs
    # (David and Susan) and the joint GIA") -- it doesn't contain any single account's type
    # wording as a substring, so only a model's candidate mapping resolves it; several
    # accounts is the correct, expected outcome, not R8's ambiguity case.
    accounts = resolve_ownership(CLIENT_02).accounts
    result = resolve_scope(
        "Holloway ISAs (David and Susan) and the joint GIA",
        accounts,
        candidate_account_ids=["H-ISA-D", "H-ISA-S", "H-GIA-J"],
    )
    assert result.unresolved is False
    assert set(result.resolved_ids) == {"H-ISA-D", "H-ISA-S", "H-GIA-J"}


def test_r8_a_hallucinated_candidate_id_is_dropped_not_trusted() -> None:
    accounts = resolve_ownership(CLIENT_02).accounts
    result = resolve_scope(
        "Holloway ISAs (David and Susan) and the joint GIA",
        accounts,
        candidate_account_ids=["H-ISA-D", "H-ISA-S", "not-a-real-id"],
    )
    assert result.unresolved is False
    assert set(result.resolved_ids) == {"H-ISA-D", "H-ISA-S"}


def test_r8_only_hallucinated_candidates_is_unresolved_not_guessed() -> None:
    accounts = resolve_ownership(CLIENT_02).accounts
    result = resolve_scope("anything", accounts, candidate_account_ids=["not-a-real-id"])
    assert result.unresolved is True
    assert result.resolved_ids == []


def test_r8_no_candidate_list_falls_back_to_the_substring_match() -> None:
    # Omitting the third argument entirely must behave exactly as it did before T19
    # (client 01's own R8 tests rely on this).
    accounts = resolve_ownership(CLIENT_02).accounts
    result = resolve_scope("Holloway Stocks & Shares ISA", accounts)
    assert result.unresolved is True  # matches both David's and Susan's ISA -- ambiguous
