"""T13's live check (DESIGN.md section 4, section 10.7): extract client 01's meeting note
and report instruction for real, and confirm the result matches its expected-facts fixture.
Run once by hand (`uv run pytest -m live tests/test_extract_live.py`) with explicit
approval; every other run relies on the offline, scripted-model tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent_pipeline.config import load_prompt, load_report_config
from agent_pipeline.extract.instruction import LLMInstructionModel, extract_instruction
from agent_pipeline.extract.meeting import LLMMeetingModel, extract_meeting
from agent_pipeline.llm import LLMClient, OpenAITransport
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.json_accounts import read_accounts

load_dotenv()

CLIENT_DIR = Path("data/client_01_clean")


def _llm(trace_path: Path | None = None) -> LLMClient:
    config = load_report_config(Path("config/template_config.json"))
    models = json.loads(Path("config/models.json").read_text(encoding="utf-8"))
    return LLMClient(
        OpenAITransport(),
        stages=config.stages,
        models=models,
        cache_root=Path("cache/llm"),
        trace_path=trace_path,
    )


@pytest.mark.live
def test_client_01_meeting_extraction_matches_its_fixture() -> None:
    doc = read_docx(CLIENT_DIR / "meeting_notes.docx")
    prompt = load_prompt(Path("config/prompts/extract_meeting.md"))
    model = LLMMeetingModel(_llm(), prompt)

    result = extract_meeting(doc, model)

    assert result.value_observations == []
    assert result.money_items == []
    assert result.disposals == []
    assert result.dropped == []

    expected = json.loads((Path("eval/expected/client_01_clean.json")).read_text(encoding="utf-8"))[
        "extraction"
    ]["open_actions"]
    assert len(result.open_actions) == len(expected)
    for actual, exp in zip(result.open_actions, expected, strict=True):
        assert actual.blocking == exp["blocking"]
        assert (
            exp["evidence_quote"] in actual.text.text or actual.text.text in exp["evidence_quote"]
        )


@pytest.mark.live
def test_client_01_instruction_extraction_matches_its_fixture() -> None:
    doc = read_docx(CLIENT_DIR / "report_request.docx")
    label_prompt = load_prompt(Path("config/prompts/extract_instruction.md"))
    scope_prompt = load_prompt(Path("config/prompts/scope_mapping.md"))
    model = LLMInstructionModel(_llm(), label_prompt, scope_prompt)

    account_data = read_accounts(CLIENT_DIR / "client_data_db.json")
    accounts = resolve_ownership(account_data).accounts

    result = extract_instruction(doc, accounts, model)

    assert all(f.canonical is not None for f in result.fields)
    assert all(not f.is_tbc for f in result.fields)
    risk_profile = next(f for f in result.fields if f.canonical == "risk_profile")
    assert risk_profile.value == "4 (moderate)"

    assert result.scope_mapping is not None
    assert result.scope_mapping.candidate_account_ids == ["H-ISA-01"]
