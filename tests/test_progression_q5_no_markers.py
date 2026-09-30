"""The judge scores Q5 (markers are specific) as 5 when a report has no markers at all, which
says nothing about marker quality. The results file records how many markers each client had, and
the progression table shows Q5 as n/a where there were none, with one line saying why."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from report_eval.results import ClientResult, ResultsFile

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "progression_script_4", ROOT / "scripts" / "progression.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROGRESSION = _load()


def _client(marker_count: int | None, q5: int) -> ClientResult:
    return ClientResult.model_validate(
        {
            "client": "alpha",
            "release_state": "draft",
            "expected_release_state": "draft",
            "gate_results": [{"gate": "G1", "passed": True}],
            "q_scores": [{"criterion": "Q5", "score": q5}],
            "marker_count": marker_count,
        }
    )


def _results(client: ClientResult) -> ResultsFile:
    return ResultsFile(
        generated_at="2026-09-30T10:00:00Z",
        commit="c",
        dirty=False,
        config_hash="h",
        clients=[client],
    )


def test_client_result_records_the_marker_count_and_old_files_still_load() -> None:
    assert _client(3, 4).marker_count == 3
    assert _client(None, 4).marker_count is None


def test_q5_is_n_a_where_the_client_had_no_markers() -> None:
    text = PROGRESSION.render(_results(_client(0, 5)), "b.json", _results(_client(4, 3)), "a.json")

    assert "| Q5 | n/a (no markers) | 3 |" in text
    last = text.rstrip().splitlines()[-1]
    assert last.startswith("n/a (no markers):") and "vacuous" in last


def test_q5_keeps_the_judge_score_when_markers_exist_or_the_count_is_unknown() -> None:
    text = PROGRESSION.render(
        _results(_client(2, 5)), "b.json", _results(_client(None, 4)), "a.json"
    )

    assert "| Q5 | 5 | 4 |" in text
