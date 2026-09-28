"""G5, P7: whether a section applies, decided in code, not by a model (D11).

`taxable_disposal` (G5): a disposal from a `taxable` account, or from an `unknown` wrapper
(DESIGN.md section 5.1: a possible taxable disposal pending confirmation, G5 case b, with a
review item -- `unknown_wrapper_review_items`), includes the Tax Implications section.
`tax_exempt` switches and `bond` encashments never do; a bond gets a marker in
Recommendations instead (`markers.bond_marker`, P7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_pipeline.reconcile.predicates import predicate
from agent_pipeline.reconcile.review import ReviewItemInput


@dataclass(frozen=True)
class Disposal:
    wrapper_class: str  # "taxable" | "tax_exempt" | "bond" | "cash" | "unknown"
    account_id: str = ""  # "" when the disposal matched no single account


@dataclass(frozen=True)
class SectionContext:
    disposals: list[Disposal] = field(default_factory=list)
    disposal_conflict: bool = False  # G5 case b: sources disagree on whether one is happening


@predicate("taxable_disposal")
def taxable_disposal(ctx: SectionContext) -> bool:
    """G5: Tax Implications is present iff a disposal is from a taxable-wrapper account,
    or the sources conflict about whether one is happening (G5 case b, P2)."""
    return ctx.disposal_conflict or any(
        d.wrapper_class in ("taxable", "unknown") for d in ctx.disposals
    )


def unknown_wrapper_review_items(disposals: list[Disposal]) -> list[ReviewItemInput]:
    """G5 case b: a disposal from an unrecognised wrapper, or one that matched no single
    account, is treated as a possible taxable disposal pending confirmation -- flagged for
    the adviser, never guessed either way."""
    items: list[ReviewItemInput] = []
    for disposal in disposals:
        if disposal.wrapper_class != "unknown":
            continue
        if disposal.account_id:
            detail = (
                f"disposal from account {disposal.account_id}: its type is not recognised, so "
                "it is treated as a possible taxable disposal pending confirmation."
            )
        else:
            detail = (
                "a disposal could not be matched to a single account, so it is treated as a "
                "possible taxable disposal pending confirmation."
            )
        items.append(
            ReviewItemInput(
                kind="ambiguity",
                blocking=False,
                detail=detail,
                refs=[disposal.account_id] if disposal.account_id else [],
            )
        )
    return items
