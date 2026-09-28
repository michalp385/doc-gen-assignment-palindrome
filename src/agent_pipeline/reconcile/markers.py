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
    until a client actually has two. A disposal from an `unknown` wrapper (G5 case b) also
    gets the marker, worded as a possible disposal unless a definite taxable one shares
    the advice."""
    taxable = [d for d in disposals if d.wrapper_class == "taxable"]
    unknown = [d for d in disposals if d.wrapper_class == "unknown"]
    if not taxable and not unknown:
        return []
    text = (
        "capital gains tax on the disposal"
        if taxable
        else "capital gains tax on the possible disposal, pending confirmation of the "
        "account's tax treatment"
    )
    return [
        Marker(
            id="",
            key="cgt",
            text=text,
            reason=_NEVER_ESTIMATED,
            section="tax_implications",
        )
    ]


def bond_marker(disposals: list[Disposal]) -> list[Marker]:
    """P7: a bond encashment never creates a CGT section; it gets a "chargeable-event gain
    to be assessed" marker in Recommendations, next to the encashment. One marker however
    many bonds are encashed. Never states a gain."""
    if not any(d.wrapper_class == "bond" for d in disposals):
        return []
    return [
        Marker(
            id="",
            key="bond_chargeable_gain",
            text="chargeable-event gain on the bond encashment, to be assessed",
            reason=_NEVER_ESTIMATED,
            section="recommendations",
        )
    ]


def available_marker(reason: str) -> Marker:
    """P5 (T21): the available-now amount becomes a marker when it cannot be computed
    without a guess (a commitment with no stated amount, commitments exceeding receipts,
    mixed currencies). Never states a figure."""
    return Marker(
        id="",
        key="available_to_invest",
        text="amount available to invest now, after commitments",
        reason=f"{reason} (P5); never estimated",
        section="recommendations",
    )
