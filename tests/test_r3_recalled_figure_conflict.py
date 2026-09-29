"""R3: a recalled figure that disagrees with the selected value is a conflict item (tests first;
hand-written case 02).

SCOPING R3: a figure the client recalls is not one the adviser saw, so it never selects a value; it
"only confirms or conflicts". When it differs from the value that was selected, the adviser
should see both, so a non-blocking conflict names the recalled figure and the selected one. A
recalled figure that agrees, a viewed figure (which competes under R3 instead), an unmatched
account and an account with no selected value raise nothing.
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.extract.schemas import LabelEvidence, Quote, ValueObservation
from agent_pipeline.ledger import Account, Value
from agent_pipeline.pipeline import _recalled_figure_conflicts


def _account(amount: str | None = "45000") -> Account:
    value = (
        Value(
            amount=Decimal(amount),
            currency="GBP",
            precision="exact",
            qualifier="exact",
            date=None,
            source_id="client_data_db.json",
            quote="",
            selected_by="R3",
        )
        if amount is not None
        else None
    )
    return Account(
        id="A-ISA",
        type="Stocks & Shares ISA",
        owners=["George Ashworth"],
        platform="Holloway",
        in_scope=True,
        value=value,
    )


def _observation(text: str = "around £42,000", basis: str = "recalled") -> ValueObservation:
    return ValueObservation(
        account_reference="his Stocks & Shares ISA",
        amount=Quote(paragraph_id="p3", text=text),
        basis=basis,  # type: ignore[arg-type]  # the test passes the literal by name
        basis_evidence=LabelEvidence(paragraph_id="p3", text="he recalled"),
    )


def test_a_differing_recalled_figure_is_a_non_blocking_conflict_naming_both() -> None:
    [item] = _recalled_figure_conflicts([_observation()], [_account()])
    assert item.kind == "conflict" and not item.blocking and item.refs == ["A-ISA"]
    assert "£42,000" in item.detail and "recalled" in item.detail and "£45,000" in item.detail


def test_a_recalled_figure_that_agrees_raises_nothing() -> None:
    assert _recalled_figure_conflicts([_observation("£45,000")], [_account()]) == []


def test_a_viewed_figure_is_not_this_rules_concern() -> None:
    assert _recalled_figure_conflicts([_observation(basis="viewed_in_meeting")], [_account()]) == []


def test_no_selected_value_or_no_single_match_raises_nothing() -> None:
    assert _recalled_figure_conflicts([_observation()], [_account(None)]) == []
    other = _account().model_copy(update={"type": "SIPP"})
    assert _recalled_figure_conflicts([_observation()], [other]) == []


def test_an_unparseable_recalled_figure_raises_nothing() -> None:
    assert _recalled_figure_conflicts([_observation("a fair bit")], [_account()]) == []
