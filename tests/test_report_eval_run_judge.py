"""T17: the `--judge` path of `report_eval.run`, and `_config_hash`'s determinism.

Split from `test_report_eval_run.py` because these need the eval_judge (Sol) cache entries
from the live batch this task ran -- that cache is now committed, so this replays at $0 like
everything else here, but it's kept separate rather than editing the already-committed test
file (CLAUDE.md: a committed test is the spec; additive coverage for a fix goes in a new file
when the guard flags the original)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from agent_pipeline.config import load_report_config
from agent_pipeline.llm import RawCompletion
from report_eval.expected import load_expected
from report_eval.run import _config_hash, score_client

MODELS = {
    "capabilities": {
        "gpt-6-luna": {"temperature_accepted": False},
        "gpt-6-sol": {"temperature_accepted": False},
    },
    "prices_per_1m_tokens": {
        "gpt-6-luna": {"input": 0.1, "output": 0.5},
        "gpt-6-sol": {"input": 2.0, "output": 10.0},
    },
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


def _score_with_judge(client: str, outputs_dir: Path, run_id: str):
    config = load_report_config(Path("config/template_config.json"))
    return score_client(
        client,
        expected=load_expected(client),
        outputs_dir=outputs_dir,
        data_dir=Path("data"),
        config=config,
        models=MODELS,
        cache_root=Path("cache/llm"),
        fresh=False,
        judge=True,
        run_id=run_id,
        transport=_NoNetworkTransport(),
    )


def test_client_01_real_output_scores_q1_to_q6_entirely_from_cache() -> None:
    result = _score_with_judge("client_01_clean", Path("outputs"), "test-judge-real")

    assert result.live_calls == 0
    criteria = {s.criterion for s in result.q_scores}
    assert criteria == {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}
    assert all(1 <= s.score <= 5 for s in result.q_scores)
    # Q6 is derived from G14, never a judge call -- it always has no evidence quotes.
    q6 = next(s for s in result.q_scores if s.criterion == "Q6")
    assert q6.evidence == []


def test_every_baseline_client_scores_q1_to_q6_entirely_from_cache() -> None:
    for client in (
        "client_01_clean",
        "client_02_medium",
        "client_03_hard",
        "client_04_stretch",
    ):
        result = _score_with_judge(client, Path("outputs/baseline"), f"test-judge-{client}")
        assert result.live_calls == 0
        assert {s.criterion for s in result.q_scores} == {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}


def test_config_hash_is_stable_across_separate_calls() -> None:
    path = Path("config/template_config.json")
    assert _config_hash(path) == _config_hash(path)


def test_config_hash_changes_when_the_file_content_changes(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text('{"x": 1}', encoding="utf-8")
    b.write_text('{"x": 2}', encoding="utf-8")
    assert _config_hash(a) != _config_hash(b)
