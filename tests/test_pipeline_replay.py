"""T16: client 01 end to end, offline, from the committed cache (S2/S4) -- reproducing
the committed `outputs/client_01_clean.*` exactly. No network call is possible: the
transport raises if `pipeline.run` ever tries to make one, so a cache miss fails loudly
instead of silently reaching for a real API key.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from agent_pipeline import pipeline
from agent_pipeline.config import load_report_config
from agent_pipeline.llm import RawCompletion

CLIENT_DIR = Path("data/client_01_clean")
OUTPUTS_DIR = Path("outputs")


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
            "pipeline.run tried to make a live call during an offline replay -- "
            "a cache entry is missing or stale"
        )


def test_client_01_replays_from_cache_and_matches_committed_outputs(tmp_path: Path) -> None:
    config = load_report_config(Path("config/template_config.json"))

    result = pipeline.run(CLIENT_DIR, config, outputs_dir=tmp_path, transport=_NoNetworkTransport())

    assert result.release_state == "draft"
    assert result.run_summary.total_live_calls == 0
    assert result.run_summary.total_cache_hits == result.run_summary.total_calls

    for suffix in (".md", ".review.md", ".ledger.json", ".run.json"):
        committed = (OUTPUTS_DIR / f"client_01_clean{suffix}").read_text(encoding="utf-8")
        replayed = (tmp_path / f"client_01_clean{suffix}").read_text(encoding="utf-8")
        assert replayed == committed, f"client_01_clean{suffix} does not match the committed one"
