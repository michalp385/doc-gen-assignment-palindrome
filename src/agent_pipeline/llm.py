"""The one door to the model (DESIGN.md section 9): the only module that imports `openai`
(a `Transport` isolates everything else here from the SDK's exact response shape, so tests
inject a fake one with no network at all). Caches every response (D3), retries transient
errors, re-asks once on a schema-validation failure, never returns an empty/refused result,
computes cost from usage, and traces every call.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from agent_pipeline.cache import CacheEntry, Usage, read_entry, write_entry
from agent_pipeline.config import PromptSpec, StageConfig

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 4  # total tries for transient errors (DESIGN section 9: "up to 4 attempts")
_BACKOFF_BASE_S = 1.0
_BACKOFF_JITTER_S = 0.5


class TransientAPIError(Exception):
    """429, 5xx, timeout or connection error -- retried with backoff."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SchemaValidationError(Exception):
    """The model's output didn't match the requested schema -- gets exactly one re-ask."""


class EmptyOutputError(Exception):
    """A refusal or empty output. Never returned as a result (CLAUDE.md: no invented gaps)."""


class RunawayCostError(Exception):
    """This run's cumulative cost would exceed its ceiling -- a fault guard, not a budget."""


@dataclass(frozen=True)
class ImageInput:
    name: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class Tool:
    name: str
    definition: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RawCompletion:
    parsed: BaseModel | None  # None on refusal or empty output
    refusal: str | None
    usage: Usage


