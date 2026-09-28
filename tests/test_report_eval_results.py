"""T17: the results-file schema round-trips, an unknown key fails loudly (same convention as
`report_eval.expected`), and the derived per-client/per-group figures match DESIGN.md section
10.4's definitions."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from report_eval.results import (
    ClientResult,
    GateOutcome,
    GroupSummary,
    InvestigationScore,
    QCriterionScore,
    ReleaseState,
    ResultsFile,
    git_commit_info,
    results_filename,
    summarize_group,
    write_results_file,
)


def _client(
    client: str = "client_01_clean",
    *,
    release_state: ReleaseState = "draft",
    expected_release_state: ReleaseState = "draft",
    gates: list[GateOutcome] | None = None,
    cost_usd: str = "0.05",
) -> ClientResult:
    return ClientResult(
        client=client,
        release_state=release_state,
        expected_release_state=expected_release_state,
        gate_results=gates or [GateOutcome(gate="G1", passed=True)],
        cost_usd=cost_usd,
    )


def test_round_trips_through_json() -> None:
    results = ResultsFile(
        generated_at="2026-09-28T12:00:00Z",
        commit="abc1234",
        dirty=False,
        config_hash="deadbeef",
        prompt_versions={"eval_judge": "v1"},
        stage_models={"eval_judge": "gpt-6-sol"},
        clients=[_client()],
        total_cost_usd="0.05",
    )
    again = ResultsFile.model_validate_json(results.model_dump_json())
    assert again == results


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        ClientResult.model_validate(
            {
                "client": "x",
                "release_state": "draft",
                "expected_release_state": "draft",
                "not_a_real_field": 1,
            }
        )


def test_q_score_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        QCriterionScore(criterion="Q1", score=6)


def test_client_result_flags() -> None:
    matches = _client(release_state="draft", expected_release_state="draft")
    mismatch = _client(release_state="failed", expected_release_state="draft")
    wrongly_issued = _client(release_state="draft", expected_release_state="failed")

    assert matches.issued and matches.release_state_matches and not matches.wrongly_issued
    assert not mismatch.issued and not mismatch.release_state_matches
    assert wrongly_issued.issued and wrongly_issued.wrongly_issued
    assert not wrongly_issued.release_state_matches


def test_client_result_hard_gates_passed() -> None:
    passing = _client(
        gates=[GateOutcome(gate="G1", passed=True), GateOutcome(gate="G2", passed=True)]
    )
    failing = _client(
        gates=[GateOutcome(gate="G1", passed=True), GateOutcome(gate="G2", passed=False)]
    )
    assert passing.hard_gates_passed
    assert not failing.hard_gates_passed


def test_summarize_group_computes_rates_and_cost_per_report() -> None:
    clients = [
        _client("a", release_state="draft", expected_release_state="draft", cost_usd="0.10"),
        _client("b", release_state="failed", expected_release_state="draft", cost_usd="0.20"),
        _client("c", release_state="draft", expected_release_state="failed", cost_usd="0.30"),
    ]
    summary = summarize_group("real", clients)
    assert summary.client_count == 3
    assert summary.issued_rate == pytest.approx(2 / 3)  # a and c issued, b didn't
    assert summary.release_state_match_rate == pytest.approx(1 / 3)  # only a matches
    assert summary.wrongly_issued == 1  # c
    assert summary.cost_per_report_usd == "0.2000"


def test_summarize_group_empty_is_zero_not_a_crash() -> None:
    summary = summarize_group("empty", [])
    assert summary.client_count == 0
    assert summary.issued_rate == 0.0
    assert summary.release_state_match_rate == 0.0
    assert summary.cost_per_report_usd == "0.0000"


def test_investigation_score_defaults_to_zero_not_omitted() -> None:
    score = InvestigationScore()
    assert score.accepted_and_wrong == 0
    dumped = score.model_dump()
    assert "accepted_and_wrong" in dumped


def test_group_summary_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GroupSummary.model_validate(
            {
                "group": "g",
                "client_count": 0,
                "issued_rate": 0.0,
                "release_state_match_rate": 0.0,
                "wrongly_issued": 0,
                "accepted_and_wrong": 0,
                "cost_per_report_usd": "0",
                "extra": 1,
            }
        )


def test_results_filename_format() -> None:
    generated_at = dt.datetime(2026, 9, 28, 12, 0, 0, tzinfo=dt.timezone.utc)
    assert results_filename(generated_at, "abc1234", dirty=False) == "20260928T120000Z_abc1234.json"
    assert (
        results_filename(generated_at, "abc1234", dirty=True)
        == "20260928T120000Z_abc1234-dirty.json"
    )


def test_write_results_file_writes_under_root(tmp_path) -> None:
    results = ResultsFile(
        generated_at="2026-09-28T12:00:00Z",
        commit="abc1234",
        dirty=False,
        config_hash="deadbeef",
        clients=[_client()],
    )
    path = write_results_file(results, root=tmp_path)
    assert path == tmp_path / "20260928T120000Z_abc1234.json"
    assert path.exists()
    assert ResultsFile.model_validate_json(path.read_text(encoding="utf-8")) == results


def test_git_commit_info_returns_short_sha_and_dirty_flag() -> None:
    sha, dirty = git_commit_info()
    assert len(sha) >= 7 or sha == "unknown"
    assert isinstance(dirty, bool)


def test_git_commit_info_degrades_when_not_a_repo(tmp_path) -> None:
    sha, dirty = git_commit_info(root=tmp_path)
    assert sha == "unknown"
    assert dirty is True
