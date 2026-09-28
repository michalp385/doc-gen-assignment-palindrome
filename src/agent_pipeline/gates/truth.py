"""The `Truth` a gate checks a report against, in either of the pipeline's two modes
(DESIGN.md section 8.1): `report_eval.truth.ExpectedTruth` wraps a client's hand-derived
`ExpectedFacts` (eval mode); `LedgerTruth` here wraps a real run's `Ledger` (pipeline mode).
Every gate function in `deterministic.py` is written once against this protocol and works
unchanged in both.

`ExpectedTruth` lives in `report_eval/`, not here: this package (`agent_pipeline`) is the
pipeline itself and must never depend on `report_eval` (eval/test tooling, D17) -- only the
reverse. `report_eval.truth` imports `TableAccount`/`MarkerSpec`/`ReviewSpec` from here
instead (verifier report, M0b checkpoint, finding #2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agent_pipeline.ledger import Ledger, render_prose, render_table

# A qualifier the ledger's renderers put before an amount ("c. " before an approximate one).
QUALIFIER_PREFIXES = ("c. ", "up to ", "around ", "a little over ", "a little under ")


def figure_core(figure: str) -> str:
    """The bare amount of a rendered figure, qualifier prefix removed ("c. " + amount ->
    the amount). G2's footnote-only rule matches on this, so a superseded value can't slip
    out of the footnote just by dropping its qualifier."""
    for prefix in QUALIFIER_PREFIXES:
        if figure.startswith(prefix):
            return figure[len(prefix) :]
    return figure


@dataclass(frozen=True)
class TableAccount:
    """One row the account table should show, or should not (T9 doesn't distinguish; a
    row simply not present in `table_accounts()` is out of scope, per R2/G1)."""

    id: str  # an account_id, "new:<slug>" (P9) or "unresolved:<slug>" (R8)
    owners: list[str]
    value_text: str  # as rendered: "£9,500", "c. £13,200", "To be opened", or "marker"
    superseded_texts: list[str] = field(default_factory=list)  # footnote-only values (G6)

    @property
    def is_new(self) -> bool:
        return self.id.startswith("new:")


@dataclass(frozen=True)
class MarkerSpec:
    key: str
    description: str


@dataclass(frozen=True)
class ReviewSpec:
    key: str
    kind: str
    blocking: bool
    must_mention: list[str] = field(default_factory=list)


class Truth(Protocol):
    def table_accounts(self) -> list[TableAccount]: ...  # G1, G6, G13 (new-account wording)
    def reportable_figures(self) -> set[str]: ...  # G2
    def transaction_figures(self) -> set[str]: ...  # G9: never in Background
    def tax_section_expected(self) -> bool: ...  # G5
    def required_markers(self) -> list[MarkerSpec]: ...  # G14
    def expected_review_items(self) -> list[ReviewSpec]: ...  # G15
    def risk_profile(self) -> str | None: ...  # G13
    def initial_charge(self) -> str | None: ...  # G13
    def client_names(self) -> set[str]: ...  # G13
    def excluded_item_subjects(self) -> set[str]: ...  # P6 aspirations only (see docstring)
    def tangent_subjects(self) -> set[str]: ...  # P6: never appears, anywhere (T19)


class LedgerTruth:
    """Truth from a real run's `Ledger` (pipeline mode)."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def table_accounts(self) -> list[TableAccount]:
        rows = []
        for account in self._ledger.accounts:
            if not account.in_scope:
                continue
            if account.is_new:
                value_text = "To be opened"
            elif account.value_marker:
                value_text = "marker"
            elif account.value:
                value_text = render_table(account.value)
            else:
                value_text = "marker"
            rows.append(
                TableAccount(
                    id=account.id,
                    owners=account.owners,
                    value_text=value_text,
                    superseded_texts=[render_prose(v) for v in account.superseded],
                )
            )
        return rows

    def reportable_figures(self) -> set[str]:
        figures = set()
        for fact in self._ledger.facts.values():
            if fact.reportable and fact.value:
                figures.add(render_table(fact.value))
                figures.add(render_prose(fact.value))
        # The initial charge (e.g. "0%") is never a Fact -- it's a plain Ledger field
        # inserted by a computed placeholder (T16 checkpoint), not the token machinery,
        # since G13 needs it verbatim and Fact/Value's rendering is money-shaped, not a
        # percentage label read straight from the instruction. G2 still scans the whole
        # report text for any percent figure, so it needs to be in the allowed set too.
        if self._ledger.initial_charge:
            figures.add(self._ledger.initial_charge)
        return figures

    def transaction_figures(self) -> set[str]:
        # G9's own carve-out (SCOPING.md): "values in the account table are not transaction
        # amounts" -- a disposal's proceeds are P5-rendered at the disposed account's own
        # R3-selected value, so a full disposal's proceeds figure and its account's table
        # value are necessarily the same string (T19, client 02's GIA). Excluding table
        # values here mirrors `report_eval.truth.ExpectedTruth.transaction_figures`, which
        # already did this (its own docstring cites exactly this reasoning); this ledger-
        # mode twin didn't, because no client exercised the coincidence until now.
        table_values = {render_table(a.value) for a in self._ledger.accounts if a.value}
        figures = set()
        for fact in self._ledger.facts.values():
            if fact.transaction and fact.value:
                figures.add(render_table(fact.value))
                figures.add(render_prose(fact.value))
        return figures - table_values

    def tax_section_expected(self) -> bool:
        return self._ledger.tax_section

    def required_markers(self) -> list[MarkerSpec]:
        return [MarkerSpec(key=m.key, description=m.text) for m in self._ledger.markers]

    def expected_review_items(self) -> list[ReviewSpec]:
        return [
            ReviewSpec(key=r.id, kind=r.kind, blocking=r.blocking, must_mention=[])
            for r in self._ledger.review
        ]

    def risk_profile(self) -> str | None:
        return self._ledger.risk_profile

    def initial_charge(self) -> str | None:
        return self._ledger.initial_charge

    def client_names(self) -> set[str]:
        return {owner for account in self._ledger.accounts for owner in account.owners}

    def excluded_item_subjects(self) -> set[str]:
        return {
            item.description for item in self._ledger.excluded if item.item_class == "aspiration"
        }

    def tangent_subjects(self) -> set[str]:
        return {item.description for item in self._ledger.excluded if item.item_class == "tangent"}

    def footnote_only_figures(self) -> set[str]:
        """G2 / SCOPING P9: a superseded value may appear only in the table's footnote. A
        figure whose bare amount is also a current value, a stated amount or the initial
        charge somewhere else is not restricted -- it is legitimately stated elsewhere. (An
        optional `Truth` capability, like `tangent_subjects`: the gate reads it with
        `getattr`, so a `Truth` written before it still works.)"""
        restricted: set[str] = set()
        elsewhere: set[str] = set()
        for fact in self._ledger.facts.values():
            if not (fact.reportable and fact.value):
                continue
            forms = {render_table(fact.value), render_prose(fact.value)}
            (restricted if fact.placement == "footnote_only" else elsewhere).update(forms)
        elsewhere |= {render_table(a.value) for a in self._ledger.accounts if a.value}
        if self._ledger.initial_charge:
            elsewhere.add(self._ledger.initial_charge)
        elsewhere_cores = {figure_core(f) for f in elsewhere}
        return {f for f in restricted if figure_core(f) not in elsewhere_cores}
