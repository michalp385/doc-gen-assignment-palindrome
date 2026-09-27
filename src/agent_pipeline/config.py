"""Report config loading and prompt versioning (T10, DESIGN.md sections 7.1, 7.3, 11).

A report config `extends` a base config (DESIGN section 11): resolution merges sections by
`id`, so a report can take a base section as is, override fields of it, or add its own. The
resolved `ReportConfig` is a complete inline section list. A section's `predicate` (D11) must
name a function already registered in `reconcile/predicates.py`; an unknown name fails
loading with a clear error, never a silent fallback to model-judged inclusion (that fallback
is for a section with *no* predicate at all, per DESIGN section 7.1).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_pipeline.reconcile.predicates import PREDICATES


class ConfigError(Exception):
    """A config file doesn't load or resolve. Never silently degraded."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptSpec(_Strict):
    text: str
    version: str  # sha256(text + output_schema) hex digest


class Placeholder(_Strict):
    kind: Literal["generated", "computed"]
    prompt: str | None = None  # required in practice for "generated"; unused for "computed"


class Section(_Strict):
    id: str
    title: str
    use_if: str
    predicate: str | None = None
    template: str
    placeholders: dict[str, Placeholder] = Field(default_factory=dict)
    # Glob patterns (DESIGN.md section 6): which ledger facts/markers/excluded-item classes
    # this section's plan may draw on. Client-general by construction (e.g. "account.*.value",
    # "platform_charge_*") -- never a specific account id or platform name.
    facts: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    # Which ledger free-text collections this section's plan may digit-free-rewrite (e.g.
    # "actions"), and which named, plain-language context keys it wants (e.g.
    # "scope_description") -- config-driven so a new section's needs are a config change,
    # never a new branch in write/plan.py (S6: one new config, not new code).
    text_sources: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)


class StageConfig(_Strict):
    model: str
    reasoning_effort: Literal["none", "low", "medium", "high"]


class ReportConfig(_Strict):
    document_title: str
    global_instructions: str
    stages: dict[str, StageConfig] = Field(default_factory=dict)
    sections: list[Section] = Field(default_factory=list)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{path} is not readable JSON: {exc}") from exc


def _merge_sections(base: list[dict], own: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {s["id"]: dict(s) for s in base}
    order: list[str] = [s["id"] for s in base]
    for section in own:
        section_id = section["id"]
        if section_id in merged:
            merged[section_id] = {**merged[section_id], **section}
        else:
            merged[section_id] = dict(section)
            order.append(section_id)
    return [merged[i] for i in order]


def _validate_predicates(sections: list[Section]) -> None:
    for section in sections:
        if section.predicate is not None and section.predicate not in PREDICATES:
            raise ConfigError(
                f"section {section.id!r} names unknown predicate {section.predicate!r}"
            )


def load_report_config(path: Path) -> ReportConfig:
    raw = _read_json(path)
    extends = raw.pop("extends", None)
    if extends is not None:
        base = _read_json(path.parent / extends)
        base.pop("extends", None)  # one level of extends only (DESIGN section 11)
        merged = {**base, **raw}
        merged["sections"] = _merge_sections(base.get("sections", []), raw.get("sections", []))
    else:
        merged = raw

    config = ReportConfig.model_validate(merged)
    _validate_predicates(config.sections)
    return config


def load_prompt(path: Path, output_schema: str = "") -> PromptSpec:
    text = path.read_text(encoding="utf-8")
    version = hashlib.sha256(f"{text}\n{output_schema}".encode()).hexdigest()
    return PromptSpec(text=text, version=version)
