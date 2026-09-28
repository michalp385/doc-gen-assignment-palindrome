"""T18 live check finding: the real vision model reports `amount_text` without the currency
symbol (e.g. "61,000", not "£61,000") since it's asked for separately as `currency_symbol` --
but `parse_amount` needs a symbol or code to recognise an amount at all, so `check_image_row`
must put the symbol back before parsing, or a genuine disagreement silently never gets
flagged."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.values import check_image_row


def _value(amount: str) -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 4, 30),
        source_id="client_data_db.json",
        quote="",
        selected_by="R3",
    )


def _row(amount_text: str, currency_symbol: str = "£") -> ImageValueRow:
    return ImageValueRow(
        account_label="an account",
        account_type="Stocks & Shares ISA",
        amount_text=amount_text,
        currency_symbol=currency_symbol,
    )


def test_a_confirming_amount_with_no_symbol_in_amount_text_is_still_recognised() -> None:
    # This is the real model's actual output shape (confirmed live, T18): the symbol lives
    # only in currency_symbol, not folded into amount_text.
    result = check_image_row(_value("61000"), _row("61,000"), "GBP")

    assert result is None


def test_a_disagreeing_amount_with_no_symbol_in_amount_text_is_still_flagged() -> None:
    result = check_image_row(_value("61000"), _row("99,000"), "GBP")

    assert result is not None
    assert result.kind == "image_discrepancy"


def test_an_amount_text_that_already_includes_the_symbol_still_parses() -> None:
    # Robust either way, in case a future model folds the symbol in after all.
    result = check_image_row(_value("61000"), _row("£61,000"), "GBP")

    assert result is None
