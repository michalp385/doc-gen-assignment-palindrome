"""The common shape every source adapter (T7) reads a file into.

One `SourceDoc` per file: its paragraphs, keyed by a stable id so a quote can be checked
against the specific paragraph it claims to come from (T5's same-paragraph rule), not just
"appears somewhere in the document".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class SourceDoc:
    path: Path
    paragraphs: dict[str, str] = field(default_factory=dict)  # paragraph_id -> text
    tables: list[list[list[str]]] = field(default_factory=list)
    metadata_date: date | None = None  # docx core-properties date; never selects a value (R3)

    def paragraph_text(self, paragraph_id: str) -> str | None:
        return self.paragraphs.get(paragraph_id)
