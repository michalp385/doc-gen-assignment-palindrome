"""Parse amounts and dates from verbatim source quotes (T4, D9).

Every figure and date in the report traces to a source value (CLAUDE.md's non-negotiable):
extraction returns a quote, and this module parses the number or date from the quote text
itself, never from a value a model put in a structured field. A quote with no recognised
amount or date parses to None rather than guessing, so an unparseable or ambiguous source
degrades to a review item upstream instead of producing a fabricated figure (DESIGN.md
section 4.1, section 8.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Qualifier = Literal["exact", "around", "a_little_over", "a_little_under", "up_to", "circa"]
Precision = Literal["exact", "approximate"]

_EXACT_QUALIFIER: Qualifier = "exact"

_CURRENCY_SYMBOLS = {"£": "GBP", "€": "EUR", "$": "USD"}
_CURRENCY_CODES = {"GBP", "EUR", "USD"}
_SUFFIX_MULTIPLIERS = {"k": Decimal(1_000), "m": Decimal(1_000_000)}

# Symbol immediately before the number (optional space), e.g. "£12,340", "£3.4m", "€16,800".
_SYMBOL_AMOUNT_RE = re.compile(
    r"(?P<symbol>[£€$])\s?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suffix>[kKmM])?"
)
# Currency code before the number, e.g. "GBP 7,500".
_CODE_AMOUNT_RE = re.compile(
    r"\b(?P<code>GBP|EUR|USD)\s+(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suffix>[kKmM])?"
)

# Longer/more specific phrases first, so "a little over" isn't shadowed by a looser pattern.
_QUALIFIER_PATTERNS: list[tuple[re.Pattern[str], Qualifier]] = [
    (re.compile(r"\ba little over\b", re.IGNORECASE), "a_little_over"),
    (re.compile(r"\ba little under\b", re.IGNORECASE), "a_little_under"),
    (re.compile(r"\bup to\b", re.IGNORECASE), "up_to"),
    (re.compile(r"\baround\b", re.IGNORECASE), "around"),
    (re.compile(r"\bapproximately\b", re.IGNORECASE), "around"),
    (re.compile(r"(?:^|[\s\"'(])c\.\s*(?=[£€$]|\d)", re.IGNORECASE), "circa"),
    (re.compile(r"\bcirca\b", re.IGNORECASE), "circa"),
]


@dataclass(frozen=True)
class ParsedAmount:
    amount: Decimal
    currency: str
    qualifier: Qualifier
    precision: Precision


def _qualifier_in(quote: str) -> Qualifier:
    for pattern, qualifier in _QUALIFIER_PATTERNS:
        if pattern.search(quote):
            return qualifier
    return _EXACT_QUALIFIER


def parse_amount(quote: str) -> ParsedAmount | None:
    """Parse the first recognised money amount in `quote`, or None if there isn't one."""
    match = _SYMBOL_AMOUNT_RE.search(quote)
    if match:
        currency = _CURRENCY_SYMBOLS[match.group("symbol")]
    else:
        match = _CODE_AMOUNT_RE.search(quote)
        if match is None:
            return None
        currency = match.group("code")

    number = Decimal(match.group("num").replace(",", ""))
    suffix = match.group("suffix")
    if suffix:
        number *= _SUFFIX_MULTIPLIERS[suffix.lower()]

    qualifier = _qualifier_in(quote)
    precision: Precision = "exact" if qualifier == _EXACT_QUALIFIER else "approximate"
    return ParsedAmount(amount=number, currency=currency, qualifier=qualifier, precision=precision)


_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}  # fmt: skip

# "12 May 2026", "held 14 May 2026", "15 Mar 2026".
_TEXTUAL_DATE_RE = re.compile(r"\b(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\b")
# "2026-04-30" (ISO, unambiguous).
_ISO_DATE_RE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")


def parse_date(quote: str) -> date | None:
    """Parse the first unambiguous date in `quote`, or None.

    Only ISO (YYYY-MM-DD) and "D Month YYYY" forms are recognised: both name the month
    unambiguously. A slash- or dot-separated numeric date (day/month order undecidable
    without knowing the source's convention) is never guessed.
    """
    match = _TEXTUAL_DATE_RE.search(quote)
    if match:
        month = _MONTHS.get(match.group("month").lower())
        if month is None:
            return None
        try:
            return date(int(match.group("year")), month, int(match.group("day")))
        except ValueError:
            return None

    match = _ISO_DATE_RE.search(quote)
    if match:
        try:
            return date(
                int(match.group("year")), int(match.group("month")), int(match.group("day"))
            )
        except ValueError:
            return None

    return None
