"""T19: `_describe_scope` widened for more than one in-scope account -- client 02's three
accounts exposed two defects in the single-account original: repeating "held with
<platform>" once per account, and no way to tell two same-type accounts apart (its own two
ISAs). Client 01's exact single-account phrasing is unchanged (`test_write_plan.py`'s own
`test_scope_description_context_built_from_in_scope_accounts`)."""

from __future__ import annotations

from agent_pipeline.config import Placeholder, ReportConfig, Section
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.write.plan import plan_sections


def _account(account_id: str, owners: list[str], account_type: str, platform: str) -> Account:
    return Account(
        id=account_id, owners=owners, type=account_type, platform=platform, in_scope=True
    )


def _plan_scope(ledger: Ledger) -> str:
    section = Section(
        id="introduction",
        title="Introduction",
        use_if="always",
        template="<<scope>>",
        placeholders={"scope": Placeholder(kind="generated", prompt="...")},
        context=["scope_description"],
    )

    config = ReportConfig(document_title="x", global_instructions="x", sections=[section])
    plans = plan_sections(ledger, config)
    return plans[0].context["scope_description"]


def test_same_type_accounts_are_disambiguated_by_owner() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _account("H-ISA-D", ["David Clarke"], "Stocks & Shares ISA", "Holloway"),
            _account(
                "H-GIA-J",
                ["David Clarke", "Susan Clarke"],
                "General Investment Account",
                "Holloway",
            ),
            _account("H-ISA-S", ["Susan Clarke"], "Stocks & Shares ISA", "Holloway"),
        ],
    )
    description = _plan_scope(ledger)
    assert "David's Stocks & Shares ISA" in description
    assert "Susan's Stocks & Shares ISA" in description
    assert "your General Investment Account" in description
    assert description.count("held with Holloway") == 1


def test_a_joint_account_is_never_given_an_owner_possessive() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _account(
                "H-GIA-J",
                ["David Clarke", "Susan Clarke"],
                "General Investment Account",
                "Holloway",
            ),
        ],
    )
    description = _plan_scope(ledger)
    assert description == "your General Investment Account held with Holloway"


def test_a_single_same_type_account_keeps_the_your_phrasing() -> None:
    # Only disambiguated when there's genuinely more than one of the same type in scope.
    ledger = Ledger(
        client="c",
        accounts=[_account("H-ISA-D", ["David Clarke"], "Stocks & Shares ISA", "Holloway")],
    )
    assert _plan_scope(ledger) == "your Stocks & Shares ISA held with Holloway"
