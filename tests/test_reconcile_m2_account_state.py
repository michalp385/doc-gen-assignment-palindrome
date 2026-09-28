"""R6 (null / closed accounts) and P12 (non-GBP values), tests first (T20/T21).

R6: a closed account outside scope is ignored; a closed account inside scope is a blocking
conflict, never silently dropped; an open account with no value is a marker in the value cell
when in scope and a review-sheet item only when out of scope. P12: a value not in GBP is never
converted -- the value cell is a marker and the review sheet records it (a missing currency is
treated as not-GBP, DESIGN.md section 3.3).

Client 03's and 04's shapes are read from their real account data; the rest are built inline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.account_state import check_account_states
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.sources.adapters.json_accounts import read_accounts


def _account(
    account_id: str,
    type_: str = "Stocks & Shares ISA",
    *,
    in_scope: bool = True,
    status: Literal["open", "closed"] = "open",
    platform: str | None = "Holloway",
) -> Account:
    return Account(
        id=account_id,
        owners=["A Client"],
        type=type_,
        platform=platform,
        status=status,
        in_scope=in_scope,
    )


def _with_value(account: Account) -> Account:
    from datetime import date
    from decimal import Decimal

    from agent_pipeline.ledger import Value

    return account.model_copy(
        update={
            "value": Value(
                amount=Decimal("1000"),
                currency="GBP",
                precision="exact",
                qualifier="exact",
                date=date(2026, 4, 30),
                source_id="db",
                quote="",
                selected_by="R3",
            )
        }
    )


def test_r6_closed_out_of_scope_is_ignored() -> None:
    account = _account("X-OLD", "Cash Account", in_scope=False, status="closed")
    state = check_account_states([account], {"X-OLD": "GBP"})["X-OLD"]
    assert state.review_items == []
    assert state.value_marker is None
    assert state.in_table is False
    assert state.withhold_value is True  # R6: a closed account is never given a value


def test_r6_closed_in_scope_is_a_blocking_conflict_not_silently_dropped() -> None:
    account = _account("X-OLD", "Cash Account", status="closed")
    state = check_account_states([account], {"X-OLD": "GBP"})["X-OLD"]
    assert state.in_table is False
    assert state.withhold_value is True  # R6: never given a value
    (item,) = state.review_items
    assert item.kind == "conflict"
    assert item.blocking is True
    assert item.refs == ["X-OLD"]
    for word in ("closed", "Cash Account", "Holloway"):
        assert word in item.detail


def test_r6_closed_in_scope_never_also_gets_a_value_marker() -> None:
    account = _account("X-OLD", "Cash Account", status="closed")
    state = check_account_states([account], {"X-OLD": "GBP"})["X-OLD"]
    assert state.value_marker is None


def test_r6_open_null_in_scope_gets_a_value_marker_and_an_open_action() -> None:
    account = _account("X-SIPP", "SIPP", platform="Brightwell")
    state = check_account_states([account], {"X-SIPP": "GBP"})["X-SIPP"]
    assert state.in_table is True
    assert state.value_marker is not None
    assert state.value_marker.key == "sipp_value"
    assert "SIPP" in state.value_marker.text
    (item,) = state.review_items
    assert item.kind == "open_action"
    assert item.blocking is False
    assert item.refs == ["X-SIPP"]


def test_r6_open_null_out_of_scope_is_review_only_no_marker() -> None:
    account = _account("X-CASH", "Cash Account", in_scope=False)
    state = check_account_states([account], {"X-CASH": "GBP"})["X-CASH"]
    assert state.value_marker is None
    assert state.in_table is False
    (item,) = state.review_items
    assert item.kind == "out_of_scope_no_value"
    assert item.blocking is False


def test_r6_an_account_with_a_value_is_untouched() -> None:
    account = _with_value(_account("X-ISA"))
    state = check_account_states([account], {"X-ISA": "GBP"})["X-ISA"]
    assert state.in_table is True
    assert state.value_marker is None
    assert state.review_items == []
    assert state.withhold_value is False


def test_r6_marker_text_carries_no_digits() -> None:
    account = _account("X-SIPP", "SIPP", platform="Brightwell")
    marker = check_account_states([account], {"X-SIPP": "GBP"})["X-SIPP"].value_marker
    assert marker is not None
    assert not any(ch.isdigit() for ch in marker.text)


def test_r6_two_same_type_null_accounts_get_distinct_marker_keys() -> None:
    a = _account("X-ISA-1")
    b = _account("X-ISA-2")
    states = check_account_states([a, b], {"X-ISA-1": "GBP", "X-ISA-2": "GBP"})
    keys = {s.value_marker.key for s in states.values() if s.value_marker}
    assert len(keys) == 2


def test_p12_non_gbp_value_is_a_marker_never_converted() -> None:
    account = _with_value(_account("X-GIA", "General Investment Account"))
    state = check_account_states([account], {"X-GIA": "EUR"})["X-GIA"]
    assert state.withhold_value is True
    assert state.value_marker is not None
    assert state.value_marker.key == "gia_currency_eur"
    assert "EUR" in state.value_marker.text
    (item,) = state.review_items
    assert item.kind == "currency"
    assert item.blocking is False
    assert "EUR" in item.detail


def test_p12_gbp_value_gets_no_currency_marker() -> None:
    account = _with_value(_account("X-ISA"))
    state = check_account_states([account], {"X-ISA": "GBP"})["X-ISA"]
    assert state.value_marker is None
    assert state.withhold_value is False


def test_p12_currency_code_is_case_insensitive() -> None:
    account = _with_value(_account("X-ISA"))
    state = check_account_states([account], {"X-ISA": "gbp"})["X-ISA"]
    assert state.value_marker is None


def test_p12_missing_currency_is_not_gbp() -> None:
    # DESIGN.md section 3.3: "a missing currency is treated as not-GBP under P12". The user
    # ruled for the spec, replacing the earlier interim test that pinned the opposite: the
    # value is withheld, the value cell is a marker and the review sheet says the currency
    # is not stated.
    account = _with_value(_account("X-ISA"))
    cases: list[dict[str, str | None]] = [{"X-ISA": None}, {}]
    for currency_by_id in cases:
        state = check_account_states([account], currency_by_id)["X-ISA"]
        assert state.value_marker is not None
        assert state.withhold_value is True
        (item,) = state.review_items
        assert item.kind == "currency"
        assert "not stated" in item.detail


def test_p12_out_of_scope_non_gbp_is_withheld_but_raises_no_marker_or_item() -> None:
    account = _with_value(_account("X-GIA", "General Investment Account", in_scope=False))
    state = check_account_states([account], {"X-GIA": "EUR"})["X-GIA"]
    assert state.value_marker is None
    assert state.review_items == []
    assert state.withhold_value is True


def test_marker_key_stem_is_never_empty() -> None:
    account = _account("X-ODD", "###", platform=None)
    marker = check_account_states([account], {"X-ODD": "GBP"})["X-ODD"].value_marker
    assert marker is not None
    assert marker.key == "account_value"


def test_r6_null_value_beats_currency_check_no_second_marker() -> None:
    # No amount exists to convert; the null-value marker alone covers the cell.
    account = _account("X-SIPP", "SIPP", platform="Brightwell")
    state = check_account_states([account], {"X-SIPP": "EUR"})["X-SIPP"]
    assert state.value_marker is not None
    assert state.value_marker.key == "sipp_value"
    assert [i.kind for i in state.review_items] == ["open_action"]


# --- The real clients' shapes -------------------------------------------------------------


def _accounts(client: str) -> tuple[list[Account], dict[str, str | None]]:
    data = read_accounts(Path(f"data/{client}/client_data_db.json"))
    accounts = resolve_ownership(data).accounts
    currency = {
        r.account_id: r.currency
        for holder in data.holders.values()
        for r in holder.accounts
        if r.account_id
    }
    return accounts, currency


def test_client_03_jeans_cash_account_out_of_scope_no_value_is_review_only() -> None:
    accounts, currency = _accounts("client_03_hard")
    states = check_account_states(accounts, currency)
    state = states["H-CASH-JE"]
    assert state.value_marker is None
    assert [i.kind for i in state.review_items] == ["out_of_scope_no_value"]


def test_client_03_no_in_scope_account_needs_a_marker_when_all_have_values() -> None:
    accounts, currency = _accounts("client_03_hard")
    in_scope = [
        a.model_copy(update={"in_scope": True})
        for a in accounts
        if a.id in {"H-ISA-R", "H-ISA-JE", "H-GIA-JF"}
    ]
    with_values = [_with_value(a) for a in in_scope]
    states = check_account_states(with_values, currency)
    assert all(s.value_marker is None and s.review_items == [] for s in states.values())


def test_client_04_caroline_cash_no_value_out_of_scope_is_review_only() -> None:
    accounts, currency = _accounts("client_04_stretch")
    state = check_account_states(accounts, currency)["M4-CASH-C"]
    assert state.value_marker is None
    assert [i.kind for i in state.review_items] == ["out_of_scope_no_value"]


def test_client_04_closed_meridian_account_out_of_scope_is_ignored() -> None:
    accounts, currency = _accounts("client_04_stretch")
    state = check_account_states(accounts, currency)["M4-OLD-C"]
    assert state.review_items == []
    assert state.value_marker is None


def test_client_04_closed_meridian_account_in_scope_would_be_a_blocking_conflict() -> None:
    accounts, currency = _accounts("client_04_stretch")
    in_scope = [
        a.model_copy(update={"in_scope": True}) if a.id == "M4-OLD-C" else a for a in accounts
    ]
    state = check_account_states(in_scope, currency)["M4-OLD-C"]
    assert [(i.kind, i.blocking) for i in state.review_items] == [("conflict", True)]
