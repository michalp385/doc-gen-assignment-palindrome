"""T12's live check (DESIGN.md section 3.2): classify every real file in client 01's folder
and confirm each lands on the role SCOPING.md's own source table says it should. Run once by
hand (`uv run pytest -m live tests/test_classify_live.py`) with explicit approval; every
other run relies on the offline, stubbed-classifier tests in test_classify.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent_pipeline.config import load_prompt, load_report_config
from agent_pipeline.llm import LLMClient, OpenAITransport
from agent_pipeline.sources.classify import LLMTextClassifier, classify

load_dotenv()

CLIENT_DIR = Path("data/client_01_clean")

_EXPECTED_ROLES = {
    "client_data_db.json": "account_data",
    "meeting_notes.docx": "meeting_record",
    "report_request.docx": "report_instruction",
    "template_spec.md": "report_spec",
    "fde_notes.md": "internal_guidance",
    "platform_market_update.docx": "general_document",
}


@pytest.mark.live
def test_client_01_files_classify_to_the_expected_roles() -> None:
    config = load_report_config(Path("config/template_config.json"))
    prompt = load_prompt(Path("config/prompts/classify.md"))
    models = json.loads(Path("config/models.json").read_text(encoding="utf-8"))
    llm = LLMClient(
        OpenAITransport(),
        stages=config.stages,
        models=models,
        cache_root=Path("cache/llm"),
        trace_path=None,
    )
    classifier = LLMTextClassifier(llm, prompt)

    result = classify(CLIENT_DIR, classifier)

    by_name = {s.path.name: s.role for s in result.sources}
    for filename, expected_role in _EXPECTED_ROLES.items():
        assert by_name.get(filename) == expected_role, (
            f"{filename}: expected {expected_role!r}, got {by_name.get(filename)!r}"
        )
