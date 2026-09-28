"""T17: `report_eval.run` scores client 01's real committed output and the baseline's
committed output entirely from the committed cache -- no network call is possible (same
no-network-transport discipline as `tests/test_pipeline_replay.py`). This exercises the
deterministic-gates-only path (`--judge` needs a live Sol run, covered separately once that's
been run and its cache committed).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from agent_pipeline.config import load_report_config
from agent_pipeline.llm import RawCompletion
from report_eval.expected import ExpectedFacts, Release, load_expected
from report_eval.run import score_client

MODELS = {
    "capabilities": {"gpt-6-luna": {"temperature_accepted": False}},
    "prices_per_1m_tokens": {"gpt-6-luna": {"input": 0.1, "output": 0.5}},
}


class _NoNetworkTransport:
    def responses_parse(
        self,
        *,
        model: str,
        input: list[dict],
        text_format: type[BaseModel],
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> RawCompletion:
        raise AssertionError(
            "report_eval.run tried to make a live call during an offline replay -- "
            "a cache entry is missing or stale"
        )


def _score(client: str, outputs_dir: Path, run_id: str, *, data_dir: Path = Path("data")):
    config = load_report_config(Path("config/template_config.json"))
    return score_client(
        client,
        expected=load_expected(client),
        outputs_dir=outputs_dir,
        data_dir=data_dir,
        config=config,
        models=MODELS,
        cache_root=Path("cache/llm"),
        fresh=False,
        judge=False,
        run_id=run_id,
        transport=_NoNetworkTransport(),
    )


def test_client_01_scores_from_committed_output_and_cache_with_no_live_calls() -> None:
    result = _score("client_01_clean", Path("outputs"), "test-real")

    assert result.client == "client_01_clean"
    assert result.release_state == "draft"
    assert result.expected_release_state == "draft"
    assert result.live_calls == 0
    assert result.cache_hits > 0

    by_gate = {g.gate: g for g in result.gate_results}
    assert by_gate["G1"].passed is True
    assert by_gate["G6"].passed is True
    # extraction scoring ran against the client's real extraction, from cache
    assert result.extraction_score is not None
    open_actions = next(
        c for c in result.extraction_score.categories if c.category == "open_actions"
    )
    assert open_actions.expected_count == 1


def test_baseline_client_01_scores_with_no_ledger_so_g14_and_g15_fail_by_construction() -> None:
    # client_02-04's classify() calls aren't cached yet (they've never been scored before --
    # that first happens in the live --judge batch), so only client 01's baseline is covered
    # offline here; the rest are exercised once that batch's cache is committed.
    result = _score("client_01_clean", Path("outputs/baseline"), "test-baseline")

    assert result.release_state == "draft"  # the baseline stub still issued something
    by_gate = {g.gate: g for g in result.gate_results}
    assert by_gate["G14"].passed is False  # no ledger -> no markers at all
    assert by_gate["G15"].passed is False  # no ledger -> no review sheet at all


def test_a_client_whose_sources_fail_to_classify_drops_g10_with_a_note_not_a_false_pass(
    tmp_path: Path,
) -> None:
    # An empty client folder classifies to nothing at all -- classify() raises
    # ClassificationStopError before any LLM call is even attempted (no account_data found),
    # so _NoNetworkTransport is never actually exercised here; the point is that G10 must
    # never come back "passed" off text that was never read (verifier checkpoint, T17).
    data_dir = tmp_path / "data"
    (data_dir / "empty_client").mkdir(parents=True)
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    (outputs_dir / "empty_client.md").write_text(
        "# Investment Advice Report\n\n## Introduction\n\nHello.\n", encoding="utf-8"
    )
    expected = ExpectedFacts(
        client="empty_client",
        meeting_date=None,
        risk_profile="",
        initial_charge="",
        release=Release(state="draft"),
    )
    config = load_report_config(Path("config/template_config.json"))

    result = score_client(
        "empty_client",
        expected=expected,
        outputs_dir=outputs_dir,
        data_dir=data_dir,
        config=config,
        models=MODELS,
        cache_root=Path("cache/llm"),
        fresh=False,
        judge=False,
        run_id="test-classification-failure",
        transport=_NoNetworkTransport(),
    )

    assert "G10" not in {g.gate for g in result.gate_results}
    assert any("G10 not checked" in note for note in result.notes)
