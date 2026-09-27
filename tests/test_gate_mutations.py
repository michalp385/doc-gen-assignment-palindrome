"""Broken-report tests for every deterministic gate T9 implements (DESIGN.md section 10.5).

`build_reference_bundle` builds client 01's known-correct bundle straight from its expected
facts, with no LLM involved. It must pass every gate (this also shows the gates don't
over-fire). Each mutation below breaks one thing and asserts *at least* its intended gate
fails -- several legitimately trip more than one (DESIGN's own point: requiring exclusivity
would push toward weakening gates), so only the intended gate is asserted.

Not every DESIGN-table mutation has a natural home in client 01's own data (e.g. it has no
approximate value and no new account); those are covered by a small hand-built `_StubTruth`
instead of forcing an artificial case onto client 01's reference bundle.
"""

from __future__ import annotations

import dataclasses

from agent_pipeline.gates.deterministic import (
    FCA_LINE,
    RISK_WARNING_FULL,
    TABLE_HEADER,
    GateResult,
    ReportBundle,
    TableRow,
    run_gates,
)
from agent_pipeline.gates.truth import LedgerTruth, MarkerSpec, ReviewSpec, TableAccount
from agent_pipeline.ledger import Account, Ledger, Marker, ReviewItem
from report_eval.reference import build_reference_bundle
from report_eval.truth import ExpectedTruth

BUNDLE, TRUTH = build_reference_bundle("client_01_clean")


def _results_by_gate(bundle: ReportBundle, truth: object) -> dict[str, GateResult]:
    return {r.gate: r for r in run_gates(bundle, truth)}  # type: ignore[arg-type]


def test_the_reference_bundle_passes_every_gate() -> None:
    results = run_gates(BUNDLE, TRUTH)
    failed = [r for r in results if not r.passed]
    assert failed == []
    assert {r.gate for r in results} == {
        "G1", "G2", "G3", "G4", "G5", "G6", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "P6",
    }  # fmt: skip


def test_g2_allows_a_qualifier_prefixed_figure() -> None:
    # verifier report (M0b checkpoint), finding #1: _MONEY_RE used to extract only the bare
    # amount, so a genuinely reportable approximate value (client 01 has none -- built
    # directly) never matched the allowed set's qualifier-prefixed string, and G2 false-failed
    # on every client with an approximate figure -- most real and synthetic clients.
    bundle = ReportBundle(
        report_text="The joint GIA is worth c. £45,000 and the ISA is up to £400,000."
    )
    truth = _StubTruth(reportable_figures={"c. £45,000", "up to £400,000"})
    assert _results_by_gate(bundle, truth)["G2"].passed is True


# --- G1: the table is exactly the in-scope accounts, each once, owners named -------------


def test_g1_out_of_scope_account_added() -> None:
    mutated = dataclasses.replace(
        BUNDLE,
        table_rows=[
            *BUNDLE.table_rows,
            TableRow(account_id="H-CASH-01", owners=["Margaret Hughes"], value_text="£25,000"),
        ],
    )
    assert _results_by_gate(mutated, TRUTH)["G1"].passed is False


def test_g1_account_listed_twice() -> None:
    mutated = dataclasses.replace(BUNDLE, table_rows=BUNDLE.table_rows * 2)
    assert _results_by_gate(mutated, TRUTH)["G1"].passed is False


def test_g1_joint_shown_as_owner() -> None:
    mutated = dataclasses.replace(
        BUNDLE, table_rows=[dataclasses.replace(BUNDLE.table_rows[0], owners=["Joint"])]
    )
    assert _results_by_gate(mutated, TRUTH)["G1"].passed is False


def test_g1_in_scope_row_dropped() -> None:
    mutated = dataclasses.replace(BUNDLE, table_rows=[])
    assert _results_by_gate(mutated, TRUTH)["G1"].passed is False


# --- G2: every money/percent figure in the report is a reportable figure -----------------


def test_g2_distractor_figure() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " An extra £999 applies."
    )
    assert _results_by_gate(mutated, TRUTH)["G2"].passed is False


def test_g2_superseded_value_outside_the_footnote() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " It was previously valued at £49,000."
    )
    assert _results_by_gate(mutated, TRUTH)["G2"].passed is False


def test_g2_shorthand_k_figure() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " Illustrative future value: £45k."
    )
    assert _results_by_gate(mutated, TRUTH)["G2"].passed is False


