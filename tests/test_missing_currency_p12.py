"""Two spec fixes, tests first.

1. P12 / DESIGN 3.3: "a missing currency is treated as not-GBP". A record with no `currency`
   must never have its value rendered as sterling: the value cell is a marker, the value is
   withheld, the review sheet records it. `select_values` used to label a missing currency
   GBP, the opposite.
2. A marker that reaches no section would silently vanish. `unrouted_markers` finds them and
   the pipeline fails the run instead of dropping them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from agent_pipeline.ledger import Account, Value
from agent_pipeline.pipeline import _apply_account_states
from agent_pipeline.reconcile.account_state import check_account_states
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.reconcile.values import select_values
from agent_pipeline.sources.adapters.json_accounts import read_accounts


def _account(in_scope: bool = True) -> Account:
    return Account(
        id="X-GIA",
        owners=["A Client"],
        type="General Investment Account",
        platform="Holloway",
        in_scope=in_scope,
        value=Value(
            amount=Decimal("18000"),
            currency="GBP",
            precision="exact",
            qualifier="exact",
            date=date(2026, 5, 1),
            source_id="db",
            quote="",
            selected_by="R3",
        ),
    )


# --- a missing currency is not GBP ---------------------------------------------------------


def test_select_values_never_labels_a_missing_currency_gbp() -> None:
    value = select_values(Decimal("1000"), date(2026, 4, 30), None, [])
    assert value is not None
    assert value.currency != "GBP"


def test_select_values_keeps_a_stated_currency() -> None:
    value = select_values(Decimal("1000"), date(2026, 4, 30), "EUR", [])
    assert value is not None and value.currency == "EUR"


@pytest.mark.parametrize("currency_by_id", [{"X-GIA": None}, {}])
def test_a_missing_currency_in_scope_is_a_marker_and_the_value_is_withheld(
    currency_by_id: dict[str, str | None],
) -> None:
    state = check_account_states([_account()], currency_by_id)["X-GIA"]
    assert state.withhold_value is True
    assert state.value_marker is not None
    assert state.value_marker.key == "gia_currency_unknown"
    assert not any(ch.isdigit() for ch in state.value_marker.text)
    (item,) = state.review_items
    assert item.kind == "currency"
    assert "not stated" in item.detail


def test_a_missing_currency_out_of_scope_is_withheld_without_a_marker() -> None:
    state = check_account_states([_account(in_scope=False)], {})["X-GIA"]
    assert state.withhold_value is True
    assert state.value_marker is None
    assert state.review_items == []


def test_a_blank_currency_counts_as_missing() -> None:
    state = check_account_states([_account()], {"X-GIA": "  "})["X-GIA"]
    assert state.withhold_value is True


def test_the_stage_graph_helper_withholds_a_missing_currency_value() -> None:
    accounts, markers, items = _apply_account_states([_account()], {})
    assert accounts[0].value is None
    assert [m.key for m in markers] == ["gia_currency_unknown"]
    assert [i.kind for i in items] == ["currency"]


@pytest.mark.parametrize(
    "client", ["client_01_clean", "client_02_medium", "client_03_hard", "client_04_stretch"]
)
def test_the_real_clients_all_state_gbp_so_nothing_changes_for_them(client: str) -> None:
    data = read_accounts(Path(f"data/{client}/client_data_db.json"))
    accounts = [a.model_copy(update={"in_scope": True}) for a in resolve_ownership(data).accounts]
    currency = {
        r.account_id: r.currency
        for holder in data.holders.values()
        for r in holder.accounts
        if r.account_id
    }
    assert all(c == "GBP" for c in currency.values())
    states = check_account_states(accounts, currency)
    assert not any(s.value_marker and "currency" in s.value_marker.key for s in states.values())
