"""T15: `decide_release` -- exactly two post-gates states (DESIGN.md section 8.3)."""

from __future__ import annotations

from agent_pipeline.gates.deterministic import GateResult
from agent_pipeline.gates.release import decide_release


def test_all_gates_passing_is_a_draft():
    results = [GateResult("G1", True), GateResult("G2", True)]
    assert decide_release(results) == "draft"


def test_any_gate_failing_is_failed():
    results = [GateResult("G1", True), GateResult("G4", False, "paraphrase found")]
    assert decide_release(results) == "failed"


def test_empty_gate_results_is_a_draft():
    assert decide_release([]) == "draft"
