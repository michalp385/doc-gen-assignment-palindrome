"""Amount and date parsing from quotes (T4). Code parses every figure and date from the
verbatim quote itself; a model's own field is never trusted (D9, DESIGN.md section 4.1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agent_pipeline.extract.parsing import parse_amount, parse_date


@pytest.mark.parametrize(
    ("quote", "amount", "currency", "qualifier", "precision"),
    [
        ("The ISA is worth £45,000.", "45000", "GBP", "exact", "exact"),
        ("Investment amount | GBP 120,000", "120000", "GBP", "exact", "exact"),
        ("The fund is valued at £1.2m.", "1200000", "GBP", "exact", "exact"),
        ("She would like to move £45k into the ISA.", "45000", "GBP", "exact", "exact"),
        (
            "a deferred earnout of up to £400,000, payable over two years",
            "400000",
            "GBP",
            "up_to",
            "approximate",
        ),
        (
            "It was showing a little over £45,000, which is up from where it had been.",
            "45000",
            "GBP",
            "a_little_over",
            "approximate",
        ),
        (
            "Pulling it up during the meeting, it was showing around £38,000.",
            "38000",
            "GBP",
            "around",
            "approximate",
        ),
        (
            'Meeting note, 14 May 2026: "c. £45,000".',
            "45000",
            "GBP",
            "circa",
            "approximate",
        ),
        (
            "A separate automated read of these same images reported €61,000.",
            "61000",
            "EUR",
            "exact",
            "exact",
        ),
    ],
)
def test_parse_amount_recognised_forms(
    quote: str, amount: str, currency: str, qualifier: str, precision: str
) -> None:
    parsed = parse_amount(quote)
    assert parsed is not None, f"expected an amount in {quote!r}"
    assert parsed.amount == Decimal(amount)
    assert parsed.currency == currency
    assert parsed.qualifier == qualifier
    assert parsed.precision == precision


def test_parse_amount_a_little_under() -> None:
    parsed = parse_amount("The account was a little under £20,000 at the last review.")
    assert parsed is not None
    assert parsed.amount == Decimal("20000")
    assert parsed.qualifier == "a_little_under"
    assert parsed.precision == "approximate"


@pytest.mark.parametrize(
    "quote",
    [
        "Held 12 May 2026 at our offices.",
        "No investments are being sold to do this.",
        "Margaret has no income requirement from the portfolio.",
        "",
    ],
)
def test_parse_amount_returns_none_when_there_is_no_amount(quote: str) -> None:
    assert parse_amount(quote) is None


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        (
            "Annual review meeting with Margaret Hughes, held 12 May 2026 at our offices.",
            date(2026, 5, 12),
        ),
        ("Last statement value: £40,000 at 15 Mar 2026.", date(2026, 3, 15)),
        ('"snapshot_date": "2026-04-30"', date(2026, 4, 30)),
        ("Review meeting with David and Susan Clarke, held 14 May 2026.", date(2026, 5, 14)),
    ],
)
def test_parse_date_recognised_forms(quote: str, expected: date) -> None:
    assert parse_date(quote) == expected


@pytest.mark.parametrize(
    "quote",
    [
        "Review meeting with Mildred Sowerby.",  # no date at all
        "sometime next spring",  # no day or year
        "14/05/2026",  # day/month order is ambiguous; never guessed
        "",
    ],
)
def test_parse_date_returns_none_when_ambiguous_or_absent(quote: str) -> None:
    assert parse_date(quote) is None