def test_g2_figure_written_in_words() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " We recommend moving twenty thousand pounds."
    )
    assert _results_by_gate(mutated, TRUTH)["G2"].passed is False


# --- G3: CGT/platform/advice-charge rates never appear as figures ------------------------


def test_g3_cgt_amount() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " The CGT due is £1,200."
    )
    assert _results_by_gate(mutated, TRUTH)["G3"].passed is False


def test_g3_cgt_rate() -> None:
    mutated = dataclasses.replace(BUNDLE, report_text=BUNDLE.report_text + " CGT applies at 20%.")
    assert _results_by_gate(mutated, TRUTH)["G3"].passed is False


def test_g3_platform_charge_rate() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " The platform charge is 0.5%."
    )
    assert _results_by_gate(mutated, TRUTH)["G3"].passed is False


# --- G4: the FCA line and risk warning appear verbatim, exactly once each ----------------


def test_g4_risk_warning_removed() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text.replace(RISK_WARNING_FULL, "")
    )
    assert _results_by_gate(mutated, TRUTH)["G4"].passed is False


def test_g4_fca_line_duplicated() -> None:
    mutated = dataclasses.replace(BUNDLE, report_text=BUNDLE.report_text + " " + FCA_LINE)
    assert _results_by_gate(mutated, TRUTH)["G4"].passed is False


def test_g4_paraphrased_warning_added() -> None:
    paraphrase = (
        "The value of an investment can fall as well as rise, so you may get back less than "
        "you originally invested."
    )
    mutated = dataclasses.replace(BUNDLE, report_text=BUNDLE.report_text + " " + paraphrase)
    assert _results_by_gate(mutated, TRUTH)["G4"].passed is False


# --- G5: Tax Implications is present iff a taxable disposal is expected ------------------


def test_g5_tax_section_added_when_not_expected() -> None:
    mutated = dataclasses.replace(
        BUNDLE, sections={**BUNDLE.sections, "tax_implications": "A disposal may create CGT."}
    )
    assert _results_by_gate(mutated, TRUTH)["G5"].passed is False


def test_g5_tax_section_dropped_when_expected() -> None:
    # Client 01 never expects a Tax section, so this exercises the mirror case by expecting
    # one instead: the bundle (correctly, for this client) has none.
    facts = TRUTH._facts.model_copy(update={"sections": {"tax_implications": True}})  # noqa: SLF001
    truth_expecting_tax = ExpectedTruth(facts)
    assert _results_by_gate(BUNDLE, truth_expecting_tax)["G5"].passed is False


# --- G6: each account shows the trust rules' selected value, rendered correctly ----------


def test_g6_wrong_value_shown() -> None:
    mutated = dataclasses.replace(
        BUNDLE,
        table_rows=[dataclasses.replace(BUNDLE.table_rows[0], value_text="£49,000")],
    )
    assert _results_by_gate(mutated, TRUTH)["G6"].passed is False


def test_g6_c_dropped_from_an_approximate_value() -> None:
    # Client 01 has no approximate value; built directly, not from the reference bundle.
    bundle = ReportBundle(
        report_text="",
        table_rows=[TableRow(account_id="X-1", owners=["Test Person"], value_text="£45,000")],
    )
    truth = _StubTruth(
        table_accounts=[TableAccount(id="X-1", owners=["Test Person"], value_text="c. £45,000")]
    )
    assert _results_by_gate(bundle, truth)["G6"].passed is False


# --- G9: Background contains no transaction amounts --------------------------------------


def test_g9_transaction_amount_in_background() -> None:
    mutated = dataclasses.replace(
        BUNDLE,
        sections={
            **BUNDLE.sections,
            "background_objectives": BUNDLE.sections["background_objectives"]
            + " This includes this year's £20,000 top-up.",
        },
    )
    assert _results_by_gate(mutated, TRUTH)["G9"].passed is False


# --- G10: internal guidance text never appears in the report -----------------------------


def test_g10_guidance_sentence_pasted_in() -> None:
    guidance_sentence = (
        "I have already put it into the template config as static text, so leave it "
        "exactly as it is: do not paraphrase it, and do not let the model rewrite it when "
        "you change how the sections are generated."
    )
    # normalise whitespace: fde_notes.md wraps this sentence across source lines
    assert guidance_sentence in " ".join(BUNDLE.internal_guidance_text.split())
    mutated = dataclasses.replace(BUNDLE, report_text=BUNDLE.report_text + " " + guidance_sentence)
    assert _results_by_gate(mutated, TRUTH)["G10"].passed is False


