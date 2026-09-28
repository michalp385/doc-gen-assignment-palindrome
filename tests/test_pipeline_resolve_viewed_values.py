"""T19: `_resolve_viewed_values` must date a live-viewed meeting figure with the meeting's
own date, not `None` -- `select_values`' "latest date wins" comparison treats a `None` date
as `date.min`, so an undated viewed value always loses to the account data's own dated
snapshot, whatever that date is. No client before client 02 had a live-viewed value that
needed to actually win against a snapshot, so this real bug went uncaught until a live run
against client 02 showed the GIA's table cell stuck at its stale statement value (T19
checkpoint)."""

from __future__ import annotations

from datetime import date

from agent_pipeline.extract.schemas import LabelEvidence, Quote
from agent_pipeline.extract.schemas import ValueObservation as ExtractedValueObservation
from agent_pipeline.ledger import Account
from agent_pipeline.pipeline import _resolve_viewed_values

_MEETING_DATE = date(2026, 5, 14)
_EVIDENCE = LabelEvidence(paragraph_id="p5", text="pulled the account up live")


def _account() -> Account:
    return Account(
        id="H-GIA-J",
        owners=["David Clarke", "Susan Clarke"],
        type="General Investment Account",
        platform="Holloway",
    )


def _observation() -> ExtractedValueObservation:
    return ExtractedValueObservation(
        account_reference="jointly-held General Investment Account on the Holloway platform",
        amount=Quote(paragraph_id="p5", text="a little over £45,000"),
        basis="viewed_in_meeting",
        basis_evidence=_EVIDENCE,
    )


def test_a_viewed_value_is_dated_with_the_meeting_date_not_none() -> None:
    result = _resolve_viewed_values(
        [_observation()], [_account()], "meeting_notes.docx", _MEETING_DATE
    )
    assert result["H-GIA-J"][0].date == _MEETING_DATE


def test_a_recalled_value_is_never_selected_as_viewed() -> None:
    recalled = _observation().model_copy(update={"basis": "recalled"})
    result = _resolve_viewed_values([recalled], [_account()], "meeting_notes.docx", _MEETING_DATE)
    assert result == {}


def test_no_meeting_date_leaves_the_value_undated_not_a_crash() -> None:
    result = _resolve_viewed_values([_observation()], [_account()], "meeting_notes.docx", None)
    assert result["H-GIA-J"][0].date is None
