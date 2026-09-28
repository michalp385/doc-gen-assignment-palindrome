"""P2, P3, P7: markers that are always required, built in code, never typed by the model.

Platform charge rates and the ongoing advice charge rate are never estimated (CLAUDE.md's
non-negotiable); one platform-charge marker per platform actually in scope, plus the one
advice-charge marker. Marker text is built here from the ledger; IDs are assigned later, at
assembly, by number_markers (T6), in order of first appearance in the report (P1).
"""

from __future__ import annotations

from agent_pipeline.ledger import Marker
from agent_pipeline.reconcile.sections import Disposal

_NEVER_ESTIMATED = "never estimated (CLAUDE.md non-negotiable)"


def required_markers(in_scope_platforms: set[str]) -> list[Marker]:
    markers = [
        Marker(
            id="",
            key=f"platform_charge_{platform.lower()}",
            text=f"ongoing platform charge rate, {platform}",
            reason=_NEVER_ESTIMATED,
            section="fees_charges",
        )
        for platform in sorted(in_scope_platforms)
    ]
    markers.append(
        Marker(
            id="",
            key="advice_charge",
            text="ongoing advice charge rate",
            reason=_NEVER_ESTIMATED,
            section="fees_charges",
        )
    )
    return markers


def cgt_marker(disposals: list[Disposal]) -> list[Marker]:
    """P7 (T19): one marker per taxable disposal -- CGT amounts are never estimated
    (CLAUDE.md non-negotiable), same rule as the charge markers above. Key is a bare
    "cgt" for the single-disposal case every current client has; a second taxable
    disposal in the same advice (none yet) would need a disambiguating key, not built
    until a client actually has two."""
    taxable = [d for d in disposals if d.wrapper_class == "taxable"]
    if not taxable:
        return []
    return [
        Marker(
            id="",
            key="cgt",
            text="capital gains tax on the disposal",
            reason=_NEVER_ESTIMATED,
            section="tax_implications",
        )
    ]
