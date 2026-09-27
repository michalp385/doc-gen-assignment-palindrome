"""T11's one-off live capability check (DESIGN.md section 9, section 16 item 3): confirm,
per default model, that structured outputs, image input and `temperature=0` actually work
against the real API, and record the finding in `config/models.json`. Unlike every other
`-m live` test in this project, this one deliberately writes to a committed file as its
whole point -- that write *is* "recorded in config/models.json" (T11's Done line). Run once
by hand (`uv run pytest -m live tests/test_llm_live.py`); every other run replays the
committed recording, so this file's assertions don't need to pass every CI run, only when
someone re-verifies a model's capabilities.
"""

from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

import pytest
from dotenv import load_dotenv
from openai import BadRequestError
from pydantic import BaseModel

from agent_pipeline.config import PromptSpec, StageConfig
from agent_pipeline.llm import ImageInput, LLMClient, OpenAITransport

load_dotenv()  # same convention as generate.py: OPENAI_API_KEY from .env, not the shell

MODELS_PATH = Path("config/models.json")

# A 1x1 transparent PNG -- just enough bytes to confirm image input is accepted at all.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _ProbeAnswer(BaseModel):
    answer: str


def _probe_client(model: str, *, force_temperature: bool) -> LLMClient:
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    if force_temperature:
        models.setdefault("capabilities", {}).setdefault(model, {})["temperature_accepted"] = True
    return LLMClient(
        OpenAITransport(),
        stages={"probe": StageConfig(model=model, reasoning_effort="low")},
        models=models,
        cache_root=Path("cache/llm"),
        trace_path=None,
    )


def _record_capabilities(model: str, **flags: bool) -> None:
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    entry = models.setdefault("capabilities", {}).setdefault(model, {})
    entry.update(flags)
    entry["checked"] = date.today().isoformat()
    MODELS_PATH.write_text(json.dumps(models, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _probe(model: str) -> None:
    prompt = PromptSpec(text="Answer with a single word.", version="live-probe-v1")
    image = ImageInput(name="pixel.png", content=_TINY_PNG)

    temperature_accepted = True
    try:
        client = _probe_client(model, force_temperature=True)
        result = client.structured(
            stage="probe",
            prompt=prompt,
            inputs={"question": "What colour is a clear sky? One word."},
            schema=_ProbeAnswer,
            images=[image],
        )
    except BadRequestError:
        temperature_accepted = False
        client = _probe_client(model, force_temperature=False)
        result = client.structured(
            stage="probe",
            prompt=prompt,
            inputs={"question": "What colour is a clear sky? One word."},
            schema=_ProbeAnswer,
            images=[image],
        )

    assert isinstance(result.output, _ProbeAnswer)
    assert result.output.answer  # structured outputs worked: a real, non-empty field back

    _record_capabilities(
        model,
        structured_outputs=True,
        image_input=True,
        temperature_accepted=temperature_accepted,
    )


@pytest.mark.live
def test_luna_capabilities() -> None:
    _probe("gpt-6-luna")


@pytest.mark.live
def test_sol_capabilities() -> None:
    _probe("gpt-6-sol")
