"""P10: a statement image that prints a currency code, not a symbol (tests first; case 01).

The vision model reports the currency separately from the digits, and for "GBP 34,000" that
currency is the code "GBP". Gluing it to the digits ("GBP34,000") made `parse_amount` fail
silently, so a genuine disagreement with the selected value was never flagged. The row is now
parsed with a separating space, and the item names the figure as printed, the selected value and
the date the statement gives.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.values import check_image_row

SELECTED = Value(
    amount=Decimal("30000"),
    currency="GBP",
    precision="exact",
    qualifier="exact",
    date=date(2026, 6, 1),
    source_id="client_data_db.json",
    quote="",
    selected_by="R3",
)


def _row(symbol: str, amount: str) -> ImageValueRow:
    return ImageValueRow(
        account_label="Holloway ISA (Helen)",
        account_type="Stocks & Shares ISA",
        amount_text=amount,
        currency_symbol=symbol,
        valued_on_text="10 Jun 2026",
    )


def test_a_currency_code_row_that_disagrees_is_flagged_with_both_figures_and_the_date() -> None:
    item = check_image_row(SELECTED, _row("GBP", "34,000"), "GBP")
    assert item is not None and item.kind == "image_discrepancy" and not item.blocking
    assert "GBP 34,000" in item.detail
    assert "£30,000" in item.detail
    assert "10 Jun 2026" in item.detail


def test_a_currency_code_row_that_agrees_is_silent() -> None:
    assert check_image_row(SELECTED, _row("GBP", "30,000"), "GBP") is None


def test_a_symbol_row_still_works() -> None:
    item = check_image_row(SELECTED, _row("£", "34,000"), "GBP")
    assert item is not None and item.kind == "image_discrepancy"
    # The wording symbol rows have always had, which committed ledgers carry.
    assert item.detail == (
        "statement image shows '34,000' for 'Holloway ISA (Helen)'; selected value is 30000"
    )
    assert check_image_row(SELECTED, _row("£", "30,000"), "GBP") is None
