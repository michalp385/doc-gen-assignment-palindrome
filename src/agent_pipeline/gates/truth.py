"""The `Truth` a gate checks a report against, in either of the pipeline's two modes
(DESIGN.md section 8.1): `ExpectedTruth` wraps a client's hand-derived `ExpectedFacts`
(eval mode); `LedgerTruth` wraps a real run's `Ledger` (pipeline mode). Every gate function
in `deterministic.py` is written once against this protocol and works unchanged in both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agent_pipeline.ledger import Ledger, render_prose, render_table
from report_eval.expected import ExpectedFacts


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


class ExpectedTruth:
    """Truth from a client's hand-derived `eval/expected/<client>.json` (eval mode)."""

    def __init__(self, facts: ExpectedFacts) -> None:
        self._facts = facts

    def table_accounts(self) -> list[TableAccount]:
        return [
            TableAccount(
                id=row.account,
                owners=row.owners,
                value_text=row.value,
                superseded_texts=[row.footnote] if row.footnote else [],
            )
            for row in self._facts.table_rows
        ]

    def reportable_figures(self) -> set[str]:
        return {fig.value for fig in self._facts.reportable_figures}

    def transaction_figures(self) -> set[str]:
        # ExpectedFacts.ReportableFigure has no explicit "transaction" flag (unlike the real
        # Ledger's Fact.transaction, T6): a table value is never a transaction amount (G9's
        # own wording), and a percentage is a charge/risk figure, not a money movement --
        # what's left is exactly SCOPING's "top-ups, proceeds, new money, tax figures".
        table_values = {row.value for row in self._facts.table_rows}
        return {
            fig.value
            for fig in self._facts.reportable_figures
            if fig.value not in table_values and "%" not in fig.value
        }

    def tax_section_expected(self) -> bool:
        return self._facts.sections.get("tax_implications", False)

    def required_markers(self) -> list[MarkerSpec]:
        return [
            MarkerSpec(key=m.key, description=m.description)
            for m in self._facts.markers
            if m.required
        ]

    def expected_review_items(self) -> list[ReviewSpec]:
        return [
            ReviewSpec(key=r.key, kind=r.kind, blocking=r.blocking, must_mention=r.must_mention)
            for r in self._facts.review_items
        ]

    def risk_profile(self) -> str | None:
        return self._facts.risk_profile

    def initial_charge(self) -> str | None:
        return self._facts.initial_charge

    def client_names(self) -> set[str]:
        return {owner for row in self._facts.table_rows for owner in row.owners}

    def excluded_item_subjects(self) -> set[str]:
        # P6's at-most-once rule is T9's scope; tangents ("never appear at all") and
        # circumstances aren't a named T9 gate, so only aspirations are represented here.
        return {
            item.subject for item in self._facts.excluded_items if item.item_class == "aspiration"
        }


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
        return figures

    def transaction_figures(self) -> set[str]:
        figures = set()
        for fact in self._ledger.facts.values():
            if fact.transaction and fact.value:
                figures.add(render_table(fact.value))
                figures.add(render_prose(fact.value))
        return figures

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
