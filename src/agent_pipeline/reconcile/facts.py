"""Builds `Ledger.facts{}` from reconciled data (DESIGN.md section 6): the fact IDs and
roles `write/plan.py`'s selectors and `write/writer.py`'s G9 check read. One function per
fact kind, like every other rule here -- not a job for `pipeline.py`, which owns stage
order and must not decide facts (ARCHITECTURE.md).
"""

from __future__ import annotations

from agent_pipeline.ledger import Account, Fact, MoneyItem, Value


def account_value_fact(account: Account) -> Fact | None:
    """`account.<id>.value` -- `None` if the account has no selected value yet (a marker
    covers that account instead; `write/table.py` already handles that case)."""
    if account.value is None:
        return None
    return Fact(
        id=f"account.{account.id}.value",
        kind="money",
        description=f"the {account.type}'s current value",
        value=account.value,
        reportable=True,
        transaction=False,
        role="account value",
    )


def action_amount_fact(action_id: str, amount: Value, *, is_proceeds: bool = False) -> Fact:
    """`action.<action_id>.amount` -- a top-up, proceeds or new-money figure: always
    `transaction=True`, so G9 keeps it out of Background. `is_proceeds` (T19, P5) carries
    P5's own required qualifiers into the fact's description -- gross, before any CGT, not
    yet realised -- so the writer has them to draw on; a plain internal transfer (client
    01's cash-to-ISA top-up) has none of that baggage and keeps the generic description."""
    description = (
        "the gross sale proceeds from this disposal, before any CGT and not yet realised"
        if is_proceeds
        else "the amount involved in this action"
    )
    return Fact(
        id=f"action.{action_id}.amount",
        kind="money",
        description=description,
        value=amount,
        reportable=True,
        transaction=True,
        role="sale proceeds" if is_proceeds else "transaction",
    )


def superseded_value_fact(account: Account, index: int, value: Value) -> Fact:
    """`account.<id>.superseded.<n>` (T19, R3/G2): a superseded value is still reportable,
    but only in the table's own footnote -- `placement="footnote_only"` is what lets G2
    allow it there without also allowing it to be quoted as if it were the account's
    current value anywhere else in the report."""
    return Fact(
        id=f"account.{account.id}.superseded.{index}",
        kind="money",
        description=f"the {account.type}'s superseded value",
        value=value,
        reportable=True,
        transaction=False,
        role="superseded value",
        placement="footnote_only",
    )


def money_amount_fact(item: MoneyItem) -> Fact | None:
    """`money.<id>.amount` (T21, P5): a received, committed or external money item's stated
    amount -- `None` for an amountless item (a marker covers it) and for proceeds, whose
    figure the disposal's `action.<id>.amount` fact already carries. Always
    `transaction=True` (G9 keeps money figures out of Background). External money's role is
    "excluded": it is named as not allocated, never as available."""
    if item.amount is None or item.money_class == "proceeds":
        return None
    role, description = {
        "received": ("received money", "money the client has already received"),
        "committed": ("committed money", "received money already committed elsewhere"),
        "external": (
            "excluded",
            "contingent money not yet received, excluded from the plan",
        ),
    }[item.money_class]
    return Fact(
        id=f"money.{item.id}.amount",
        kind="money",
        description=description,
        value=item.amount,
        reportable=True,
        transaction=True,
        role=role,
    )


def available_fact(value: Value) -> Fact:
    """`money.available` (T21, P5): received minus committed, computed in code."""
    return Fact(
        id="money.available",
        kind="money",
        description="the money available to invest now, after commitments",
        value=value,
        reportable=True,
        transaction=True,
        role="available to invest",
    )


def build_facts(
    accounts: list[Account],
    action_amounts: dict[str, Value],
    proceeds_action_ids: set[str] | None = None,
    money_items: list[MoneyItem] | None = None,
    available: Value | None = None,
) -> dict[str, Fact]:
    """Assembles the `facts{}` dict `plan_sections` reads. Scope filtering (which accounts
    to include) is the caller's decision, not this function's -- it just converts whatever
    it's given. `proceeds_action_ids` (T19): which `action_amounts` entries are disposal
    proceeds (P5), vs. a plain internal transfer -- the caller already knows this
    (`pipeline.py::_apply_proceeds_to_actions`), so it's not re-derived here."""
    proceeds_action_ids = proceeds_action_ids or set()
    facts: dict[str, Fact] = {}
    for account in accounts:
        fact = account_value_fact(account)
        if fact is not None:
            facts[fact.id] = fact
        for i, superseded in enumerate(account.superseded, start=1):
            fact = superseded_value_fact(account, i, superseded)
            facts[fact.id] = fact
    for action_id, amount in action_amounts.items():
        fact = action_amount_fact(action_id, amount, is_proceeds=action_id in proceeds_action_ids)
        facts[fact.id] = fact
    for item in money_items or []:
        money_fact = money_amount_fact(item)
        if money_fact is not None:
            facts[money_fact.id] = money_fact
    if available is not None:
        facts["money.available"] = available_fact(available)
    return facts