class Transport(Protocol):
    def responses_parse(
        self,
        *,
        model: str,
        input: list[dict],
        text_format: type[BaseModel],
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> RawCompletion: ...


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    output: T
    cache_hit: bool
    usage: Usage
    cost_usd: Decimal
    latency_s: float
    attempts: int


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def compute_cache_key(
    *,
    model: str,
    reasoning_effort: str | None,
    temperature: float | None,
    prompt_text: str,
    schema_json: str,
    rendered_inputs: str,
    image_hashes: Sequence[str],
    tool_defs: Sequence[dict],
) -> str:
    """DESIGN.md section 9: sha256 of {model, stage settings, prompt text, schema JSON,
    rendered inputs, image sha256s, tool definitions}. No path, run id or timestamp is ever
    an input to this function -- the key can't drift by checkout or by when it runs (S4)."""
    canonical = {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "temperature": temperature,
        "prompt_text": prompt_text,
        "schema_json": schema_json,
        "inputs": rendered_inputs,
        "image_hashes": sorted(image_hashes),
        "tools": list(tool_defs),
    }
    return hashlib.sha256(_canonical_json(canonical).encode()).hexdigest()


def _backoff_delay(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return retry_after
    return _BACKOFF_BASE_S * (2 ** (attempt - 1)) + random.uniform(0, _BACKOFF_JITTER_S)


def _compute_cost(model: str, usage: Usage, prices: Mapping[str, Mapping[str, float]]) -> Decimal:
    # input_tokens/output_tokens are already inclusive totals (cached-input is a subset of
    # input_tokens, reasoning is a subset of output_tokens, matching the real API's own
    # usage accounting) -- config/models.json has no separate cached/reasoning rate, so
    # they're billed at the ordinary input/output rate they're already part of. The two
    # subset fields exist on Usage for visibility (a run summary can report them), not as
    # additional billed quantities.
    price = prices[model]
    input_rate = Decimal(str(price["input"])) / Decimal(1_000_000)
    output_rate = Decimal(str(price["output"])) / Decimal(1_000_000)
    return usage.input_tokens * input_rate + usage.output_tokens * output_rate


class LLMClient:
    def __init__(
        self,
        transport: Transport,
        *,
        stages: Mapping[str, StageConfig],
        models: Mapping[str, object],
        cache_root: Path,
        fresh: bool = False,
        runaway_ceiling_usd: Decimal = Decimal("1.00"),
        trace_path: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._stages = stages
        self._prices: Mapping[str, Mapping[str, float]] = models.get("prices_per_1m_tokens", {})  # type: ignore[assignment]
        self._capabilities: Mapping[str, Mapping[str, object]] = models.get("capabilities", {})  # type: ignore[assignment]
        self._cache_root = cache_root
        self._fresh = fresh
        self._runaway_ceiling_usd = runaway_ceiling_usd
        self._trace_path = trace_path
        self._sleep = sleep
        self.hit_count = 0
        self.live_count = 0
        self._spent_usd = Decimal(0)

    def _temperature_accepted(self, model: str) -> bool:
        entry = self._capabilities.get(model, {})
        return bool(entry.get("temperature_accepted", False))

    def _render_input(
        self, prompt: PromptSpec, inputs: Mapping[str, object], images: Sequence[ImageInput]
    ) -> list[dict]:
        rendered_inputs = _canonical_json(inputs)
        user_content: object = rendered_inputs
        if images:
            parts: list[dict] = [{"type": "input_text", "text": rendered_inputs}]
            for image in images:
                b64 = base64.b64encode(image.content).decode("ascii")
                parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{b64}"})
            user_content = parts
        return [
            {"role": "system", "content": prompt.text},
            {"role": "user", "content": user_content},
        ]

    def _write_trace(self, **fields: object) -> None:
        if self._trace_path is None:
            return
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self._trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fields, sort_keys=True) + "\n")

    def structured(
        self,
        *,
        stage: str,
        prompt: PromptSpec,
        inputs: Mapping[str, object],
        schema: type[T],
        images: Sequence[ImageInput] = (),
        tools: Sequence[Tool] = (),
    ) -> LLMResult[T]:
        stage_config = self._stages[stage]
        rendered_inputs = _canonical_json(inputs)
        schema_json = _canonical_json(schema.model_json_schema())
        temperature = 0.0 if self._temperature_accepted(stage_config.model) else None
        key = compute_cache_key(
            model=stage_config.model,
            reasoning_effort=stage_config.reasoning_effort,
            temperature=temperature,
            prompt_text=prompt.text,
            schema_json=schema_json,
            rendered_inputs=rendered_inputs,
            image_hashes=[img.sha256 for img in images],
            tool_defs=[t.definition for t in tools],
        )

        if not self._fresh:
            cached = read_entry(self._cache_root, key)
            if cached is not None:
                self.hit_count += 1
                output = schema.model_validate(cached.response)
                self._write_trace(
                    stage=stage,
                    model=stage_config.model,
                    prompt_version=prompt.version,
                    cache_hit=True,
                    tokens=cached.usage.model_dump(),
                    cost_usd=cached.cost_usd,
                    latency_s=0.0,
                    attempts=0,
                    outcome="success",
                )
                return LLMResult(
                    output=output,
                    cache_hit=True,
                    usage=cached.usage,
                    cost_usd=Decimal(cached.cost_usd),
                    latency_s=0.0,
                    attempts=0,
                )

        estimated_min_cost = self._spent_usd  # a live call only adds to this; check first
        if estimated_min_cost > self._runaway_ceiling_usd:
            raise RunawayCostError(
                f"stage {stage!r}: cumulative cost ${self._spent_usd} already exceeds the "
                f"${self._runaway_ceiling_usd} per-run ceiling"
            )

        self.live_count += 1
        start = time.monotonic()
        current_input = self._render_input(prompt, inputs, images)
        # `tools` is part of the cache key (DESIGN section 9), but no stage in scope yet
        # calls with tools, so actually wiring tool-call definitions/round-trips into the
        # transport call is deferred to whichever task first needs it (investigate/tools.py).
        attempts = 0
        transient_attempts = 0
        schema_reasked = False
        raw: RawCompletion | None = None
        while raw is None:
            attempts += 1
            try:
                raw = self._transport.responses_parse(
                    model=stage_config.model,
                    input=current_input,
                    text_format=schema,
                    temperature=temperature,
                    reasoning_effort=stage_config.reasoning_effort,
                )
            except TransientAPIError as exc:
                transient_attempts += 1
                if transient_attempts >= MAX_ATTEMPTS:
                    self._write_trace(
                        stage=stage,
                        model=stage_config.model,
                        prompt_version=prompt.version,
                        cache_hit=False,
                        attempts=attempts,
                        latency_s=time.monotonic() - start,
                        outcome="transient_error_exhausted",
                    )
                    raise
                self._sleep(_backoff_delay(transient_attempts, exc.retry_after))
            except SchemaValidationError as exc:
                if schema_reasked:
                    self._write_trace(
                        stage=stage,
                        model=stage_config.model,
                        prompt_version=prompt.version,
                        cache_hit=False,
                        attempts=attempts,
                        latency_s=time.monotonic() - start,
                        outcome="schema_invalid",
                    )
                    raise
                schema_reasked = True
                retry_note = f"Your output did not match the required schema: {exc}. Try again."
                current_input = [*current_input, {"role": "user", "content": retry_note}]

        latency_s = time.monotonic() - start
        if raw.parsed is None:
            self._write_trace(
                stage=stage,
                model=stage_config.model,
                prompt_version=prompt.version,
                cache_hit=False,
                attempts=attempts,
                latency_s=latency_s,
                outcome="empty_or_refused",
            )
            raise EmptyOutputError(raw.refusal or "empty output")

        cost = _compute_cost(stage_config.model, raw.usage, self._prices)
        self._spent_usd += cost
        write_entry(
            self._cache_root,
            key,
            CacheEntry(
                stage=stage,
                model=stage_config.model,
                prompt_version=prompt.version,
                input_hash=hashlib.sha256(rendered_inputs.encode()).hexdigest(),
                response=raw.parsed.model_dump(),
                usage=raw.usage,
                cost_usd=str(cost),
            ),
        )
        self._write_trace(
            stage=stage,
            model=stage_config.model,
            prompt_version=prompt.version,
            cache_hit=False,
            tokens=raw.usage.model_dump(),
            cost_usd=str(cost),
            latency_s=latency_s,
            attempts=attempts,
            outcome="success",
        )
        return LLMResult(
            output=raw.parsed,  # type: ignore[arg-type]
            cache_hit=False,
            usage=raw.usage,
            cost_usd=cost,
            latency_s=latency_s,
            attempts=attempts,
        )


class OpenAITransport:
    """The real `Transport`, wrapping `openai.OpenAI().responses.parse(...)`. The only place
    in this module (and the whole pipeline, DESIGN.md section 9) that imports `openai`.
    """

    def __init__(self, client: object | None = None) -> None:
        from openai import OpenAI

        self._client = client if client is not None else OpenAI()

    def responses_parse(
        self,
        *,
        model: str,
        input: list[dict],
        text_format: type[BaseModel],
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> RawCompletion:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            BadRequestError,
            RateLimitError,
        )

        kwargs: dict = {"model": model, "input": input, "text_format": text_format}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": reasoning_effort}

        try:
            response = self._client.responses.parse(**kwargs)  # type: ignore[attr-defined]
        except RateLimitError as exc:
            retry_after = _retry_after_seconds(exc)
            raise TransientAPIError(str(exc), retry_after=retry_after) from exc
        except APITimeoutError as exc:
            raise TransientAPIError(str(exc)) from exc
        except APIConnectionError as exc:
            raise TransientAPIError(str(exc)) from exc
        except BadRequestError:
            raise  # not transient, not a schema failure -- e.g. an unsupported temperature
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientAPIError(str(exc)) from exc
            raise

        usage = response.usage
        if usage is None:
            raise EmptyOutputError("the API response carried no usage data")
        return RawCompletion(
            parsed=response.output_parsed,
            refusal=_extract_refusal(response),
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.input_tokens_details.cached_tokens,
                reasoning_tokens=usage.output_tokens_details.reasoning_tokens,
            ),
        )


def _retry_after_seconds(exc: object) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    value = headers.get("retry-after") if headers is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _extract_refusal(response: object) -> str | None:
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            if getattr(content, "type", None) == "refusal":
                return getattr(content, "refusal", None)
    return None
