"""Builds `Ledger.facts{}` from reconciled data (DESIGN.md section 6): the fact IDs and
roles `write/plan.py`'s selectors and `write/writer.py`'s G9 check read. One function per
fact kind, like every other rule here -- not a job for `pipeline.py`, which owns stage
order and must not decide facts (ARCHITECTURE.md).
"""

from __future__ import annotations

from agent_pipeline.ledger import Account, Fact, Value


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


def build_facts(
    accounts: list[Account],
    action_amounts: dict[str, Value],
    proceeds_action_ids: set[str] | None = None,
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
    return facts
