"""Read a .md file into a SourceDoc: one addressable paragraph id per blank-line-separated
block (headings included), so a quote from internal guidance can be checked against the
specific block it came from (T7).
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_pipeline.sources.document import SourceDoc


def read_markdown(path: Path) -> SourceDoc:
    text = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    paragraphs = {f"p{i}": block for i, block in enumerate(blocks, start=1)}
    return SourceDoc(path=path, paragraphs=paragraphs)
