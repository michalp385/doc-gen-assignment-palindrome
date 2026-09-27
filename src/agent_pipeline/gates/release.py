"""The release decision (DESIGN.md section 8.3): exactly two post-gates states. A third
state -- the pre-stage-3 input stop, with no draft, no ledger and no gate results at all --
never reaches this function; `assemble.write_input_stop` handles that path directly.
"""

from __future__ import annotations

from typing import Literal

from agent_pipeline.gates.deterministic import GateResult

ReleaseState = Literal["draft", "failed"]


def decide_release(gate_results: list[GateResult]) -> ReleaseState:
    return "draft" if all(r.passed for r in gate_results) else "failed"
