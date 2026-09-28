"""G2 and the footnote-only rule, tests first (T24).

SCOPING P9: "The footnote is the only place a superseded value may appear (G2)", and DESIGN
10.5's G2 mutation is "a superseded value outside the footnote". A superseded figure is still
a reportable figure -- it must be allowed in the footnote -- so G2's allowed-set check alone
can't catch it stated in prose: the gate must also know which figures are footnote-only and
reject them anywhere outside the table's own footnote (the text after the table in
Background).

Found by running every mutation across all four real clients' reference bundles (T24): the
client 01 bundle has no superseded value, so its own G2 test could only use an unknown
figure.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import cast

import pytest

from agent_pipeline.gates.deterministic import TABLE_HEADER, ReportBundle, run_gates
from agent_pipeline.gates.truth import LedgerTruth, MarkerSpec, ReviewSpec, TableAccount, Truth
from agent_pipeline.ledger import Account, Fact, Ledger, Qualifier, Value
from report_eval.expected import ExpectedFacts
from report_eval.reference import build_reference_bundle
from report_eval.truth import ExpectedTruth

FOOTNOTE_CLIENTS = ["client_02_medium", "client_03_hard", "client_04_stretch"]


def _g2(bundle: ReportBundle, truth: Truth) -> bool:
    return {r.gate: r for r in run_gates(bundle, truth)}["G2"].passed


def _superseded(facts: ExpectedFacts) -> str:
    return next(f.value for f in facts.reportable_figures if f.placement == "footnote_only")


def _replace_section(bundle: ReportBundle, section: str, new: str) -> ReportBundle:
    old = bundle.sections[section]
    return dataclasses.replace(
        bundle,
        report_text=bundle.report_text.replace(old, new, 1),
        sections={**bundle.sections, section: new},
    )


def _truth_facts(truth: ExpectedTruth) -> ExpectedFacts:
    return truth._facts  # noqa: SLF001  # the test needs the fixture behind the truth


@pytest.mark.parametrize("client", FOOTNOTE_CLIENTS)
def test_the_clean_bundle_keeps_its_superseded_figure_in_the_footnote_only(client: str) -> None:
    bundle, truth = build_reference_bundle(client)
    assert _g2(bundle, truth) is True
    assert truth.footnote_only_figures()  # the rule has something to enforce


@pytest.mark.parametrize("client", FOOTNOTE_CLIENTS)
def test_a_superseded_value_in_recommendations_fails_g2(client: str) -> None:
    bundle, truth = build_reference_bundle(client)
    figure = _superseded(_truth_facts(truth))
    old = bundle.sections["recommendations"]
    mutated = _replace_section(bundle, "recommendations", f"{old} It was previously {figure}.")
    assert _g2(mutated, truth) is False


@pytest.mark.parametrize("client", FOOTNOTE_CLIENTS)
def test_a_superseded_value_in_background_before_the_table_fails_g2(client: str) -> None:
    bundle, truth = build_reference_bundle(client)
    figure = _superseded(_truth_facts(truth))
    old = bundle.sections["background_objectives"]
    mutated = _replace_section(bundle, "background_objectives", f"It was {figure}.\n\n{old}")
    assert _g2(mutated, truth) is False


@pytest.mark.parametrize("client", FOOTNOTE_CLIENTS)
def test_a_superseded_value_in_the_table_cell_fails_g2(client: str) -> None:
    bundle, truth = build_reference_bundle(client)
    figure = _superseded(_truth_facts(truth))
    approximate = next(r.value_text for r in bundle.table_rows if r.value_text.startswith("c. "))
    old = bundle.sections["background_objectives"]
    new = old.replace(f"| {approximate} |", f"| {figure} |", 1)
    assert new != old
    assert _g2(_replace_section(bundle, "background_objectives", new), truth) is False


def test_a_figure_also_listed_with_placement_any_is_not_footnote_only() -> None:
    _, truth = build_reference_bundle("client_02_medium")
    facts = _truth_facts(truth)
    figures = [
        f.model_copy(update={"placement": "any"}) if f.placement == "footnote_only" else f
        for f in facts.reportable_figures
    ]
    relaxed = ExpectedTruth(facts.model_copy(update={"reportable_figures": figures}))
    assert relaxed.footnote_only_figures() == set()


def test_a_truth_without_the_method_is_not_a_crash() -> None:
    class _OldTruth:
        """Every `Truth` method except the newer optional ones (tangents, footnote-only)."""

        def table_accounts(self) -> list[TableAccount]:
            return []

        def reportable_figures(self) -> set[str]:
            return {"£1"}

        def transaction_figures(self) -> set[str]:
            return set()

        def tax_section_expected(self) -> bool:
            return False

        def required_markers(self) -> list[MarkerSpec]:
            return []

        def expected_review_items(self) -> list[ReviewSpec]:
            return []

        def risk_profile(self) -> str | None:
            return None

        def initial_charge(self) -> str | None:
            return None

        def client_names(self) -> set[str]:
            return set()

        def excluded_item_subjects(self) -> set[str]:
            return set()

    assert _g2(ReportBundle(report_text="It is £1."), cast(Truth, _OldTruth())) is True


# --- pipeline mode (LedgerTruth) -----------------------------------------------------------


def _value(amount: str, qualifier: Qualifier = "exact") -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision="exact" if qualifier == "exact" else "approximate",
        qualifier=qualifier,
        date=None,
        source_id="s",
        quote="",
        selected_by="R3",
    )


def _ledger() -> Ledger:
    account = Account(id="A", owners=["A B"], type="General Investment Account", in_scope=True)
    return Ledger(
        client="c",
        accounts=[account],
        facts={
            "account.A.value": Fact(
                id="account.A.value",
                kind="money",
                description="value",
                value=_value("45000", "circa"),
                reportable=True,
                role="account value",
            ),
            "account.A.superseded.1": Fact(
                id="account.A.superseded.1",
                kind="money",
                description="superseded",
                value=_value("40000"),
                reportable=True,
                role="superseded value",
                placement="footnote_only",
            ),
        },
    )


_TABLE = f"{TABLE_HEADER}\n|---|---|---|---|\n| A | A B | GIA | c. £45,000 |"


def _report(background_tail: str, elsewhere: str) -> ReportBundle:
    background = f"Summary.\n\n{_TABLE}\n\n{background_tail}"
    sections = {"background_objectives": background, "recommendations": elsewhere}
    return ReportBundle(report_text="\n\n".join(sections.values()), sections=sections)


def test_ledger_truth_lists_only_the_footnote_only_figures() -> None:
    assert LedgerTruth(_ledger()).footnote_only_figures() == {"£40,000"}


def test_ledger_truth_allows_the_figure_in_the_footnote_after_the_table() -> None:
    bundle = _report("Your joint GIA was previously shown as £40,000.", "We recommend a review.")
    assert _g2(bundle, LedgerTruth(_ledger())) is True


def test_ledger_truth_rejects_the_figure_anywhere_else() -> None:
    bundle = _report("(no footnote)", "It used to be £40,000.")
    assert _g2(bundle, LedgerTruth(_ledger())) is False


def test_the_footnote_zone_falls_back_to_the_text_after_the_table_without_sections() -> None:
    text = f"Summary.\n\n{_TABLE}\n\nPreviously £40,000."
    truth = LedgerTruth(_ledger())
    assert _g2(ReportBundle(report_text=text), truth) is True
    assert _g2(ReportBundle(report_text="Earlier it was £40,000. " + text), truth) is False
