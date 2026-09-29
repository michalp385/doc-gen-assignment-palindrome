"""R4: the report instruction's decisions against what the meeting records (DESIGN.md
`reconcile_decisions`, SCOPING section 3.1 rule 4).

Today one decision: "selling existing investments?". A mismatch with the disposals the meeting
records is never settled silently: it is a blocking conflict quoting both sides, plus a marker,
and a selling mismatch is G5 case b, a possible taxable disposal pending confirmation. When the
instruction says yes and the meeting records no sale, a possible disposal is added so that the
tax section is included rather than omitted ("flagging a possible disposal is safer than
omitting one"). A value that is not clearly yes or no is left alone. Pure code, no model call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agent_pipeline.ledger import Marker
from agent_pipeline.reconcile.review import ReviewItemInput

_YES = {"yes", "y", "partial", "part"}
_NO = {"no", "n", "none", "nil"}


@dataclass(frozen=True)
class DecisionCheck:
    marker: Marker | None = None
    review_item: ReviewItemInput | None = None
    add_possible_disposal: bool = False


def _says_selling(value: str) -> bool | None:
    words = value.strip().lower().split()
    if not words:
        return None
    first = words[0].strip(".,;:()?!")
    if first in _YES:
        return True
    if first in _NO:
        return False
    return None


def check_selling_decision(label: str, value: str, disposal_quotes: Sequence[str]) -> DecisionCheck:
    """`label` and `value` are the instruction's own wording; `disposal_quotes` are the verified
    quotes of the disposals the meeting records."""
    says_selling = _says_selling(value)
    if says_selling is None or says_selling == bool(disposal_quotes):
        return DecisionCheck()
    said = f"{label} | {value}"
    if says_selling:
        detail = (
            f"the report instruction says '{said}' but the meeting record shows no sale; "
            "confirm whether anything is sold before anything is finalised."
        )
    else:
        quoted = "; ".join(f'"{q}"' for q in disposal_quotes)
        detail = (
            f"the report instruction says '{said}' but the meeting record shows a sale: "
            f"{quoted}; confirm whether anything is sold before anything is finalised."
        )
    return DecisionCheck(
        marker=Marker(
            id="",
            key="disposal_pending_confirmation",
            text="whether an existing investment is sold: the report instruction and the "
            "meeting record differ",
            reason="R4/G5b: a possible taxable disposal pending confirmation, not settled silently",
            section="recommendations",
        ),
        review_item=ReviewItemInput(kind="conflict", blocking=True, detail=detail, refs=[]),
        add_possible_disposal=says_selling,
    )
