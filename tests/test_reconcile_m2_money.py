"""P5, tests first (T20/T21): money available now, derived approximate totals, and the money
items built from a meeting extraction.

Available = received - committed, in code (client 04: £850,000 - £200,000 = £650,000). A
commitment with no stated amount makes the available amount a marker: a guessed amount is
never subtracted. External (contingent, not received) money is named as excluded and never
counted. A derived value is approximate if any input is, rendered with "c." and never rounded
(client 03: £120,000 + c. £38,000 = c. £158,000). Proceeds are classify_money's job (T19) and
are not rebuilt here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.extract.schemas import LabelEvidence, Quote
from agent_pipeline.extract.schemas import MoneyItem as ExtractedMoneyItem
from agent_pipeline.ledger import MoneyItem, Value, render_prose, render_table
from agent_pipeline.reconcile.facts import available_fact, money_amount_fact
from agent_pipeline.reconcile.money import (
    available_now,
    build_money_items,
    compute_available,
    sum_values,
)


def _value(text: str, *, day: date | None = None) -> Value:
    parsed = parse_amount(text)
    assert parsed is not None
    return Value(
        amount=parsed.amount,
        currency=parsed.currency,
        precision=parsed.precision,
        qualifier=parsed.qualifier,
        date=day,
        source_id="meeting_notes.docx",
        quote=text,
        selected_by="test",
    )


def _item(item_id: str, money_class: str, text: str | None, *, counted: bool = True) -> MoneyItem:
    return MoneyItem.model_validate(
        {
            "id": item_id,
            "class": money_class,
            "amount": _value(text) if text is not None else None,
            "counted": counted,
        }
    )


# --- sum_values: derived totals ----------------------------------------------------------


def test_sum_of_exact_values_is_exact() -> None:
    total = sum_values([_value("£120,000"), _value("£30,000")], "P5")
    assert total is not None
    assert total.amount == Decimal("150000")
    assert total.precision == "exact"
    assert render_table(total) == "£150,000"


def test_sum_is_approximate_if_any_input_is_and_never_rounded() -> None:
    # client 03: £120,000 (exact) + c. £38,000 (approximate) = c. £158,000
    total = sum_values([_value("£120,000"), _value("around £38,000")], "P5")
    assert total is not None
    assert total.amount == Decimal("158000")
    assert total.precision == "approximate"
    assert render_table(total) == "c. £158,000"
    assert render_prose(total) == "c. £158,000"


def test_sum_keeps_pence_it_is_never_rounded() -> None:
    total = sum_values([_value("around £38,000.50"), _value("£120,000.25")], "P5")
    assert total is not None
    assert total.amount == Decimal("158000.75")


def test_sum_of_nothing_is_none() -> None:
    assert sum_values([], "P5") is None


def test_sum_across_currencies_is_none_never_converted() -> None:
    assert sum_values([_value("£10,000"), _value("€5,000")], "P5") is None


def test_derived_value_names_its_rule_and_has_no_source_quote_or_date() -> None:
    total = sum_values([_value("£1,000"), _value("£2,000")], "P5")
    assert total is not None
    assert total.selected_by == "P5"
    assert total.date is None
    assert total.quote == ""


# --- available_now ------------------------------------------------------------------------


def test_available_is_received_minus_committed_in_code() -> None:
    # client 04: completion payment £850,000 received, £200,000 committed to a bridging loan
    result = available_now(
        [
            _item("m1", "received", "£850,000"),
            _item("m2", "committed", "£200,000"),
        ]
    )
    assert result.marker_reason is None
    assert result.value is not None
    assert result.amount == Decimal("650000")
    assert render_table(result.value) == "£650,000"
    assert result.value.selected_by == "P5"


def test_available_with_nothing_committed_is_the_received_total() -> None:
    result = available_now([_item("m1", "received", "£850,000")])
    assert result.amount == Decimal("850000")


def test_available_sums_several_received_items() -> None:
    result = available_now([_item("m1", "received", "£10,000"), _item("m2", "received", "£5,000")])
    assert result.amount == Decimal("15000")


def test_available_is_approximate_if_any_input_is() -> None:
    result = available_now(
        [_item("m1", "received", "around £850,000"), _item("m2", "committed", "£200,000")]
    )
    assert result.value is not None
    assert result.value.precision == "approximate"
    assert render_table(result.value) == "c. £650,000"


def test_external_money_is_never_counted() -> None:
    # client 04's earnout: up to £400,000, contingent, not received, excluded
    result = available_now(
        [
            _item("m1", "received", "£850,000"),
            _item("m2", "committed", "£200,000"),
            _item("m3", "external", "up to £400,000", counted=False),
        ]
    )
    assert result.amount == Decimal("650000")


def test_proceeds_are_not_part_of_available_now() -> None:
    result = available_now(
        [_item("m1", "received", "£100,000"), _item("m2", "proceeds", "around £45,000")]
    )
    assert result.amount == Decimal("100000")


def test_a_commitment_with_no_stated_amount_makes_available_a_marker() -> None:
    # P5: "a guessed amount is never subtracted"
    result = available_now([_item("m1", "received", "£850,000"), _item("m2", "committed", None)])
    assert result.value is None
    assert result.amount is None
    assert result.marker_reason is not None
    assert "commitment" in result.marker_reason


def test_a_received_item_with_no_stated_amount_makes_available_a_marker() -> None:
    result = available_now([_item("m1", "received", None)])
    assert result.value is None
    assert result.marker_reason is not None
    assert "received" in result.marker_reason


def test_commitments_exceeding_receipts_make_available_a_marker_not_a_negative() -> None:
    result = available_now(
        [_item("m1", "received", "£100,000"), _item("m2", "committed", "£200,000")]
    )
    assert result.value is None
    assert result.marker_reason is not None


def test_mixed_currencies_make_available_a_marker_never_converted() -> None:
    result = available_now(
        [_item("m1", "received", "€100,000"), _item("m2", "committed", "£1,000")]
    )
    assert result.value is None
    assert result.marker_reason is not None


def test_no_received_money_means_nothing_to_compute_and_no_marker() -> None:
    # client 01: moving cash between the client's own accounts is not P5 money at all
    result = available_now([])
    assert result.value is None
    assert result.marker_reason is None


def test_committed_alone_with_nothing_received_is_still_nothing_to_compute() -> None:
    result = available_now([_item("m1", "committed", "£1,000")])
    assert result.value is None
    assert result.marker_reason is None


def test_compute_available_keeps_returning_a_decimal_or_none() -> None:
    assert compute_available([]) is None
    assert compute_available(
        [_item("m1", "received", "£850,000"), _item("m2", "committed", "£200,000")]
    ) == Decimal("650000")
    assert (
        compute_available([_item("m1", "received", "£1"), _item("m2", "committed", None)]) is None
    )


# --- build_money_items: from the extraction -----------------------------------------------


def _extracted(
    money_class: str | None, purpose: str, amount_text: str | None
) -> ExtractedMoneyItem:
    return ExtractedMoneyItem.model_validate(
        {
            "money_class": money_class,
            "purpose": purpose,
            "amount": {"paragraph_id": "p1", "text": amount_text} if amount_text else None,
            "class_evidence": {"paragraph_id": "p1", "text": "evidence"},
        }
    )


def test_build_maps_received_committed_and_external_with_parsed_amounts() -> None:
    build = build_money_items(
        [
            _extracted("received", "completion payment", "£850,000"),
            _extracted("committed", "bridging loan", "£200,000"),
            _extracted("external", "earnout", "up to £400,000"),
        ],
        "meeting_notes.docx",
    )
    by_class = {m.money_class: m for m in build.items}
    assert set(by_class) == {"received", "committed", "external"}
    assert by_class["received"].amount is not None
    assert by_class["received"].amount.amount == Decimal("850000")
    assert by_class["received"].counted is True
    assert by_class["committed"].counted is True
    assert by_class["external"].amount is not None
    assert by_class["external"].amount.qualifier == "up_to"
    assert by_class["external"].counted is False
    assert "excluded" in by_class["external"].reason
    assert build.review_items == []


def test_build_carries_the_source_quote_and_source_id() -> None:
    build = build_money_items(
        [_extracted("received", "completion payment", "£850,000")], "meeting_notes.docx"
    )
    (item,) = build.items
    assert item.quote == "£850,000"
    assert item.source_id == "meeting_notes.docx"


def test_build_a_money_item_with_an_unverified_class_is_never_allocated() -> None:
    # DESIGN 4.2: no verified class -> "not available; review item" (G7)
    build = build_money_items([_extracted(None, "a payment", "£5,000")], "meeting_notes.docx")
    assert build.items == []
    (review,) = build.review_items
    assert review.kind == "unverified"
    assert review.blocking is False


def test_build_skips_proceeds_they_belong_to_the_disposal_path() -> None:
    build = build_money_items(
        [_extracted("proceeds", "sale of the GIA", "around £45,000")], "meeting_notes.docx"
    )
    assert build.items == []
    assert build.review_items == []


def test_build_keeps_an_amountless_item_with_no_value() -> None:
    build = build_money_items(
        [_extracted("committed", "loan repayment", None)], "meeting_notes.docx"
    )
    (item,) = build.items
    assert item.amount is None
    assert item.quote != ""  # falls back to the item's purpose text so it still traces


def test_build_an_unparseable_amount_quote_is_a_valueless_item_not_a_guess() -> None:
    build = build_money_items(
        [_extracted("committed", "loan repayment", "a fair bit")], "meeting_notes.docx"
    )
    (item,) = build.items
    assert item.amount is None


def test_build_ids_are_unique_and_start_where_the_caller_says() -> None:
    build = build_money_items(
        [_extracted("received", "a", "£1,000"), _extracted("committed", "b", "£500")],
        "meeting_notes.docx",
        start_index=3,
    )
    assert [m.id for m in build.items] == ["m3", "m4"]


def test_build_then_available_reproduces_client_04s_arithmetic() -> None:
    build = build_money_items(
        [
            _extracted("received", "completion payment", "£850,000"),
            _extracted("committed", "bridging loan", "£200,000"),
            _extracted("external", "earnout", "up to £400,000"),
        ],
        "meeting_notes.docx",
    )
    assert available_now(build.items).amount == Decimal("650000")


# --- facts ---------------------------------------------------------------------------------


def test_available_fact_has_the_available_to_invest_role_and_is_a_transaction() -> None:
    result = available_now(
        [_item("m1", "received", "£850,000"), _item("m2", "committed", "£200,000")]
    )
    assert result.value is not None
    fact = available_fact(result.value)
    assert fact.id == "money.available"
    assert fact.role == "available to invest"
    assert fact.transaction is True
    assert fact.reportable is True
    assert fact.value == result.value


def test_external_money_fact_is_role_excluded() -> None:
    fact = money_amount_fact(_item("m3", "external", "up to £400,000", counted=False))
    assert fact is not None
    assert fact.id == "money.m3.amount"
    assert fact.role == "excluded"
    assert fact.transaction is True


def test_received_and_committed_facts_have_their_own_roles() -> None:
    received = money_amount_fact(_item("m1", "received", "£850,000"))
    committed = money_amount_fact(_item("m2", "committed", "£200,000"))
    assert received is not None and committed is not None
    assert received.role == "received money"
    assert committed.role == "committed money"


def test_an_amountless_item_has_no_fact() -> None:
    assert money_amount_fact(_item("m2", "committed", None)) is None


def test_proceeds_items_have_no_money_fact_the_action_fact_carries_them() -> None:
    assert money_amount_fact(_item("m4", "proceeds", "around £45,000")) is None


def test_money_fact_descriptions_carry_no_digits() -> None:
    for money_class in ("received", "committed", "external"):
        fact = money_amount_fact(_item("m1", money_class, "£1,000"))
        assert fact is not None
        assert not any(ch.isdigit() for ch in fact.description)
    result = available_now([_item("m1", "received", "£1,000")])
    assert result.value is not None
    assert not any(ch.isdigit() for ch in available_fact(result.value).description)


def test_label_evidence_and_quote_types_are_the_extraction_ones() -> None:
    # guards the import aliasing above: the extraction schema, not the ledger's
    assert LabelEvidence(paragraph_id="p1", text="x").text == "x"
    assert Quote(paragraph_id="p1", text="y").text == "y"
