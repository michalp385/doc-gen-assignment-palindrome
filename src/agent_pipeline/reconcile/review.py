"""P2, G15: assemble the review sheet's items with stable ids.

A thin, generic assembly step: every conflict, superseded value, out-of-scope null, open
action, P4 note, scope flag and currency item ends up here as a ReviewItemInput, whatever
rule produced it; this just numbers them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_pipeline.ledger import ReviewItem


@dataclass(frozen=True)
class ReviewItemInput:
    kind: str
    blocking: bool
    detail: str
    refs: list[str] = field(default_factory=list)


def build_review_items(entries: list[ReviewItemInput]) -> list[ReviewItem]:
    return [
        ReviewItem(id=f"rv{i}", kind=e.kind, blocking=e.blocking, detail=e.detail, refs=e.refs)
        for i, e in enumerate(entries, start=1)
    ]
