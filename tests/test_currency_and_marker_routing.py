"""A marker that reaches no section would silently vanish (tests first). `unrouted_markers`
finds them and the pipeline fails the run instead of dropping them. (The missing-currency
tests live apart: that change is waiting on approval to update one committed test.)"""

from __future__ import annotations

from agent_pipeline.ledger import Ledger, Marker
from agent_pipeline.write.plan import unrouted_markers
from agent_pipeline.write.schemas import PlanMarker, SectionPlan

# --- no marker silently vanishes -----------------------------------------------------------


def _plan(section_id: str, *keys: str) -> SectionPlan:
    return SectionPlan(
        section_id=section_id,
        markers=[PlanMarker(key=k, text="t") for k in keys],
    )


def _ledger(*markers: Marker) -> Ledger:
    return Ledger(client="c", markers=list(markers))


def _marker(key: str, section: str = "recommendations") -> Marker:
    return Marker(id="", key=key, text="t", reason="r", section=section)


def test_a_marker_in_a_plan_is_routed() -> None:
    ledger = _ledger(_marker("cgt"), _marker("advice_charge"))
    plans = [_plan("tax_implications", "cgt"), _plan("fees_charges", "advice_charge")]
    assert unrouted_markers(ledger, plans) == []


def test_a_marker_in_no_plan_is_reported() -> None:
    ledger = _ledger(_marker("cgt"), _marker("available_to_invest"))
    assert unrouted_markers(ledger, [_plan("tax_implications", "cgt")]) == ["available_to_invest"]


def test_a_table_cell_marker_needs_no_section() -> None:
    ledger = _ledger(_marker("gia_currency_eur", section="account_table"))
    assert unrouted_markers(ledger, []) == []


def test_every_unrouted_marker_is_listed_in_ledger_order() -> None:
    ledger = _ledger(_marker("b_one"), _marker("a_two"))
    assert unrouted_markers(ledger, []) == ["b_one", "a_two"]
