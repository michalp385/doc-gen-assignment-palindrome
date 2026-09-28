"""Each synthetic scenario's expected facts must be consistent with the deterministic gates:
render the scenario's known-correct report from them (the reference-bundle stub writer) and
every gate must pass. A scenario whose expected facts contradicted a gate (a figure the gate
would reject, a marker with no review row, a name missing from the report) would make the
later live synthetic run fail for a reason that has nothing to do with the pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import report_eval.reference as reference
from agent_pipeline.gates.deterministic import run_gates
from report_eval.synth.scenario import expected_facts, required_phrases, sample_scenario
from report_eval.synth.writers import write_client
from report_eval.truth import ExpectedTruth

SEEDS = list(range(1, 41))


@pytest.mark.parametrize("seed", SEEDS)
def test_the_reference_report_for_a_synthetic_scenario_passes_every_gate(
    seed: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = sample_scenario(seed)
    note = "\n\n".join(p.text for p in required_phrases(scenario))
    write_client(scenario, note, tmp_path / scenario.client_id)
    monkeypatch.setattr(reference, "DATA_ROOT", tmp_path)

    facts = expected_facts(scenario)
    bundle = reference._build_from_expected(facts)  # noqa: SLF001  # the generic stub writer
    results = run_gates(bundle, ExpectedTruth(facts))

    assert [(r.gate, r.detail) for r in results if not r.passed] == []
