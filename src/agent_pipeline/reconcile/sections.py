"""G5, P7: whether a section applies, decided in code, not by a model (D11).

Only `taxable_disposal` exists for now (client 01 has no disposal at all). The `bond`
marker-not-section path (P7) and the `unknown`-wrapper pending-confirmation path (G5 case
b) arrive in M2 with the clients and hand-written cases that exercise them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_pipeline.reconcile.predicates import predicate


@dataclass(frozen=True)
class Disposal:
    wrapper_class: str  # "taxable" | "tax_exempt" | "bond" | "unknown"


@dataclass(frozen=True)
class SectionContext:
    disposals: list[Disposal] = field(default_factory=list)
    disposal_conflict: bool = False  # G5 case b: sources disagree on whether one is happening


@predicate("taxable_disposal")
def taxable_disposal(ctx: SectionContext) -> bool:
    """G5: Tax Implications is present iff a disposal is from a taxable-wrapper account,
    or the sources conflict about whether one is happening (G5 case b, P2)."""
    return ctx.disposal_conflict or any(d.wrapper_class == "taxable" for d in ctx.disposals)
