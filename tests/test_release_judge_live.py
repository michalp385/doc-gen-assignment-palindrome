"""T15's live check (DESIGN.md section 8.2, section 10.7): run the release judge for real
against client 01's reference bundle, and confirm every gate passes and the report ends up
a "draft". Run once by hand (`uv run pytest -m live tests/test_release_judge_live.py`) with
explicit approval; every other run relies on the offline, scripted-judge tests in
test_gates_judge.py.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent_pipeline.config import load_prompt, load_report_config
from agent_pipeline.gates.judge import LLMJudgeModel, release_judge
from agent_pipeline.gates.release import decide_release
from agent_pipeline.ledger import Action
from agent_pipeline.llm import LLMClient, OpenAITransport
from agent_pipeline.sources.adapters.docx import read_docx
from report_eval.reference import build_reference_bundle

load_dotenv()

CLIENT_DIR = Path("data/client_01_clean")


def _llm() -> LLMClient:
    config = load_report_config(Path("config/template_config.json"))
    models = json.loads(Path("config/models.json").read_text(encoding="utf-8"))
    return LLMClient(
        OpenAITransport(), stages=config.stages, models=models, cache_root=Path("cache/llm")
    )


@pytest.mark.live
def test_client_01_reference_bundle_passes_the_release_judge() -> None:
    bundle, _ = build_reference_bundle("client_01_clean")
    # The reference bundle (T9) carries no `actions` -- it only ever needed to exercise the
    # report-level deterministic gates. Add the one agreed action client 01's recommendation
    # text actually describes, so this also exercises G8's coverage/mapping check for real.
    ledger = bundle.ledger.model_copy(
        update={
            "actions": [
                Action(
                    id="a1",
                    description="move £20,000 from the cash account into the ISA",
                    kind="action",
                )
            ]
        }
    )
    bundle = dataclasses.replace(bundle, ledger=ledger)

    sources = {
        "meeting_notes.docx": read_docx(CLIENT_DIR / "meeting_notes.docx"),
        "report_request.docx": read_docx(CLIENT_DIR / "report_request.docx"),
    }
    prompt = load_prompt(Path("config/prompts/release_judge.md"))
    model = LLMJudgeModel(_llm(), prompt)

    results = release_judge(bundle, ledger, sources, model)
    failing = [r for r in results if not r.passed]
    assert failing == [], f"judge found: {failing}"
    assert decide_release(results) == "draft"
