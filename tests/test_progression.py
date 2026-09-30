"""`scripts/progression.py`: the before/after table. Every figure in it is read from the two
results files, so these tests build results files and check the table says what they say."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from report_eval.results import ClientResult, GateOutcome, QCriterionScore, ResultsFile

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "progression_script", ROOT / "scripts" / "progression.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROGRESSION = _load()


def _gates(failing: set[str]) -> list[GateOutcome]:
    return [GateOutcome(gate=g, passed=g not in failing) for g in ("G1", "G2", "G3", "G14")]


def _client(
    name: str, state: str, failing: set[str], q: dict[str, int] | None = None
) -> ClientResult:
    return ClientResult.model_validate(
        {
            "client": name,
            "release_state": state,
            "expected_release_state": "draft",
            "gate_results": [g.model_dump() for g in _gates(failing)],
            "q_scores": [
                QCriterionScore.model_validate({"criterion": k, "score": v}).model_dump()
                for k, v in (q or {}).items()
            ],
        }
    )


def _results(commit: str, *clients: ClientResult) -> ResultsFile:
    return ResultsFile(
        generated_at="2026-09-30T10:00:00Z",
        commit=commit,
        dirty=False,
        config_hash="h",
        clients=list(clients),
    )


def test_one_table_per_client_with_release_state_and_gates_before_and_after() -> None:
    before = _results("aaa1111", _client("alpha", "failed", {"G2", "G14"}))
    after = _results("bbb2222", _client("alpha", "draft", set()))

    text = PROGRESSION.render(before, "before.json", after, "after.json")

    assert "### alpha" in text
    assert "| Release state (expected draft) | failed | draft |" in text
    assert "| Deterministic gates passed | 2 of 4 | 4 of 4 |" in text
    assert "| Failing gates | G2, G14 | none |" in text
    assert "`before.json`" in text and "`after.json`" in text
    assert "aaa1111" in text and "bbb2222" in text


def test_judge_scores_show_n_a_where_a_side_has_none() -> None:
    before = _results("aaa1111", _client("alpha", "failed", set()))
    after = _results("bbb2222", _client("alpha", "draft", set(), {"Q1": 3, "Q6": 5}))

    text = PROGRESSION.render(before, "b.json", after, "a.json")

    assert "| Q1 | n/a | 3 |" in text
    assert "| Q6 | n/a | 5 |" in text
    assert "| Q2 |" not in text


def test_a_client_on_one_side_only_is_listed_with_n_a() -> None:
    before = _results("aaa1111")
    after = _results("bbb2222", _client("alpha", "draft", set()))

    text = PROGRESSION.render(before, "b.json", after, "a.json")

    assert "| Release state (expected draft) | n/a | draft |" in text