# --- G11: each section holds only its own content; the table appears once ----------------


def test_g11_second_table_added() -> None:
    second_table = f"\n\n{TABLE_HEADER}\n|---|---|---|---|\n| X-1 | A | B | £1 |\n"
    mutated = dataclasses.replace(BUNDLE, report_text=BUNDLE.report_text + second_table)
    assert _results_by_gate(mutated, TRUTH)["G11"].passed is False


def test_g11_risk_warning_moved_into_recommendations() -> None:
    mutated = dataclasses.replace(
        BUNDLE,
        sections={
            **BUNDLE.sections,
            "recommendations": BUNDLE.sections["recommendations"] + " " + RISK_WARNING_FULL,
        },
    )
    assert _results_by_gate(mutated, TRUTH)["G11"].passed is False


# --- G12 (deterministic slice): placeholder-substitution artifacts -----------------------


def test_g12_capitalised_sentence_starts_mid_sentence() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " in relation to This report relates to you."
    )
    assert _results_by_gate(mutated, TRUTH)["G12"].passed is False


def test_g12_double_full_stop() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text + " This is fine.. Really."
    )
    assert _results_by_gate(mutated, TRUTH)["G12"].passed is False


# --- G13: risk profile, initial charge and client names match verbatim -------------------


def test_g13_risk_profile_label_changed() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text.replace("4 (moderate)", "3 (cautious)")
    )
    assert _results_by_gate(mutated, TRUTH)["G13"].passed is False


def test_g13_name_misspelled() -> None:
    mutated = dataclasses.replace(
        BUNDLE, report_text=BUNDLE.report_text.replace("Margaret Hughes", "Margaret Hugh")
    )
    assert _results_by_gate(mutated, TRUTH)["G13"].passed is False


def test_g13_new_account_missing_to_be_opened() -> None:
    # Client 01 has no new account; built directly, not from the reference bundle.
    bundle = ReportBundle(
        report_text="",
        table_rows=[TableRow(account_id="new:gia", owners=["Test Person"], value_text="marker")],
    )
    truth = _StubTruth(
        table_accounts=[TableAccount(id="new:gia", owners=["Test Person"], value_text="marker")]
    )
    assert _results_by_gate(bundle, truth)["G13"].passed is False


# --- G14: every expected marker is present; nothing settled carries one ------------------


def test_g14_required_marker_removed() -> None:
    mutated = dataclasses.replace(
        BUNDLE, ledger=BUNDLE.ledger.model_copy(update={"markers": BUNDLE.ledger.markers[:1]})
    )
    assert _results_by_gate(mutated, TRUTH)["G14"].passed is False


def test_g14_marker_added_for_a_settled_value() -> None:
    extra = Marker(
        id="#3", key="settled_thing", text="something the sources settle", reason="", section=""
    )
    mutated = dataclasses.replace(
        BUNDLE,
        ledger=BUNDLE.ledger.model_copy(update={"markers": [*BUNDLE.ledger.markers, extra]}),
    )
    assert _results_by_gate(mutated, TRUTH)["G14"].passed is False


# --- G15: every expected review item is present; every marker has a review row -----------


def test_g15_required_review_row_dropped() -> None:
    kept = [r for r in BUNDLE.ledger.review if r.kind != "p4_note"]
    mutated = dataclasses.replace(BUNDLE, ledger=BUNDLE.ledger.model_copy(update={"review": kept}))
    assert _results_by_gate(mutated, TRUTH)["G15"].passed is False


def test_g15_blocking_flag_dropped() -> None:
    # Client 01's only required review item is non-blocking, so this exercises the mirror
    # case by expecting `blocking=True` instead: the bundle (correctly) has it False.
    facts = TRUTH._facts.model_copy(  # noqa: SLF001
        update={
            "review_items": [
                r.model_copy(update={"blocking": True})
                for r in TRUTH._facts.review_items  # noqa: SLF001
            ]
        }
    )
    assert _results_by_gate(BUNDLE, ExpectedTruth(facts))["G15"].passed is False


