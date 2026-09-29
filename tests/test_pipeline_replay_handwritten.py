"""The 20 hand-written cases end to end, offline, from the committed cache (DESIGN 10.6).

Each case replays with a transport that raises on any live call, so a missing or stale cache
entry fails loudly instead of reaching for an API key, and its report (or failure file) and
ledger must equal the committed ones. This is what makes the hand-written results file a claim a
clean checkout can check: the cases, their cache and their outputs are committed together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent_pipeline import pipeline
from agent_pipeline.config import load_report_config
from agent_pipeline.llm import RawCompletion

CASES_DIR = Path("data/synthetic/handwritten")
OUTPUTS_DIR = Path("outputs/handwritten")
CASES = [f"case_{n:02d}" for n in range(1, 21)]


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
        raise AssertionError("a hand-written case tried a live call during an offline replay")


@pytest.mark.parametrize("case", CASES)
def test_case_replays_from_the_committed_cache_and_matches_the_committed_outputs(
    case: str, tmp_path: Path
) -> None:
    config = load_report_config(Path("config/template_config.json"))

    result = pipeline.run(
        CASES_DIR / case, config, outputs_dir=tmp_path, transport=_NoNetworkTransport()
    )

    committed_state = json.loads((OUTPUTS_DIR / f"{case}.run.json").read_text(encoding="utf-8"))
    assert result.release_state == committed_state["release_state"]
    assert result.run_summary.total_live_calls == 0
    for suffix in (".md", ".failed.md", ".ledger.json"):
        committed = OUTPUTS_DIR / f"{case}{suffix}"
        if committed.exists():
            replayed = (tmp_path / f"{case}{suffix}").read_text(encoding="utf-8")
            assert replayed == committed.read_text(encoding="utf-8"), f"{case}{suffix} differs"
