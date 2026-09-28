"""G2's footnote-only rule at its edges (T24 verifier checkpoint): a superseded figure followed
by punctuation, a superseded approximate figure written bare in prose, a longer number that
merely contains the superseded one, and the real committed client 02 report.

`tests/test_gates_g2_footnote_only.py` covers the three placements; this file covers how the
figure is written, which is where the first version of the rule had a hole (a trailing comma
was treated as part of the number, so "worth £40,000, which" passed).
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from agent_pipeline.gates.deterministic import TABLE_HEADER, ReportBundle, run_gates
from agent_pipeline.gates.truth import LedgerTruth, Truth
from agent_pipeline.ledger import Account, Fact, Ledger, Qualifier, Value
from report_eval.expected import ReportableFigure
from report_eval.reference import build_reference_bundle
from report_eval.truth import ExpectedTruth


def _g2(bundle: ReportBundle, truth: Truth) -> bool:
    return {r.gate: r for r in run_gates(bundle, truth)}["G2"].passed


def _with_recommendation(bundle: ReportBundle, extra: str) -> ReportBundle:
    old = bundle.sections["recommendations"]
    return dataclasses.replace(
        bundle,
        report_text=bundle.report_text.replace(old, old + extra, 1),
        sections={**bundle.sections, "recommendations": old + extra},
    )


@pytest.mark.parametrize("after", [",", ".", ";", ")", ":", " which", "\n"])
def test_a_superseded_figure_fails_g2_whatever_follows_it(after: str) -> None:
    bundle, truth = build_reference_bundle("client_02_medium")
    mutated = _with_recommendation(bundle, f" The account was worth £40,000{after} earlier.")
    assert _g2(mutated, truth) is False


def test_a_longer_number_containing_the_superseded_one_is_not_a_match() -> None:
    bundle, truth = build_reference_bundle("client_02_medium")
    facts = truth._facts  # noqa: SLF001  # the test needs the fixture behind the truth
    figures = [*facts.reportable_figures, ReportableFigure(value="£140,000", placement="any")]
    relaxed = ExpectedTruth(facts.model_copy(update={"reportable_figures": figures}))
    mutated = _with_recommendation(bundle, " A larger holding was worth £140,000.")
    assert _g2(mutated, relaxed) is True


def _approximate(amount: str, qualifier: Qualifier) -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision="approximate",
        qualifier=qualifier,
        date=None,
        source_id="s",
        quote="",
        selected_by="R3",
    )


def _ledger_with_approximate_superseded() -> Ledger:
    return Ledger(
        client="c",
        accounts=[
            Account(id="A", owners=["A B"], type="General Investment Account", in_scope=True)
        ],
        facts={
            "account.A.superseded.1": Fact(
                id="account.A.superseded.1",
                kind="money",
                description="superseded",
                value=_approximate("40000", "around"),
                reportable=True,
                role="superseded value",
                placement="footnote_only",
            ),
        },
    )


def test_a_superseded_approximate_figure_written_bare_in_prose_fails_g2() -> None:
    # The ledger renders it "c. £40,000" / "around £40,000"; prose "worth £40,000" has neither
    # qualifier, but it is the same amount and still a superseded value outside the footnote.
    truth = LedgerTruth(_ledger_with_approximate_superseded())
    table = f"{TABLE_HEADER}\n|---|---|---|---|\n| A | A B | GIA | marker |"
    bundle = ReportBundle(report_text=f"{table}\n\nIt was worth £40,000 last spring.")
    assert "£40,000" not in truth.reportable_figures()  # only the qualified forms are allowed
    assert _g2(bundle, truth) is False


def test_the_qualified_superseded_figure_inside_the_footnote_is_allowed() -> None:
    truth = LedgerTruth(_ledger_with_approximate_superseded())
    table = f"{TABLE_HEADER}\n|---|---|---|---|\n| A | A B | GIA | marker |"
    bundle = ReportBundle(report_text=f"{table}\n\nPreviously shown as around £40,000.")
    assert _g2(bundle, truth) is True


# --- the real committed client 02 report ---------------------------------------------------


def test_g2_holds_on_the_committed_client_02_report() -> None:
    """The replay test only covers client 01, which has no superseded value; client 02's real
    output is the one committed report that exercises the footnote-only rule."""
    ledger = Ledger.model_validate_json(
        Path("outputs/client_02_medium.ledger.json").read_text(encoding="utf-8")
    )
    text = Path("outputs/client_02_medium.md").read_text(encoding="utf-8")
    truth = LedgerTruth(ledger)
    assert truth.footnote_only_figures()  # the rule has something to enforce here
    assert _g2(ReportBundle(report_text=text, ledger=ledger), truth) is True
