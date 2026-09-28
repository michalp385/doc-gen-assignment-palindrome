"""`ExpectedTruth`: the eval-mode `Truth` (agent_pipeline.gates.truth.Truth), wrapping a
client's hand-derived `ExpectedFacts`. Lives here, not in `agent_pipeline/`, so the pipeline
package's dependency graph never points into eval/test tooling -- only the reverse
(verifier report, M0b checkpoint, finding #2; D17's exemption relies on that direction
holding).
"""

from __future__ import annotations

from agent_pipeline.gates.truth import MarkerSpec, ReviewSpec, TableAccount
from report_eval.expected import ExpectedFacts


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
        # what's left is exactly SCOPING's "top-ups, proceeds, new money, tax figures". A
        # `footnote_only` figure (T19, client 02's superseded GIA statement value) is a
        # historical account *value*, not a transaction amount either, the same reasoning
        # as a current table value -- it just lives in the table's own footnote instead of
        # its cell (G6, `write/table.py`), still squarely part of the account table, not a
        # transaction G9 polices.
        table_values = {row.value for row in self._facts.table_rows}
        footnote_only = {
            fig.value for fig in self._facts.reportable_figures if fig.placement == "footnote_only"
        }
        return {
            fig.value
            for fig in self._facts.reportable_figures
            if fig.value not in table_values
            and fig.value not in footnote_only
            and "%" not in fig.value
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
        # Aspirations only: the at-most-once-in-Background rule (P6). Circumstances aren't
        # a named gate. Tangents have their own, stricter rule -- `tangent_subjects` below.
        return {
            item.subject for item in self._facts.excluded_items if item.item_class == "aspiration"
        }

    def tangent_subjects(self) -> set[str]:
        return {item.subject for item in self._facts.excluded_items if item.item_class == "tangent"}
