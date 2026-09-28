"""T14: `fill_tokens` substitutes `{fact:<id>}`/`{marker:<key>}` tokens from the ledger;
`build_table` renders the account table in code, never by the model (P9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agent_pipeline.ledger import Account, Fact, Ledger, Marker, Qualifier, Value
from agent_pipeline.write.table import build_table
from agent_pipeline.write.tokens import TokenError, fill_tokens

MEETING_DATE = date(2026, 1, 1)


def _value(quote: str, amount: Decimal = Decimal("20000"), qualifier: Qualifier = "exact") -> Value:
    return Value(
        amount=amount,
        currency="GBP",
        precision="exact" if qualifier == "exact" else "approximate",
        qualifier=qualifier,
        date=MEETING_DATE,
        source_id="meeting_notes.docx",
        quote=quote,
        selected_by="R3",
    )


def _ledger(**overrides) -> Ledger:
    base = Ledger(
        client="client_01_clean",
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the top-up amount",
                value=_value("£20,000"),
                reportable=True,
                transaction=True,
                role="transaction",
            )
        },
        markers=[
            Marker(
                id="#1",
                key="platform_charge_holloway",
                text="the platform charge rate for Holloway",
                reason="not stated in any source",
                section="fees_charges",
            )
        ],
    )
    return base.model_copy(update=overrides)


def test_fill_tokens_substitutes_a_fact_token_with_rendered_prose():
    ledger = _ledger()
    text = "We recommend moving {fact:action.a1.amount} into the ISA."
    assert fill_tokens(text, ledger) == "We recommend moving £20,000 into the ISA."


def test_fill_tokens_substitutes_a_marker_token_with_the_bracket_format():
    ledger = _ledger()
    text = "The applicable rate is {marker:platform_charge_holloway}."
    assert fill_tokens(text, ledger) == (
        "The applicable rate is [ADVISER TO CONFIRM #1: the platform charge rate for Holloway]."
    )


def test_fill_tokens_keeps_the_qualifier_wording_in_prose():
    ledger = _ledger(
        facts={
            "account.h1.value": Fact(
                id="account.h1.value",
                kind="money",
                description="the ISA value",
                value=_value("c. £52,000", amount=Decimal("52000"), qualifier="circa"),
                reportable=True,
                role="account value",
            )
        }
    )
    text = "Your ISA is currently worth {fact:account.h1.value}."
    assert fill_tokens(text, ledger) == "Your ISA is currently worth c. £52,000."


def test_fill_tokens_normalises_a_divergent_qualifier_to_c():
    # T19, client 02's worked example: an approximate disposal value reads "c." in report
    # prose too, same as the table (`render_table`), never the source's own qualifier
    # wording ("a little over ..."), which only the account table's own footnote keeps
    # (`write/table.py`, which calls `render_prose` directly). "circa" (above) happens to
    # render "c." either way, which is why this only showed up once a genuinely divergent
    # qualifier existed.
    ledger = _ledger(
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the disposal proceeds",
                value=_value(
                    "a little over £45,000", amount=Decimal("45000"), qualifier="a_little_over"
                ),
                reportable=True,
                transaction=True,
                role="transaction",
            )
        }
    )
    text = "We will use {fact:action.a1.amount} to fund the top-up."
    assert fill_tokens(text, ledger) == "We will use c. £45,000 to fund the top-up."


def test_fill_tokens_raises_on_an_unknown_fact_id():
    ledger = _ledger()
    with pytest.raises(TokenError):
        fill_tokens("{fact:does.not.exist}", ledger)


def test_fill_tokens_raises_on_an_unknown_marker_key():
    ledger = _ledger()
    with pytest.raises(TokenError):
        fill_tokens("{marker:does_not_exist}", ledger)


def test_fill_tokens_raises_on_a_fact_with_no_value():
    ledger = _ledger(
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the top-up amount",
                role="transaction",
            )
        }
    )
    with pytest.raises(TokenError):
        fill_tokens("{fact:action.a1.amount}", ledger)


def _table_ledger(**overrides) -> Ledger:
    base = Ledger(
        client="client_01_clean",
        accounts=[
            Account(
                id="H-ISA-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                platform="Holloway",
                in_scope=True,
                value=_value("£52,000", amount=Decimal("52000")),
            )
        ],
    )
    return base.model_copy(update=overrides)


def test_build_table_renders_an_exact_value_row():
    table = build_table(_table_ledger())
    assert "| H-ISA-01 | Margaret Hughes | Stocks & Shares ISA | £52,000 |" in table


def test_build_table_shows_to_be_opened_for_a_new_account():
    ledger = _table_ledger(
        accounts=[
            Account(
                id="H-NEW-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                platform="Holloway",
                in_scope=True,
                is_new=True,
            )
        ]
    )
    table = build_table(ledger)
    assert "| H-NEW-01 | Margaret Hughes | Stocks & Shares ISA | To be opened |" in table


def test_build_table_footnotes_a_superseded_value_never_the_cell():
    superseded = _value("c. £48,000 (2025 statement)", amount=Decimal("48000"), qualifier="circa")
    superseded = superseded.model_copy(
        update={"source_id": "annual_statement_2025.png", "date": date(2025, 1, 1)}
    )
    account = Account(
        id="H-ISA-01",
        owners=["Margaret Hughes"],
        type="Stocks & Shares ISA",
        platform="Holloway",
        in_scope=True,
        value=_value("£52,000", amount=Decimal("52000")),
        superseded=[superseded],
    )
    ledger = _table_ledger(accounts=[account])
    table = build_table(ledger)
    assert "| H-ISA-01 | Margaret Hughes | Stocks & Shares ISA | £52,000 |" in table
    assert "£48,000" not in table.split("\n\n")[0]
    footnote_block = table.split("\n\n", 1)[1]
    # The footnote names the source in client terms, never its internal filename (P9): an
    # image is "your statement". The earlier assertion pinned the raw filename, which the
    # release judge flags as system information (G10).
    assert "your statement" in footnote_block
    assert "annual_statement_2025.png" not in footnote_block
    assert "c. £48,000" in footnote_block


def test_build_table_excludes_out_of_scope_accounts():
    ledger = _table_ledger(
        accounts=[
            Account(
                id="H-CASH-01",
                owners=["Margaret Hughes"],
                type="Cash Account",
                platform="Holloway",
                in_scope=False,
            )
        ]
    )
    table = build_table(ledger)
    assert "H-CASH-01" not in table
