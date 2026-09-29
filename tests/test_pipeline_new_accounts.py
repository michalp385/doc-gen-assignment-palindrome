"""Wiring for new accounts (tests first): a verified `new_accounts` extraction becomes ledger
accounts, a charges marker and review items; a new account is never given the "no value" marker
that an existing valueless account gets (its value is "To be opened"); and the shipped config
routes the charges marker to Fees & Charges, so the unrouted-marker safeguard does not stop a
run that has one.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.config import load_report_config
from agent_pipeline.extract.schemas import NewAccount, Quote
from agent_pipeline.ledger import Account, Ledger, Marker
from agent_pipeline.pipeline import _apply_new_accounts
from agent_pipeline.reconcile.account_state import check_account_states
from agent_pipeline.sources.adapters.json_accounts import AccountData, AccountRecord, Holder
from agent_pipeline.write.plan import plan_sections, unrouted_markers


def _data() -> AccountData:
    record = AccountRecord(account_id="X-ISA", type="Stocks & Shares ISA", status="open")
    return AccountData(
        holders={
            "client": Holder(name="Robert Fletcher", accounts=[record]),
            "partner": Holder(name="Jean Fletcher", accounts=[]),
        }
    )


def _mention(joint: bool = True) -> NewAccount:
    return NewAccount(
        description=Quote(paragraph_id="p9", text="open a new joint account"), joint=joint
    )


def test_a_verified_mention_becomes_a_to_be_opened_account_a_marker_and_a_review_row() -> None:
    accounts, markers, items = _apply_new_accounts(
        [_mention()], "the ISAs and a new joint account", _data()
    )
    (account,) = accounts
    assert account.id == "new:joint_investment_account"
    assert account.owners == ["Robert Fletcher", "Jean Fletcher"]
    assert account.is_new and account.in_scope and account.value is None
    assert [m.key for m in markers] == ["new_account_charges"]
    assert [i.kind for i in items] == ["scope_flag"]


def test_no_mentions_change_nothing() -> None:
    assert _apply_new_accounts([], "the ISAs", _data()) == ([], [], [])


def test_a_mention_the_scope_does_not_name_is_a_conflict_and_no_account() -> None:
    accounts, markers, items = _apply_new_accounts([_mention()], "the ISAs only", _data())
    assert accounts == [] and markers == []
    assert [i.kind for i in items] == ["conflict"]


def test_a_new_account_never_gets_the_no_value_marker() -> None:
    new, _, _ = _apply_new_accounts([_mention()], "and a new joint account", _data())
    state = check_account_states(new, {})["new:joint_investment_account"]
    assert state.value_marker is None
    assert state.review_items == []
    assert state.withhold_value is False
    assert state.in_table is True


def test_an_existing_valueless_account_still_gets_the_marker() -> None:
    account = Account(id="A", owners=["A B"], type="SIPP", in_scope=True)
    assert check_account_states([account], {"A": "GBP"})["A"].value_marker is not None


def test_the_shipped_config_routes_the_charges_marker_to_a_section() -> None:
    config = load_report_config(Path("config/template_config.json"))
    ledger = Ledger(
        client="c",
        markers=[
            Marker(
                id="#1",
                key="new_account_charges",
                text="charges on the new joint account",
                reason="r",
                section="fees_charges",
            ),
            Marker(
                id="#2",
                key="new_account_charges_2",
                text="charges on the new account",
                reason="r",
                section="fees_charges",
            ),
        ],
    )
    plans = plan_sections(ledger, config)
    assert unrouted_markers(ledger, plans) == []