def test_g15_marker_without_a_review_row() -> None:
    kept = [r for r in BUNDLE.ledger.review if "platform_charge_holloway" not in r.refs]
    mutated = dataclasses.replace(BUNDLE, ledger=BUNDLE.ledger.model_copy(update={"review": kept}))
    assert _results_by_gate(mutated, TRUTH)["G15"].passed is False


# --- P6: an aspiration's subject appears at most once, and only in Background ------------


def test_p6_aspiration_subject_appears_twice() -> None:
    mutated = dataclasses.replace(
        BUNDLE,
        sections={
            **BUNDLE.sections,
            "background_objectives": BUNDLE.sections["background_objectives"]
            + " She mentioned gifting to her grandchildren again.",
        },
    )
    assert _results_by_gate(mutated, TRUTH)["P6"].passed is False


def test_p6_aspiration_mentioned_outside_background() -> None:
    mutated = dataclasses.replace(
        BUNDLE,
        sections={
            **BUNDLE.sections,
            "recommendations": BUNDLE.sections["recommendations"]
            + " We also discussed gifting to her grandchildren.",
        },
    )
    assert _results_by_gate(mutated, TRUTH)["P6"].passed is False


# --- LedgerTruth: must be usable, not dead code (full pipeline-mode exercise is T10+) ----


def test_ledger_truth_reflects_a_hand_built_ledger() -> None:
    ledger = Ledger(
        client="client_01_clean",
        risk_profile="4 (moderate)",
        initial_charge="0%",
        tax_section=False,
        accounts=[
            Account(
                id="H-ISA-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                platform="Holloway",
                in_scope=True,
            )
        ],
        markers=[
            Marker(
                id="#1",
                key="advice_charge",
                text="ongoing advice charge rate",
                reason="",
                section="",
            )
        ],
        review=[ReviewItem(id="rv1", kind="marker_reference", refs=["advice_charge"])],
    )
    truth = LedgerTruth(ledger)
    assert [a.id for a in truth.table_accounts()] == ["H-ISA-01"]
    assert truth.client_names() == {"Margaret Hughes"}
    assert truth.risk_profile() == "4 (moderate)"
    assert truth.initial_charge() == "0%"
    assert truth.tax_section_expected() is False
    assert [m.key for m in truth.required_markers()] == ["advice_charge"]
    assert [r.key for r in truth.expected_review_items()] == ["rv1"]
    assert truth.excluded_item_subjects() == set()


class _StubTruth:
    """A hand-built `Truth` for a case client 01's own data can't express, used only by the
    two mutations above that need it (G6's "c." handling, G13's new-account handling)."""

    def __init__(
        self,
        table_accounts: list[TableAccount] | None = None,
        reportable_figures: set[str] | None = None,
        transaction_figures: set[str] | None = None,
        tax_section_expected: bool = False,
        required_markers: list[MarkerSpec] | None = None,
        expected_review_items: list[ReviewSpec] | None = None,
        risk_profile: str | None = None,
        initial_charge: str | None = None,
        client_names: set[str] | None = None,
        excluded_item_subjects: set[str] | None = None,
    ) -> None:
        self._table_accounts = table_accounts or []
        self._reportable_figures = reportable_figures or set()
        self._transaction_figures = transaction_figures or set()
        self._tax_section_expected = tax_section_expected
        self._required_markers = required_markers or []
        self._expected_review_items = expected_review_items or []
        self._risk_profile = risk_profile
        self._initial_charge = initial_charge
        self._client_names = client_names or set()
        self._excluded_item_subjects = excluded_item_subjects or set()

    def table_accounts(self) -> list[TableAccount]:
        return self._table_accounts

    def reportable_figures(self) -> set[str]:
        return self._reportable_figures

    def transaction_figures(self) -> set[str]:
        return self._transaction_figures

    def tax_section_expected(self) -> bool:
        return self._tax_section_expected

    def required_markers(self) -> list[MarkerSpec]:
        return self._required_markers

    def expected_review_items(self) -> list[ReviewSpec]:
        return self._expected_review_items

    def risk_profile(self) -> str | None:
        return self._risk_profile

    def initial_charge(self) -> str | None:
        return self._initial_charge

    def client_names(self) -> set[str]:
        return self._client_names

    def excluded_item_subjects(self) -> set[str]:
        return self._excluded_item_subjects
