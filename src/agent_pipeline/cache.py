"""The LLM response cache: committed JSON files, one per call (D3, DESIGN.md section 9).

No keys, no headers, no absolute paths -- a reviewer's fresh clone hits the same entries a
prior run wrote, so a re-run on unchanged inputs costs nothing. Sharded by the key's first
two hex characters (`cache/llm/<aa>/<key>.json`) so the directory doesn't hold thousands of
files flat, a plain git-friendly convention with no other significance.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0


class CacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    model: str
    prompt_version: str
    input_hash: str
    response: dict = Field(default_factory=dict)
    usage: Usage
    cost_usd: str  # Decimal's string form: no float rounding in a committed file


def cache_path(root: Path, key: str) -> Path:
    return root / key[:2] / f"{key}.json"


def read_entry(root: Path, key: str) -> CacheEntry | None:
    path = cache_path(root, key)
    if not path.exists():
        return None
    return CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))


def write_entry(root: Path, key: str, entry: CacheEntry) -> None:
    path = cache_path(root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry.model_dump(), indent=2, sort_keys=True), encoding="utf-8")
