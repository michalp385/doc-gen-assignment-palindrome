"""Section plan types (DESIGN.md section 6): what a writer call is allowed to see and use.

`context` holds plain, digit-free descriptive strings a prompt reads as input (e.g. "which
account(s) this section covers") -- distinct from `facts`, which are `{fact:<id>}` tokens
the model may *emit* in its output. Keeping these separate avoids inventing a non-numeric
"account identity" fact DESIGN's own fact-ID examples never show (T14 plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlanFact:
    id: str
    description: str  # no digits (ledger.Fact.description already guarantees this, T6)
    role: str
    transaction: bool = False  # a top-up, proceeds, new money or tax figure (G9: never Background)


@dataclass(frozen=True)
class PlanMarker:
    key: str
    text: str


@dataclass(frozen=True)
class WithheldText:
    """A digit-bearing extraction text with no matching fact -- never reaches the writer
    (DESIGN.md section 6: "a planner gap costs a detail, not the report")."""

    original: str
    reason: str


@dataclass(frozen=True)
class SectionPlan:
    section_id: str
    facts: list[PlanFact] = field(default_factory=list)
    markers: list[PlanMarker] = field(default_factory=list)
    context: dict[str, str] = field(default_factory=dict)
    # Whole-document text (not per-section), for G10's slot-level guidance-leak exclusion:
    # a 6-gram shared with either is legitimate vocabulary, never a guidance leak (DESIGN.md
    # section 8.1's "excluding any 6-gram that also occurs in the meeting record or the spec").
    spec_text: str = ""
    meeting_text: str = ""
    rewritten_texts: dict[str, str] = field(default_factory=dict)
    withheld: list[WithheldText] = field(default_factory=list)
    # Verified handling directives for this section (D8), one line each: the instruction only,
    # never the guidance text.
    handling: list[str] = field(default_factory=list)
