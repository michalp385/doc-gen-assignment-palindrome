"""T20/T21: the rules T19 built for client 02, pinned on clients 03 and 04's real account data
(the plan asks for tests per client): R9 (joint accounts deduplicated by account_id), R3 (a
later live-viewed value beats the statement snapshot, the loser goes to the footnote list),
P5 (a full disposal's proceeds counted at the R3-selected value) and P7 (a partial GIA sale
is a taxable disposal; a bond left alone is not a disposal at all).

These describe behaviour that already exists; they are here so a change for one client cannot
silently regress another (the plan: "a change for one client must not regress another").
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.ledger import Value
from agent_pipeline.reconcile.markers import bond_marker, cgt_marker
from agent_pipeline.reconcile.money import classify_money
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.reconcile.predicates import evaluate
from agent_pipeline.reconcile.sections import Disposal, SectionContext
from agent_pipeline.reconcile.values import select_values, superseded_values
from agent_pipeline.reconcile.wrappers import classify_wrapper
from agent_pipeline.sources.adapters.json_accounts import AccountData, read_accounts


def _data(client: str) -> AccountData:
    return read_accounts(Path(f"data/{client}/client_data_db.json"))


def _viewed(text: str, day: date) -> Value:
    parsed = parse_amount(text)
    assert parsed is not None
    return Value(
        amount=parsed.amount,
        currency=parsed.currency,
        precision=parsed.precision,
        qualifier=parsed.qualifier,
        date=day,
        source_id="meeting_notes.docx",
        quote=text,
        selected_by="R3",
    )


# --- R9 ----------------------------------------------------------------------------------


def test_r9_client_03_joint_gia_once_with_both_owners() -> None:
    result = resolve_ownership(_data("client_03_hard"))
    ids = [a.id for a in result.accounts]
    assert ids.count("H-GIA-JF") == 1
    by_id = {a.id: a for a in result.accounts}
    assert by_id["H-GIA-JF"].owners == ["Robert Fletcher", "Jean Fletcher"]
    assert result.conflicts == []
    assert result.set_aside == []


def test_r9_client_04_every_joint_account_once_with_both_owners() -> None:
    result = resolve_ownership(_data("client_04_stretch"))
    ids = [a.id for a in result.accounts]
    for joint in ("H4-GIA-HJ", "B4-GIA-J", "M4-BOND-J"):
        assert ids.count(joint) == 1
    by_id = {a.id: a for a in result.accounts}
    for joint in ("H4-GIA-HJ", "B4-GIA-J", "M4-BOND-J"):
        assert by_id[joint].owners == ["James Whitmore", "Caroline Whitmore"]
    assert result.conflicts == []


def test_r9_client_04_account_count() -> None:
    # 13 records across the two holders, three of them joint copies: 10 distinct accounts
    assert len(resolve_ownership(_data("client_04_stretch")).accounts) == 10


# --- R3 ----------------------------------------------------------------------------------


def test_r3_client_03_live_gia_figure_beats_the_march_statement() -> None:
    record = next(
        r
        for h in _data("client_03_hard").holders.values()
        for r in h.accounts
        if r.account_id == "H-GIA-JF"
    )
    viewed = [_viewed("a little over £38,000", date(2026, 5, 16))]
    selected = select_values(record.value, record.valuation_date, record.currency, viewed)
    assert selected is not None
    assert selected.amount == Decimal("38000")
    assert selected.date == date(2026, 5, 16)
    losers = superseded_values(
        record.value, record.valuation_date, record.currency, viewed, selected
    )
    assert [(v.amount, v.date) for v in losers] == [(Decimal("30000"), date(2026, 3, 10))]


def test_r3_client_04_live_holloway_gia_beats_the_february_statement() -> None:
    record = next(
        r
        for h in _data("client_04_stretch").holders.values()
        for r in h.accounts
        if r.account_id == "H4-GIA-HJ"
    )
    viewed = [_viewed("around £255,000", date(2026, 5, 20))]
    selected = select_values(record.value, record.valuation_date, record.currency, viewed)
    assert selected is not None
    assert selected.amount == Decimal("255000")
    assert selected.precision == "approximate"
    losers = superseded_values(
        record.value, record.valuation_date, record.currency, viewed, selected
    )
    assert [(v.amount, v.date) for v in losers] == [(Decimal("240000"), date(2026, 2, 28))]


def test_r3_an_account_with_no_live_figure_keeps_its_snapshot_and_nothing_is_superseded() -> None:
    record = next(
        r
        for h in _data("client_04_stretch").holders.values()
        for r in h.accounts
        if r.account_id == "B4-GIA-J"
    )
    selected = select_values(record.value, record.valuation_date, record.currency, [])
    assert selected is not None
    assert selected.amount == Decimal("95000")
    assert selected.precision == "exact"
    assert (
        superseded_values(record.value, record.valuation_date, record.currency, [], selected) == []
    )


# --- P5 ----------------------------------------------------------------------------------


def test_p5_client_03_full_gia_disposal_counts_the_live_value_as_proceeds() -> None:
    live = _viewed("a little over £38,000", date(2026, 5, 16))
    result = classify_money(live, "full", destination_known=True)
    assert result.counted is True
    assert result.amount == live


def test_p5_client_04_partial_gia_sale_adds_nothing_until_amount_and_destination_known() -> None:
    live = _viewed("around £255,000", date(2026, 5, 20))
    result = classify_money(live, "portion", destination_known=False)
    assert result.counted is False
    assert result.amount is None


# --- P7 / G5 -----------------------------------------------------------------------------


def test_p7_client_04_partial_gia_sale_is_a_taxable_disposal_with_one_cgt_marker() -> None:
    gia = classify_wrapper("General Investment Account").wrapper_class
    disposals = [Disposal(wrapper_class=gia, account_id="H4-GIA-HJ")]
    assert evaluate("taxable_disposal", SectionContext(disposals=disposals)) is True
    assert [m.key for m in cgt_marker(disposals)] == ["cgt"]
    assert bond_marker(disposals) == []


def test_p7_client_04_offshore_bond_left_as_it_is_is_no_disposal_no_marker() -> None:
    # An agreed non-action is not a disposal, so nothing reaches the section context.
    assert evaluate("taxable_disposal", SectionContext(disposals=[])) is False
    assert cgt_marker([]) == []
    assert bond_marker([]) == []


def test_p7_a_bond_encashment_would_get_its_marker_but_no_tax_section() -> None:
    bond = classify_wrapper("Offshore Investment Bond").wrapper_class
    disposals = [Disposal(wrapper_class=bond, account_id="M4-BOND-J")]
    assert evaluate("taxable_disposal", SectionContext(disposals=disposals)) is False
    assert [m.key for m in bond_marker(disposals)] == ["bond_chargeable_gain"]
    assert cgt_marker(disposals) == []
