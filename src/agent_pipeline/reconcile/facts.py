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


def action_amount_fact(action_id: str, amount: Value) -> Fact:
    """`action.<action_id>.amount` -- a top-up, proceeds or new-money figure: always
    `transaction=True`, so G9 keeps it out of Background."""
    return Fact(
        id=f"action.{action_id}.amount",
        kind="money",
        description="the amount involved in this action",
        value=amount,
        reportable=True,
        transaction=True,
        role="transaction",
    )


def build_facts(accounts: list[Account], action_amounts: dict[str, Value]) -> dict[str, Fact]:
    """Assembles the `facts{}` dict `plan_sections` reads. Scope filtering (which accounts
    to include) is the caller's decision, not this function's -- it just converts whatever
    it's given."""
    facts: dict[str, Fact] = {}
    for account in accounts:
        fact = account_value_fact(account)
        if fact is not None:
            facts[fact.id] = fact
    for action_id, amount in action_amounts.items():
        fact = action_amount_fact(action_id, amount)
        facts[fact.id] = fact
    return facts
