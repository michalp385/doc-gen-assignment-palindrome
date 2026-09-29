"""The facts ledger: one typed record of every fact, its source and the rule that selected
it (T6, DESIGN.md section 6, S5). The table, the tokens, the markers and the review sheet
all read from this, so a report can't contradict itself the way the baseline's client 03
report did, whose Conclusion gave a different account value from its own table (SCOPING.md
section 6).
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Qualifier = Literal["exact", "around", "a_little_over", "a_little_under", "up_to", "circa"]
Precision = Literal["exact", "approximate"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Value(_Strict):
    """A single dated figure, with the source it came from and the rule that selected it."""

    amount: Decimal
    currency: str
    precision: Precision
    qualifier: Qualifier
    date: _date | None
    source_id: str
    quote: str
    selected_by: str  # the trust rule, e.g. "R3"


class Fact(_Strict):
    id: str
    kind: str
    description: str  # never contains digits; a figure reaches prose only via render_*
    value: Value | None = None
    reportable: bool = False
    transaction: bool = False  # a top-up, proceeds, new money or tax figure (G9: never Background)
    role: str = "any"  # e.g. "account value", "available to invest", "sale proceeds", "excluded"
    placement: Literal["any", "table", "footnote_only", "never"] = "any"


class Account(_Strict):
    id: str
    owners: list[str]
    type: str
    platform: str | None = None
    status: Literal["open", "closed"] = "open"
    in_scope: bool = False
    scope_reason: str | None = None
    is_new: bool = False
    value: Value | None = None
    superseded: list[Value] = Field(default_factory=list)
    value_marker: str | None = None


class MoneyItem(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    money_class: Literal["received", "committed", "proceeds", "external"] = Field(alias="class")
    amount: Value | None = None
    counted: bool = False
    reason: str = ""
    quote: str = ""
    source_id: str = ""


class Action(_Strict):
    id: str
    description: str
    kind: Literal["action", "non_action"] = "action"
    accounts: list[str] = Field(default_factory=list)
    quote: str = ""
    source_id: str = ""


class ExcludedItem(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    item_class: Literal["tangent", "aspiration", "circumstance"] = Field(alias="class")
    description: str
    allowed_in: list[str] = Field(default_factory=list)
    quote: str = ""


class Marker(_Strict):
    id: str  # "#1", "#2", ...; assigned by number_markers, empty until then
    key: str
    text: str  # built in code from the ledger, never by a model (P1)
    reason: str
    section: str
    fact_ref: str | None = None


class ReviewItem(_Strict):
    id: str
    kind: str
    blocking: bool = False
    detail: str = ""
    refs: list[str] = Field(default_factory=list)


class Question(_Strict):
    id: str
    kind: str
    subject_ref: str
    status: Literal["resolved", "unresolved"] = "unresolved"
    accepted: bool = False
    reason: str = ""
    resolved_to: str | None = None  # the account an accepted investigation finding linked


class Ledger(_Strict):
    client: str
    meeting_date: _date | None = None
    # The report instruction's own values, verbatim (G13); None until T10's config/instruction
    # loading populates them from a real run -- LedgerTruth (gates/truth.py) needs a field to
    # read, not a speculative one: G13 is in T9's gate scope and has nothing else to check.
    risk_profile: str | None = None
    initial_charge: str | None = None
    # A plain, digit-free summary of the client's objectives and circumstances (write/plan.py's
    # "objectives" context key); None until real extraction/reconciliation populates it (T16).
    objectives: str | None = None
    # Whether the Tax Implications section applies (G5), set by resolve_sections's
    # `taxable_disposal` predicate (reconcile/sections.py); mirrors that decision so gates
    # don't re-derive it from raw disposal data.
    tax_section: bool = False
    accounts: list[Account] = Field(default_factory=list)
    money: list[MoneyItem] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    excluded: list[ExcludedItem] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)
    review: list[ReviewItem] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    facts: dict[str, Fact] = Field(default_factory=dict)


_CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}

_PROSE_PREFIX: dict[Qualifier, str] = {
    "exact": "",
    "around": "around ",
    "a_little_over": "a little over ",
    "a_little_under": "a little under ",
    "up_to": "up to ",
    "circa": "c. ",
}


def _format_amount(value: Value) -> str:
    symbol = _CURRENCY_SYMBOLS.get(value.currency, f"{value.currency} ")
    if value.amount == value.amount.to_integral_value():
        number = f"{int(value.amount):,}"
    else:
        number = f"{value.amount:,}"
    return f"{symbol}{number}"


def render_table(value: Value) -> str:
    """How a value appears in the account table (P9): 'c.' for any approximate value,
    regardless of the source's own qualifier wording."""
    formatted = _format_amount(value)
    return formatted if value.precision == "exact" else f"c. {formatted}"


def render_prose(value: Value) -> str:
    """How a value reads inline in a sentence: keeps the source's own qualifier wording."""
    return f"{_PROSE_PREFIX[value.qualifier]}{_format_amount(value)}"


def render_date(d: _date) -> str:
    """ "day Month" (e.g. "15 March"), for review-sheet text (G15's superseded-value item
    quotes both dates this way, not ISO). Never `%-d`: that flag isn't portable across
    platforms, unlike building the string from `d.day` directly."""
    return f"{d.day} {d.strftime('%B')}"


def number_markers(ledger: Ledger, report_order: list[str]) -> Ledger:
    """Assign '#1', '#2', ... to markers by order of first appearance in the assembled
    report (P1), not the order they were created in. A marker whose key never appears in
    `report_order` is still numbered, after every marker that did appear."""
    numbers: dict[str, int] = {}
    for key in report_order:
        if key not in numbers:
            numbers[key] = len(numbers) + 1
    for marker in ledger.markers:
        if marker.key not in numbers:
            numbers[marker.key] = len(numbers) + 1

    numbered = [
        marker.model_copy(update={"id": f"#{numbers[marker.key]}"}) for marker in ledger.markers
    ]
    return ledger.model_copy(update={"markers": numbered})
