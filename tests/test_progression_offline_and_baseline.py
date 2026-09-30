"""`scripts/progression.py`: the offline transport raises its own `CacheMiss` (so the script
catches only that, never any other assertion), and the baseline column does not claim a release
state the starter pipeline never had."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import BaseModel

from report_eval.results import ClientResult, ResultsFile

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "progression_script_2", ROOT / "scripts" / "progression.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROGRESSION = _load()


class _Out(BaseModel):
    x: int = 0


def test_the_offline_transport_raises_cache_miss_and_counts_it() -> None:
    transport = PROGRESSION._NoNetworkTransport()

    with pytest.raises(PROGRESSION.CacheMiss):
        transport.responses_parse(
            model="m", input=[], text_format=_Out, temperature=None, reasoning_effort=None
        )

    assert transport.attempts == 1


def test_a_plain_assertion_error_is_not_a_cache_miss() -> None:
    assert not issubclass(AssertionError, PROGRESSION.CacheMiss)


def _client(state: str, failing: int) -> ClientResult:
    gates = [{"gate": f"G{i}", "passed": i >= failing} for i in range(4)]
    return ClientResult.model_validate(
        {
            "client": "alpha",
            "release_state": state,
            "expected_release_state": "draft",
            "gate_results": gates,
        }
    )


def _results(*clients: ClientResult) -> ResultsFile:
    return ResultsFile(
        generated_at="2026-09-30T10:00:00Z",
        commit="c",
        dirty=False,
        config_hash="h",
        clients=list(clients),
    )


def test_baseline_release_state_is_not_shown_as_a_value_and_failed_gates_are_counted() -> None:
    before = _results(_client("draft", 3))
    after = _results(_client("draft", 0))

    text = PROGRESSION.render(before, "b.json", after, "a.json", before_has_release_states=False)

    assert (
        "| Release state (expected draft) | n/a (starter has no release states) | draft |" in text
    )
    assert "| Failed deterministic gates | 3 | 0 |" in text
