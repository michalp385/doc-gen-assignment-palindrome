"""Ledger models and rendering (T6, DESIGN.md section 6).

The ledger is the one place every fact, its source and the rule that selected it live
(S5); the report, the table, the markers and the review sheet all read from it, so the
report can't contradict itself the way the baseline's client 03 report did.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.ledger import (
    Account,
    Ledger,
    Marker,
    Value,
    number_markers,
    render_prose,
    render_table,
)


def _value(amount: str, precision: str, qualifier: str) -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision=precision,  # type: ignore[arg-type]
        qualifier=qualifier,  # type: ignore[arg-type]
        date=date(2026, 5, 12),
        source_id="meeting_notes.docx",
        quote="the exact source wording",
        selected_by="R3",
    )


def test_exact_value_renders_the_same_in_prose_and_table() -> None:
    value = _value("52000", "exact", "exact")
    assert render_table(value) == "£52,000"
    assert render_prose(value) == "£52,000"


def test_approximate_value_renders_c_in_the_table() -> None:
    value = _value("45000", "approximate", "a_little_over")
    assert render_table(value) == "c. £45,000"


def test_approximate_value_keeps_the_source_wording_in_prose() -> None:
    assert render_prose(_value("45000", "approximate", "a_little_over")) == "a little over £45,000"
    assert render_prose(_value("38000", "approximate", "around")) == "around £38,000"
    assert render_prose(_value("400000", "approximate", "up_to")) == "up to £400,000"
    assert render_prose(_value("45000", "approximate", "circa")) == "c. £45,000"


def test_marker_ids_are_assigned_by_first_appearance_in_the_report_not_creation_order() -> None:
    ledger = Ledger(
        client="client_01_clean",
        markers=[
            Marker(id="", key="cgt", text="capital gains tax", reason="disposal", section="tax"),
            Marker(
                id="",
                key="platform_charge_holloway",
                text="ongoing platform charge rate, Holloway",
                reason="never estimated",
                section="fees",
            ),
            Marker(
                id="",
                key="advice_charge",
                text="ongoing advice charge rate",
                reason="never estimated",
                section="fees",
            ),
        ],
    )
    # advice_charge is mentioned twice in the assembled report; only its first mention counts.
    report_order = ["advice_charge", "advice_charge", "cgt", "platform_charge_holloway"]

    numbered = number_markers(ledger, report_order)

    by_key = {m.key: m.id for m in numbered.markers}
    assert by_key == {
        "advice_charge": "#1",
        "cgt": "#2",
        "platform_charge_holloway": "#3",
    }


def test_marker_not_mentioned_in_the_report_is_still_numbered_after_the_mentioned_ones() -> None:
    ledger = Ledger(
        client="client_01_clean",
        markers=[
            Marker(id="", key="cgt", text="capital gains tax", reason="disposal", section="tax"),
            Marker(
                id="",
                key="unmentioned",
                text="never made it into the draft",
                reason="dropped",
                section="fees",
            ),
        ],
    )
    numbered = number_markers(ledger, report_order=["cgt"])
    by_key = {m.key: m.id for m in numbered.markers}
    assert by_key == {"cgt": "#1", "unmentioned": "#2"}


def test_ledger_json_round_trip() -> None:
    ledger = Ledger(
        client="client_01_clean",
        meeting_date=date(2026, 5, 12),
        accounts=[
            Account(
                id="H-ISA-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                platform="Holloway",
                status="open",
                in_scope=True,
                value=_value("52000", "exact", "exact"),
            )
        ],
        markers=[
            Marker(
                id="#1",
                key="platform_charge_holloway",
                text="ongoing platform charge rate, Holloway",
                reason="never estimated",
                section="fees",
            )
        ],
    )

    restored = Ledger.model_validate_json(ledger.model_dump_json())

    assert restored == ledger
    assert restored.accounts[0].value is not None
    assert restored.accounts[0].value.amount == ledger.accounts[0].value.amount  # type: ignore[union-attr]
