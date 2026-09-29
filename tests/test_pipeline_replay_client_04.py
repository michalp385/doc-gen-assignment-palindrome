"""Client 04 end to end, offline, from the committed cache: a replay reaches the same decisions
and the same report text as the committed run, with no live call. A cache entry that is missing
or stale makes the transport raise, so the test fails loudly instead of reaching for an API key.

Like client 02's, it does not reproduce the committed `review.md` / `run.json` call counts (the
committed run was partly live, which a replay reports as cache hits), so `run.json` is compared
on everything except the call counts and cost. `tests/test_pipeline_replay.py` covers client 01
exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from agent_pipeline import pipeline
from agent_pipeline.config import load_report_config
from agent_pipeline.llm import RawCompletion

CLIENT = "client_04_stretch"
OUTPUTS_DIR = Path("outputs")
_COUNT_KEYS = {"total_calls", "total_cache_hits", "total_live_calls", "total_cost_usd", "stages"}


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
        raise AssertionError("client 04 tried a live call during an offline replay")


def test_client_04_replays_with_no_live_call_and_the_same_decisions(tmp_path: Path) -> None:
    config = load_report_config(Path("config/template_config.json"))

    result = pipeline.run(
        Path("data") / CLIENT, config, outputs_dir=tmp_path, transport=_NoNetworkTransport()
    )

    assert result.release_state == "draft"
    assert result.run_summary.total_live_calls == 0
    assert result.run_summary.total_cache_hits == result.run_summary.total_calls

    for suffix in (".md", ".ledger.json"):
        committed = (OUTPUTS_DIR / f"{CLIENT}{suffix}").read_text(encoding="utf-8")
        replayed = (tmp_path / f"{CLIENT}{suffix}").read_text(encoding="utf-8")
        assert replayed == committed, f"{CLIENT}{suffix} differs from the committed one"

    def decisions(path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if k not in _COUNT_KEYS}

    assert decisions(tmp_path / f"{CLIENT}.run.json") == decisions(
        OUTPUTS_DIR / f"{CLIENT}.run.json"
    )
