"""The LLM client (T11): cache key stability, retries, schema re-ask, cost, tracing.
Offline only -- a FakeTransport stands in for the real openai SDK call, never network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel

from agent_pipeline.cache import Usage
from agent_pipeline.config import PromptSpec, StageConfig
from agent_pipeline.llm import (
    EmptyOutputError,
    LLMClient,
    RawCompletion,
    RunawayCostError,
    SchemaValidationError,
    TransientAPIError,
    compute_cache_key,
)


class Answer(BaseModel):
    text: str


@dataclass
class FakeTransport:
    responses: list[RawCompletion | Exception]
    calls: list[dict] = field(default_factory=list)

    def responses_parse(
        self,
        *,
        model: str,
        input: list[dict],
        text_format: type[BaseModel],
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> RawCompletion:
        self.calls.append(
            {
                "model": model,
                "input": input,
                "text_format": text_format,
                "temperature": temperature,
                "reasoning_effort": reasoning_effort,
            }
        )
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _stage_config(
    model: str = "test-model",
    reasoning_effort: Literal["none", "low", "medium", "high"] = "low",
) -> StageConfig:
    return StageConfig(model=model, reasoning_effort=reasoning_effort)


def _models() -> dict:
    return {
        "prices_per_1m_tokens": {"test-model": {"input": 1.0, "output": 2.0}},
        "capabilities": {},
    }


def _prompt(text: str = "Answer the question.") -> PromptSpec:
    return PromptSpec(text=text, version="v1")


def _ok(text: str = "hello", input_tokens: int = 100, output_tokens: int = 10) -> RawCompletion:
    return RawCompletion(
        parsed=Answer(text=text),
        refusal=None,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _client(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    fresh: bool = False,
    sleeps: list[float] | None = None,
    runaway_ceiling_usd: Decimal = Decimal("1.00"),
) -> LLMClient:
    return LLMClient(
        transport,
        stages={"extract": _stage_config()},
        models=_models(),
        cache_root=tmp_path / "cache",
        fresh=fresh,
        runaway_ceiling_usd=runaway_ceiling_usd,
        trace_path=tmp_path / "trace.jsonl",
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


# --- Cache key stability and sensitivity --------------------------------------------------


def test_cache_key_takes_no_path_run_id_or_timestamp_argument() -> None:
    import inspect

    params = set(inspect.signature(compute_cache_key).parameters)
    assert params == {
        "model",
        "reasoning_effort",
        "temperature",
        "prompt_text",
        "schema_json",
        "rendered_inputs",
        "image_hashes",
        "tool_defs",
    }


def _base_key_kwargs() -> dict:
    return {
        "model": "test-model",
        "reasoning_effort": "low",
        "temperature": 0.0,
        "prompt_text": "Answer the question.",
        "schema_json": '{"type": "object"}',
        "rendered_inputs": '{"a": 1}',
        "image_hashes": [],
        "tool_defs": [],
    }


@pytest.mark.parametrize(
    "changed_field,new_value",
    [
        ("model", "other-model"),
        ("reasoning_effort", "high"),
        ("temperature", None),
        ("prompt_text", "A different prompt."),
        ("schema_json", '{"type": "object", "extra": true}'),
        ("rendered_inputs", '{"a": 2}'),
        ("image_hashes", ["deadbeef"]),
        ("tool_defs", [{"name": "lookup"}]),
    ],
)
def test_any_field_change_misses_the_cache_key(changed_field: str, new_value: object) -> None:
    base = compute_cache_key(**_base_key_kwargs())
    kwargs = _base_key_kwargs()
    kwargs[changed_field] = new_value
    changed = compute_cache_key(**kwargs)
    assert base != changed


def test_same_logical_call_produces_the_same_key_regardless_of_call_site() -> None:
    key_a = compute_cache_key(**_base_key_kwargs())
    key_b = compute_cache_key(**_base_key_kwargs())
    assert key_a == key_b


# --- Retries --------------------------------------------------------------------------------


def test_429_then_success_retries_and_reports_two_attempts(tmp_path: Path) -> None:
    transport = FakeTransport(responses=[TransientAPIError("rate limited"), _ok()])
    sleeps: list[float] = []
    client = _client(tmp_path, transport, sleeps=sleeps)

    result = client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    assert result.attempts == 2
    assert result.cache_hit is False
    assert len(sleeps) == 1  # backoff happened once, between the two attempts


def test_five_consecutive_429s_raises_after_four_attempts(tmp_path: Path) -> None:
    transport = FakeTransport(responses=[TransientAPIError("rate limited")] * 5)
    client = _client(tmp_path, transport, sleeps=[])

    with pytest.raises(TransientAPIError):
        client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    assert len(transport.calls) == 4  # MAX_ATTEMPTS, not all 5 queued responses used


# --- Schema re-ask ----------------------------------------------------------------------


def test_one_schema_reask_then_success(tmp_path: Path) -> None:
    transport = FakeTransport(responses=[SchemaValidationError("missing field 'text'"), _ok()])
    client = _client(tmp_path, transport)

    result = client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    assert result.attempts == 2
    # the retry carried the validation error back to the model
    second_call_input = transport.calls[1]["input"]
    assert any("missing field 'text'" in str(m.get("content", "")) for m in second_call_input)


def test_two_schema_failures_raises_schema_validation_error(tmp_path: Path) -> None:
    transport = FakeTransport(
        responses=[SchemaValidationError("bad"), SchemaValidationError("still bad")]
    )
    client = _client(tmp_path, transport)

    with pytest.raises(SchemaValidationError):
        client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    assert len(transport.calls) == 2  # one original call, one re-ask, then it gives up


# --- Empty / refused output ---------------------------------------------------------------


def test_refusal_raises_empty_output_error_not_an_empty_result(tmp_path: Path) -> None:
    transport = FakeTransport(
        responses=[
            RawCompletion(
                parsed=None,
                refusal="cannot help with this",
                usage=Usage(input_tokens=5, output_tokens=0),
            )
        ]
    )
    client = _client(tmp_path, transport)

    with pytest.raises(EmptyOutputError):
        client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)


def test_empty_parsed_with_no_refusal_also_raises(tmp_path: Path) -> None:
    transport = FakeTransport(
        responses=[
            RawCompletion(parsed=None, refusal=None, usage=Usage(input_tokens=5, output_tokens=0))
        ]
    )
    client = _client(tmp_path, transport)

    with pytest.raises(EmptyOutputError):
        client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)


# --- Cost -----------------------------------------------------------------------------------


def test_cost_is_computed_from_usage_against_the_price_table(tmp_path: Path) -> None:
    # test-model: $1.00 / 1M input, $2.00 / 1M output (see _models()).
    transport = FakeTransport(responses=[_ok(input_tokens=1000, output_tokens=500)])
    client = _client(tmp_path, transport)

    result = client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    # 1000 * (1.00 / 1_000_000) + 500 * (2.00 / 1_000_000) = 0.001 + 0.001
    assert result.cost_usd == Decimal("0.001") + Decimal("0.001")


def test_cost_accounts_for_cached_and_reasoning_token_fields_without_double_counting(
    tmp_path: Path,
) -> None:
    # cached_input_tokens/reasoning_tokens are subsets of input/output_tokens (matching the
    # real API's own usage accounting), not additional billed quantities -- the price table
    # has no separate rate for them.
    usage = Usage(
        input_tokens=1000, output_tokens=500, cached_input_tokens=400, reasoning_tokens=200
    )
    transport = FakeTransport(
        responses=[RawCompletion(parsed=Answer(text="hi"), refusal=None, usage=usage)]
    )
    client = _client(tmp_path, transport)

    result = client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    assert result.cost_usd == Decimal("0.001") + Decimal("0.001")
    assert result.usage.cached_input_tokens == 400
    assert result.usage.reasoning_tokens == 200


# --- Cache hit vs live, and --fresh ---------------------------------------------------------


def test_second_identical_call_hits_the_cache_and_makes_no_transport_call(tmp_path: Path) -> None:
    transport = FakeTransport(responses=[_ok()])
    client = _client(tmp_path, transport)

    first = client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)
    second = client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert client.live_count == 1
    assert client.hit_count == 1
    assert len(transport.calls) == 1  # the second call never touched the transport


def test_fresh_bypasses_an_existing_cache_entry_and_rewrites_it(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    first_transport = FakeTransport(responses=[_ok(text="first")])
    first_client = LLMClient(
        first_transport,
        stages={"extract": _stage_config()},
        models=_models(),
        cache_root=cache_root,
        trace_path=None,
        sleep=lambda s: None,
    )
    first_client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    second_transport = FakeTransport(responses=[_ok(text="second")])
    second_client = LLMClient(
        second_transport,
        stages={"extract": _stage_config()},
        models=_models(),
        cache_root=cache_root,
        fresh=True,
        trace_path=None,
        sleep=lambda s: None,
    )
    result = second_client.structured(
        stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer
    )

    assert result.cache_hit is False
    assert result.output.text == "second"
    assert len(second_transport.calls) == 1


# --- Trace ------------------------------------------------------------------------------


def test_trace_writes_one_json_line_per_call_with_designs_fields(tmp_path: Path) -> None:
    transport = FakeTransport(responses=[_ok()])
    client = _client(tmp_path, transport)

    client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)
    client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)  # hit

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)  # each line is valid JSON on its own
        for key in ("stage", "model", "prompt_version", "cache_hit", "attempts", "outcome"):
            assert key in record


# --- Runaway cost guard --------------------------------------------------------------------


def test_runaway_guard_raises_before_a_transport_call_once_the_ceiling_is_already_exceeded(
    tmp_path: Path,
) -> None:
    transport = FakeTransport(responses=[_ok(input_tokens=1_000_000, output_tokens=1_000_000)])
    client = _client(tmp_path, transport, runaway_ceiling_usd=Decimal("0.0000001"))
    # first call: spends (1_000_000 * 1e-6) + (1_000_000 * 2e-6) = $3.00, over the ceiling,
    # but the ceiling is only checked *before* a call, so this one still goes through.
    client.structured(stage="extract", prompt=_prompt(), inputs={"a": 1}, schema=Answer)

    with pytest.raises(RunawayCostError):
        client.structured(stage="extract", prompt=_prompt(), inputs={"a": 2}, schema=Answer)

    assert len(transport.calls) == 1  # the second, guarded call never reached the transport
