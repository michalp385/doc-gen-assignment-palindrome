"""P2, G15: assemble the review sheet's items with stable ids.

A thin, generic assembly step: every conflict, superseded value, out-of-scope null, open
action, P4 note, scope flag and currency item ends up here as a ReviewItemInput, whatever
rule produced it; this just numbers them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_pipeline.ledger import Marker, ReviewItem


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


def marker_review_items(markers: list[Marker]) -> list[ReviewItemInput]:
    """G15 (SCOPING.md): every report marker needs a matching review-sheet row (P1). One
    row per marker, referencing its key, so the marker is never invisible to anything that
    reads the ledger's review list rather than the rendered "Markers to fill" section."""
    return [
        ReviewItemInput(
            kind="marker_reference", blocking=False, detail=f"see marker {m.key}", refs=[m.key]
        )
        for m in markers
    ]
