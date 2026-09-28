"""P5: money available now, and disposal proceeds, in code, never a model estimate.

Available now is received minus committed (`available_now`), computed only when there is
received money to begin with -- moving cash between a client's own existing accounts (client
01's ISA top-up) is not received/committed/proceeds/external money under P5 at all, so there
is nothing to compute. A commitment with no stated amount makes the available amount a
marker: "a guessed amount is never subtracted" (SCOPING.md P5), and likewise a received item
with no stated amount, commitments exceeding receipts, or mixed currencies (P12: never
converted). External money (contingent, not received: client 04's earnout) is named as
excluded and never counted. A derived value is approximate if any input is, rendered with
"c." and never rounded (`sum_values`).

`build_money_items` turns the meeting extraction's money items into ledger `MoneyItem`s; a
class with no verified evidence (DESIGN.md section 4.2's conservative default) is a review
item and is never allocated. Proceeds are the other half: `classify_money` (T19, client 02's
GIA disposal) counts a disposal's proceeds toward the plan's funding only when both the amount
sold and its destination are known -- at the value R3 (`reconcile/values.py`) already
selected for that account, never a separately-extracted figure, and rendered with P5's
qualifiers via the selected `Value`'s own precision/qualifier (never rounded). A portion sold,
or an unclear destination, is a marker instead: the caller (`pipeline.py`) never has an
amount to put in a `Fact`, so it can't reach the writer. `build_money_items` therefore skips
the extraction's "proceeds" items: the disposal path owns them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.extract.schemas import MoneyItem as ExtractedMoneyItem
from agent_pipeline.ledger import MoneyItem, Value
from agent_pipeline.reconcile.review import ReviewItemInput

DERIVED_SOURCE = "derived"


def sum_values(values: list[Value], selected_by: str) -> Value | None:
    """A derived total over source values, in code. Approximate if any input is (rendered
    "c.", never rounded); `None` for nothing to sum or for mixed currencies (P12: never
    converted). Carries no date and no source quote -- it names the rule that derived it."""
    if not values:
        return None
    if len({v.currency for v in values}) != 1:
        return None
    approximate = any(v.precision == "approximate" for v in values)
    return Value(
        amount=sum((v.amount for v in values), Decimal(0)),
        currency=values[0].currency,
        precision="approximate" if approximate else "exact",
        qualifier="circa" if approximate else "exact",
        date=None,
        source_id=DERIVED_SOURCE,
        quote="",
        selected_by=selected_by,
    )


@dataclass(frozen=True)
class AvailableResult:
    """`value` is the available-now figure, or `None` with either `marker_reason` set (the
    amount must become an adviser-review marker) or not (nothing to compute)."""

    value: Value | None
    marker_reason: str | None = None

    @property
    def amount(self) -> Decimal | None:
        return self.value.amount if self.value is not None else None


def available_now(money_items: list[MoneyItem]) -> AvailableResult:
    received = [m for m in money_items if m.money_class == "received"]
    if not received:
        return AvailableResult(value=None)
    committed = [m for m in money_items if m.money_class == "committed"]

    if any(m.amount is None for m in received):
        return AvailableResult(value=None, marker_reason="a received item has no stated amount")
    if any(m.amount is None for m in committed):
        return AvailableResult(
            value=None,
            marker_reason=(
                "a commitment has no stated amount; a guessed amount is never subtracted"
            ),
        )
    # every amount is present past the two checks above; the comprehension narrows the type
    received_values = [m.amount for m in received if m.amount is not None]
    committed_values = [m.amount for m in committed if m.amount is not None]

    total_received = sum_values(received_values, "P5")
    if total_received is None:
        return AvailableResult(value=None, marker_reason="money items are in different currencies")
    if committed_values:
        total_committed = sum_values(committed_values, "P5")
        if total_committed is None or total_committed.currency != total_received.currency:
            return AvailableResult(
                value=None, marker_reason="money items are in different currencies"
            )
        if total_committed.amount > total_received.amount:
            return AvailableResult(
                value=None, marker_reason="commitments exceed the money received"
            )
        approximate = "approximate" in (total_received.precision, total_committed.precision)
        return AvailableResult(
            value=total_received.model_copy(
                update={
                    "amount": total_received.amount - total_committed.amount,
                    "precision": "approximate" if approximate else "exact",
                    "qualifier": "circa" if approximate else "exact",
                }
            )
        )
    return AvailableResult(value=total_received)


def compute_available(money_items: list[MoneyItem]) -> Decimal | None:
    return available_now(money_items).amount


@dataclass(frozen=True)
class MoneyBuild:
    items: list[MoneyItem]
    review_items: list[ReviewItemInput]


_EXTERNAL_REASON = "contingent or not yet received; named as excluded, never allocated (P5)"


def build_money_items(
    extracted: list[ExtractedMoneyItem], source_id: str, start_index: int = 1
) -> MoneyBuild:
    """Ledger `MoneyItem`s for the received, committed and external items of a meeting
    extraction. The amount is parsed in code from the item's verified quote (D9); one that
    doesn't parse is a valueless item, never a guess. `start_index` lets the caller keep ids
    unique against the disposal-proceeds items it built separately."""
    items: list[MoneyItem] = []
    review_items: list[ReviewItemInput] = []
    for item in extracted:
        if item.money_class == "proceeds":
            continue  # the disposal path owns proceeds (classify_money)
        if item.money_class is None:
            review_items.append(
                ReviewItemInput(
                    kind="unverified",
                    blocking=False,
                    detail=(
                        f"money item ({item.purpose}): its class (received, committed, "
                        "proceeds or external) has no verified evidence, so it is not "
                        "treated as available."
                    ),
                    refs=[],
                )
            )
            continue
        parsed = parse_amount(item.amount.text) if item.amount is not None else None
        amount = (
            Value(
                amount=parsed.amount,
                currency=parsed.currency,
                precision=parsed.precision,
                qualifier=parsed.qualifier,
                date=None,
                source_id=source_id,
                quote=item.amount.text if item.amount is not None else "",
                selected_by="P5",
            )
            if parsed is not None
            else None
        )
        money_class: Literal["received", "committed", "external"] = item.money_class
        items.append(
            MoneyItem.model_validate(
                {
                    "id": f"m{start_index + len(items)}",
                    "class": money_class,
                    "amount": amount,
                    "counted": money_class != "external",
                    "reason": _EXTERNAL_REASON if money_class == "external" else "",
                    "quote": item.amount.text if item.amount is not None else item.purpose,
                    "source_id": source_id,
                }
            )
        )
    return MoneyBuild(items=items, review_items=review_items)


@dataclass(frozen=True)
class ProceedsClassification:
    counted: bool
    amount: Value | None
    reason: str


def classify_money(
    disposal_value: Value,
    extent: Literal["full", "portion", "unspecified"],
    destination_known: bool,
) -> ProceedsClassification:
    """P5's proceeds rule: counted only when the disposal is `full` (a stated `portion`
    amount is a future widening -- no client has one yet) and the destination is known.
    Otherwise a marker, never a guessed or partial figure."""
    if extent != "full":
        return ProceedsClassification(
            counted=False, amount=None, reason=f"disposal extent is {extent!r}, not full"
        )
    if not destination_known:
        return ProceedsClassification(
            counted=False, amount=None, reason="the destination of the proceeds is unclear"
        )
    return ProceedsClassification(counted=True, amount=disposal_value, reason="")
