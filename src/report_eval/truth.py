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
