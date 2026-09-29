"""A new account never leaks a synthetic id or an unsupported platform into client text
(tests first; verifier findings on the new-account change).

- The holdings table shows "To be opened" accounts by a readable label, not the synthetic
  `new:<slug>` id -- a client has never seen that string.
- The introduction's "held with <platform>" clause covers only accounts whose platform is
  known; an account with none is named without one.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.write.plan import _describe_scope
from agent_pipeline.write.table import build_table


def _ledger(*accounts: Account) -> Ledger:
    return Ledger(client="c", meeting_date=None, accounts=list(accounts))


def _existing() -> Account:
    return Account(
        id="X-1", type="Stocks & Shares ISA", owners=["Ann Poe"], platform="Alpha", in_scope=True
    )


def _new() -> Account:
    return Account(
        id="new:joint_investment_account",
        type="New joint account",
        owners=["Ann Poe", "Bob Poe"],
        platform=None,
        in_scope=True,
        is_new=True,
    )


def test_table_never_prints_the_synthetic_id() -> None:
    table = build_table(_ledger(_existing(), _new()))
    assert "new:" not in table
    assert "X-1" in table
    assert "To be opened" in table


def test_intro_does_not_give_a_new_account_the_others_platform() -> None:
    text = _describe_scope(_ledger(_existing(), _new()))
    assert "held with Alpha" in text
    assert text.index("held with Alpha") < text.index("New joint account")
    assert not text.rstrip().endswith("held with Alpha")


def test_intro_platform_clause_unchanged_when_every_account_has_one() -> None:
    other = Account(
        id="X-2",
        type="General Investment Account",
        owners=["Ann Poe"],
        platform="Alpha",
        in_scope=True,
    )
    text = _describe_scope(_ledger(_existing(), other))
    assert text.endswith("held with Alpha")
