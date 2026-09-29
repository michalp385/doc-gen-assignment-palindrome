"""P11: a request field marked "TBC" is a marker, never a default (tests first; case 13).

SCOPING P11: an instruction field that is missing or reads TBC is an adviser-review marker. Two
request fields reach the report through computed placeholders (the initial charge and the agreed
risk profile), so a TBC one becomes a marker placed in that slot, worded so the report shows the
field was TBC. A field that is simply absent from the request stays "not stated".
"""

from __future__ import annotations

from agent_pipeline.extract.schemas import RequestField
from agent_pipeline.ledger import Ledger, Marker
from agent_pipeline.pipeline import _computed_placeholder
from agent_pipeline.reconcile.markers import tbc_field_markers
from agent_pipeline.write.plan import unrouted_markers


def _field(canonical: str, value: str, tbc: bool) -> RequestField:
    return RequestField(
        canonical=canonical,  # type: ignore[arg-type]  # the test passes the literal by name
        label_as_written=canonical.replace("_", " ").title(),
        value=value,
        is_tbc=tbc,
    )


def test_a_tbc_initial_charge_becomes_a_marker_that_says_tbc() -> None:
    [marker] = tbc_field_markers({"initial_charge": _field("initial_charge", "TBC", True)})
    assert marker.key == "initial_charge_tbc" and marker.section == "computed_slot"
    assert "TBC" in marker.text


def test_a_tbc_risk_profile_becomes_a_marker_too() -> None:
    [marker] = tbc_field_markers({"risk_profile": _field("risk_profile", "TBC", True)})
    assert marker.key == "risk_profile_tbc" and "TBC" in marker.text


def test_a_stated_or_absent_field_makes_no_marker() -> None:
    assert tbc_field_markers({"initial_charge": _field("initial_charge", "0.5%", False)}) == []
    assert tbc_field_markers({}) == []


def test_other_tbc_fields_are_not_computed_slots_and_make_no_marker_here() -> None:
    assert tbc_field_markers({"adviser": _field("adviser", "TBC", True)}) == []


def _ledger_with(marker: Marker | None, initial_charge: str | None = None) -> Ledger:
    ledger = Ledger(client="c", initial_charge=initial_charge)
    if marker is not None:
        ledger = ledger.model_copy(update={"markers": [marker.model_copy(update={"id": "#3"})]})
    return ledger


def test_the_computed_slot_carries_the_marker_when_the_field_is_tbc() -> None:
    [marker] = tbc_field_markers({"initial_charge": _field("initial_charge", "TBC", True)})
    text = _computed_placeholder("initial_charge", _ledger_with(marker))
    assert text.startswith("[ADVISER TO CONFIRM #3:") and "TBC" in text


def test_the_computed_slot_is_unchanged_when_the_field_is_stated_or_absent() -> None:
    assert _computed_placeholder("initial_charge", _ledger_with(None, "0.5%")) == "0.5%"
    assert _computed_placeholder("initial_charge", _ledger_with(None)) == "not stated"


def test_a_computed_slot_marker_is_not_reported_as_unrouted() -> None:
    [marker] = tbc_field_markers({"initial_charge": _field("initial_charge", "TBC", True)})
    assert unrouted_markers(_ledger_with(marker), []) == []
