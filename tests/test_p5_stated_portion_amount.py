"""P5 for a portion whose amount the note states (tests first; hand-written case 07).

SCOPING P5: proceeds count toward the plan's funding once both the amount and the destination
are known. A `full` disposal's amount is the account's value; a `portion` used to be always a
marker, but when the note states the amount sold ("sell 10,000 of the account and use the
proceeds to ...") both are known, so the stated amount counts, as gross proceeds. With no stated
amount a portion is still an unspecified amount (a marker, D24). Never a guessed figure: the
amount is parsed in code from the verified quote (D9).
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.money import classify_money, stated_proceeds_amount

ACCOUNT_VALUE = Value(
    amount=Decimal("60000"),
    currency="GBP",
    precision="exact",
    qualifier="exact",
    date=None,
    source_id="db",
    quote="",
    selected_by="R3",
)
STATED = Value(
    amount=Decimal("10000"),
    currency="GBP",
    precision="exact",
    qualifier="exact",
    date=None,
    source_id="m",
    quote="£10,000",
    selected_by="P5",
)


def test_a_portion_with_a_stated_amount_and_a_known_destination_counts_that_amount() -> None:
    result = classify_money(ACCOUNT_VALUE, "portion", True, stated_amount=STATED)
    assert result.counted and result.amount == STATED


def test_an_unspecified_extent_with_a_stated_amount_counts_the_same_way() -> None:
    assert classify_money(ACCOUNT_VALUE, "unspecified", True, stated_amount=STATED).counted


def test_a_stated_amount_with_an_unclear_destination_is_not_counted() -> None:
    result = classify_money(ACCOUNT_VALUE, "portion", False, stated_amount=STATED)
    assert not result.counted and result.amount is None and "destination" in result.reason


def test_a_portion_with_no_stated_amount_is_still_not_counted() -> None:
    result = classify_money(ACCOUNT_VALUE, "portion", True)
    assert not result.counted and result.amount is None


def test_a_full_disposal_ignores_a_stated_amount_and_counts_the_account_value() -> None:
    result = classify_money(ACCOUNT_VALUE, "full", True, stated_amount=STATED)
    assert result.counted and result.amount == ACCOUNT_VALUE


def test_the_stated_amount_is_read_from_the_single_proceeds_item_in_code() -> None:
    from agent_pipeline.extract.schemas import LabelEvidence, MoneyItem, Quote

    item = MoneyItem(
        money_class="proceeds",
        purpose="sale",
        amount=Quote(paragraph_id="p1", text="£10,000"),
        class_evidence=LabelEvidence(paragraph_id="p1", text="use the proceeds"),
    )
    value = stated_proceeds_amount([item], "meeting_notes.docx")
    assert value is not None and value.amount == Decimal("10000")
    assert value.currency == "GBP" and value.selected_by == "P5"


def test_no_stated_amount_when_there_are_none_or_several() -> None:
    from agent_pipeline.extract.schemas import LabelEvidence, MoneyItem, Quote

    def proceeds(text: str | None) -> MoneyItem:
        return MoneyItem(
            money_class="proceeds",
            purpose="sale",
            amount=Quote(paragraph_id="p1", text=text) if text else None,
            class_evidence=LabelEvidence(paragraph_id="p1", text="proceeds"),
        )

    assert stated_proceeds_amount([], "m") is None
    assert stated_proceeds_amount([proceeds(None)], "m") is None
    assert stated_proceeds_amount([proceeds("£1,000"), proceeds("£2,000")], "m") is None
