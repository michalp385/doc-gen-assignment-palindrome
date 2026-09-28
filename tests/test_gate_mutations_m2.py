"""Broken-report tests for every deterministic gate, run across all four real clients' reference
bundles (T24, DESIGN.md section 10.5).

`tests/test_gate_mutations.py` (T9) runs each mutation on client 01's bundle only, and covers
the cases client 01's data can't express with a hand-built `_StubTruth`. This file adds the
rest of DESIGN's table on clients 02-04's own bundles, where an approximate value, a footnote,
a new account, a tangent, a blocking review item or a transaction amount really exist. Each
mutation breaks one thing and asserts *at least* its intended gate fails (several
legitimately trip more than one). The clean bundle passing every gate is what shows the
gates don't over-fire; that too is asserted per client.

A mutation whose precondition a client's data doesn't meet (no joint account, no footnote) is
parametrized only over the clients that meet it, computed from each client's own truth, never
skipped.

Judge mutations (G7, G8, G12's judge part, G16, the G2 role check, G4/G10 paraphrase) are
recorded live and replayed from the cache: not offline work, so not here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

from agent_pipeline.gates.deterministic import (
    FCA_LINE,
    RISK_WARNING_FULL,
    TABLE_HEADER,
    ReportBundle,
    TableRow,
    run_gates,
    word_ngrams,
)
from agent_pipeline.ledger import Marker
from report_eval.reference import build_reference_bundle
from report_eval.truth import ExpectedTruth

CLIENTS = ["client_01_clean", "client_02_medium", "client_03_hard", "client_04_stretch"]
BUILT = {client: build_reference_bundle(client) for client in CLIENTS}

ALL_GATES = {
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G9",
    "G10",
    "G11",
    "G12",
    "G13",
    "G14",
    "G15",
    "P6",
}


def _clients_where(predicate: Callable[[ReportBundle, ExpectedTruth], bool]) -> list[str]:
    return [c for c in CLIENTS if predicate(*BUILT[c])]


def _passed(bundle: ReportBundle, truth: ExpectedTruth, gate: str) -> bool:
    return {r.gate: r for r in run_gates(bundle, truth)}[gate].passed


def _edit_section(bundle: ReportBundle, section: str, edit: Callable[[str], str]) -> ReportBundle:
    """Edits one section's text and the report text consistently."""
    old = bundle.sections[section]
    new = edit(old)
    assert old in bundle.report_text
    return dataclasses.replace(
        bundle,
        report_text=bundle.report_text.replace(old, new, 1),
        sections={**bundle.sections, section: new},
    )


def _append(bundle: ReportBundle, text: str) -> ReportBundle:
    return dataclasses.replace(bundle, report_text=bundle.report_text + text)


def _with_rows(bundle: ReportBundle, rows: list[TableRow]) -> ReportBundle:
    return dataclasses.replace(bundle, table_rows=rows)


# --- the clean bundles ---------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_the_reference_bundle_passes_every_gate(client: str) -> None:
    bundle, truth = BUILT[client]
    results = run_gates(bundle, truth)
    assert [r for r in results if not r.passed] == []
    assert {r.gate for r in results} == ALL_GATES


@pytest.mark.parametrize("client", CLIENTS)
def test_the_reference_table_rows_match_the_expected_facts(client: str) -> None:
    bundle, truth = BUILT[client]
    assert [(r.account_id, r.owners, r.value_text) for r in bundle.table_rows] == [
        (a.id, a.owners, a.value_text) for a in truth.table_accounts()
    ]


# --- G1 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g1_out_of_scope_account_added(client: str) -> None:
    bundle, truth = BUILT[client]
    extra = TableRow(account_id="X-OUT-OF-SCOPE", owners=["Someone Else"], value_text="£1")
    assert not _passed(_with_rows(bundle, [*bundle.table_rows, extra]), truth, "G1")


@pytest.mark.parametrize("client", CLIENTS)
def test_g1_account_listed_twice(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_with_rows(bundle, bundle.table_rows * 2), truth, "G1")


@pytest.mark.parametrize("client", CLIENTS)
def test_g1_in_scope_row_dropped(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_with_rows(bundle, bundle.table_rows[1:]), truth, "G1")


@pytest.mark.parametrize(
    "client", _clients_where(lambda b, t: any(len(r.owners) > 1 for r in b.table_rows))
)
def test_g1_joint_account_shown_with_joint_as_owner(client: str) -> None:
    bundle, truth = BUILT[client]
    rows = [
        dataclasses.replace(r, owners=["Joint"]) if len(r.owners) > 1 else r
        for r in bundle.table_rows
    ]
    assert not _passed(_with_rows(bundle, rows), truth, "G1")


# --- G2 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g2_distractor_figure(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " An extra £999 applies."), truth, "G2")


@pytest.mark.parametrize("client", CLIENTS)
def test_g2_shorthand_k_figure(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " Illustrative future value: £45k."), truth, "G2")


@pytest.mark.parametrize("client", CLIENTS)
def test_g2_figure_written_in_words(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " We recommend moving twenty thousand pounds."), truth, "G2")


@pytest.mark.parametrize("client", CLIENTS)
def test_g2_distractor_percentage(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " A further 7.5% applies."), truth, "G2")


@pytest.mark.parametrize(
    "client",
    _clients_where(lambda b, t: any(r.value_text.startswith("c. ") for r in b.table_rows)),
)
def test_g2_approximate_figure_written_without_its_qualifier(client: str) -> None:
    bundle, truth = BUILT[client]
    plain = next(r.value_text for r in bundle.table_rows if r.value_text.startswith("c. "))[3:]
    assert not _passed(_append(bundle, f" It is worth {plain}."), truth, "G2")


# --- G3 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g3_cgt_amount(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " The CGT due is £1,200."), truth, "G3")


@pytest.mark.parametrize("client", CLIENTS)
def test_g3_cgt_rate(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " Capital gains tax applies at 20%."), truth, "G3")


@pytest.mark.parametrize("client", CLIENTS)
def test_g3_platform_charge_rate(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " The platform charge is 0.5%."), truth, "G3")


@pytest.mark.parametrize("client", CLIENTS)
def test_g3_advice_charge_rate(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " The advice charge is 1%."), truth, "G3")


# --- G4 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g4_risk_warning_removed(client: str) -> None:
    bundle, truth = BUILT[client]
    mutated = dataclasses.replace(
        bundle, report_text=bundle.report_text.replace(RISK_WARNING_FULL, "")
    )
    assert not _passed(mutated, truth, "G4")


@pytest.mark.parametrize("client", CLIENTS)
def test_g4_fca_line_removed(client: str) -> None:
    bundle, truth = BUILT[client]
    mutated = dataclasses.replace(bundle, report_text=bundle.report_text.replace(FCA_LINE, ""))
    assert not _passed(mutated, truth, "G4")


@pytest.mark.parametrize("client", CLIENTS)
def test_g4_fca_line_duplicated(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " " + FCA_LINE), truth, "G4")


@pytest.mark.parametrize("client", CLIENTS)
def test_g4_paraphrased_warning_added(client: str) -> None:
    bundle, truth = BUILT[client]
    paraphrase = (
        " The value of an investment can fall as well as rise, so you may get back less "
        "than you originally invested."
    )
    assert not _passed(_append(bundle, paraphrase), truth, "G4")


# --- G5 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", _clients_where(lambda b, t: t.tax_section_expected()))
def test_g5_tax_section_dropped_when_required(client: str) -> None:
    bundle, truth = BUILT[client]
    text = bundle.sections["tax_implications"]
    mutated = dataclasses.replace(
        bundle,
        report_text=bundle.report_text.replace(text, ""),
        sections={k: v for k, v in bundle.sections.items() if k != "tax_implications"},
    )
    assert not _passed(mutated, truth, "G5")


@pytest.mark.parametrize("client", _clients_where(lambda b, t: not t.tax_section_expected()))
def test_g5_tax_section_added_when_not_required(client: str) -> None:
    bundle, truth = BUILT[client]
    mutated = dataclasses.replace(
        bundle, sections={**bundle.sections, "tax_implications": "A disposal may create tax."}
    )
    assert not _passed(mutated, truth, "G5")


# --- G6 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g6_wrong_value_shown(client: str) -> None:
    bundle, truth = BUILT[client]
    rows = [dataclasses.replace(bundle.table_rows[0], value_text="£1"), *bundle.table_rows[1:]]
    assert not _passed(_with_rows(bundle, rows), truth, "G6")


@pytest.mark.parametrize(
    "client",
    _clients_where(lambda b, t: any(r.value_text.startswith("c. ") for r in b.table_rows)),
)
def test_g6_c_dropped_from_an_approximate_value(client: str) -> None:
    bundle, truth = BUILT[client]
    rows = [
        dataclasses.replace(r, value_text=r.value_text[3:]) if r.value_text.startswith("c. ") else r
        for r in bundle.table_rows
    ]
    assert not _passed(_with_rows(bundle, rows), truth, "G6")


@pytest.mark.parametrize(
    "client", _clients_where(lambda b, t: any(a.superseded_texts for a in t.table_accounts()))
)
def test_g6_selected_value_swapped_for_the_superseded_one(client: str) -> None:
    bundle, truth = BUILT[client]
    superseded = next(
        f.value
        for f in truth._facts.reportable_figures  # noqa: SLF001
        if f.placement == "footnote_only"
    )
    rows = [
        dataclasses.replace(r, value_text=superseded) if r.value_text.startswith("c. ") else r
        for r in bundle.table_rows
    ]
    assert not _passed(_with_rows(bundle, rows), truth, "G6")


# --- G9 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", _clients_where(lambda b, t: bool(t.transaction_figures())))
def test_g9_transaction_amount_in_background(client: str) -> None:
    bundle, truth = BUILT[client]
    figure = sorted(truth.transaction_figures())[0]
    mutated = _edit_section(
        bundle, "background_objectives", lambda s: s + f" This includes {figure}."
    )
    assert not _passed(mutated, truth, "G9")


# --- G10 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g10_guidance_text_pasted_in(client: str) -> None:
    bundle, truth = BUILT[client]
    screened = word_ngrams(bundle.internal_guidance_text, 6) - (
        word_ngrams(bundle.meeting_text, 6) | word_ngrams(bundle.spec_text, 6)
    )
    assert screened, "precondition: the guidance holds text found in neither meeting nor spec"
    pasted = " ".join(sorted(screened)[0])
    assert not _passed(_append(bundle, f" {pasted}."), truth, "G10")


# --- G11 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g11_second_table_added(client: str) -> None:
    bundle, truth = BUILT[client]
    second = f"\n\n{TABLE_HEADER}\n|---|---|---|---|\n| X-1 | A | B | £1 |\n"
    assert not _passed(_append(bundle, second), truth, "G11")


@pytest.mark.parametrize("client", CLIENTS)
def test_g11_risk_warning_moved_into_recommendations(client: str) -> None:
    bundle, truth = BUILT[client]
    mutated = _edit_section(bundle, "recommendations", lambda s: s + " " + RISK_WARNING_FULL)
    assert not _passed(mutated, truth, "G11")


@pytest.mark.parametrize("client", CLIENTS)
def test_g11_fca_line_moved_into_recommendations(client: str) -> None:
    bundle, truth = BUILT[client]
    mutated = _edit_section(bundle, "recommendations", lambda s: s + " " + FCA_LINE)
    assert not _passed(mutated, truth, "G11")


@pytest.mark.parametrize("client", CLIENTS)
def test_g11_table_moved_into_recommendations(client: str) -> None:
    bundle, truth = BUILT[client]
    table = f"\n\n{TABLE_HEADER}\n|---|---|---|---|\n"
    mutated = _edit_section(bundle, "recommendations", lambda s: s + table)
    # the report now holds the table twice, and once outside Background
    assert not _passed(mutated, truth, "G11")


# --- G12 (deterministic slice) -------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g12_capitalised_sentence_starts_mid_sentence(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " in relation to This report relates to you."), truth, "G12")


@pytest.mark.parametrize("client", CLIENTS)
def test_g12_double_full_stop(client: str) -> None:
    bundle, truth = BUILT[client]
    assert not _passed(_append(bundle, " This is fine.. Really."), truth, "G12")


# --- G13 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g13_risk_profile_label_changed(client: str) -> None:
    bundle, truth = BUILT[client]
    risk = truth.risk_profile()
    assert risk is not None
    mutated = dataclasses.replace(
        bundle, report_text=bundle.report_text.replace(risk, "3 (cautious)")
    )
    assert not _passed(mutated, truth, "G13")


@pytest.mark.parametrize("client", CLIENTS)
def test_g13_initial_charge_changed(client: str) -> None:
    bundle, truth = BUILT[client]
    charge = truth.initial_charge()
    assert charge is not None
    mutated = dataclasses.replace(bundle, report_text=bundle.report_text.replace(charge, "9.9%"))
    assert not _passed(mutated, truth, "G13")


@pytest.mark.parametrize("client", CLIENTS)
def test_g13_every_client_name_is_checked(client: str) -> None:
    bundle, truth = BUILT[client]
    for name in sorted(truth.client_names()):
        mutated = dataclasses.replace(
            bundle, report_text=bundle.report_text.replace(name, name[:-2])
        )
        assert not _passed(mutated, truth, "G13"), name


@pytest.mark.parametrize(
    "client", _clients_where(lambda b, t: any(a.is_new for a in t.table_accounts()))
)
def test_g13_new_account_not_shown_as_to_be_opened(client: str) -> None:
    bundle, truth = BUILT[client]
    rows = [
        dataclasses.replace(r, value_text="marker") if r.value_text == "To be opened" else r
        for r in bundle.table_rows
    ]
    assert not _passed(_with_rows(bundle, rows), truth, "G13")


# --- G14 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g14_required_marker_removed(client: str) -> None:
    bundle, truth = BUILT[client]
    ledger = bundle.ledger.model_copy(update={"markers": bundle.ledger.markers[1:]})
    assert not _passed(dataclasses.replace(bundle, ledger=ledger), truth, "G14")


@pytest.mark.parametrize("client", CLIENTS)
def test_g14_marker_added_for_a_settled_value(client: str) -> None:
    bundle, truth = BUILT[client]
    extra = Marker(id="#99", key="settled_thing", text="something settled", reason="", section="")
    ledger = bundle.ledger.model_copy(update={"markers": [*bundle.ledger.markers, extra]})
    assert not _passed(dataclasses.replace(bundle, ledger=ledger), truth, "G14")


# --- G15 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_g15_expected_review_rows_dropped(client: str) -> None:
    bundle, truth = BUILT[client]
    kept = [r for r in bundle.ledger.review if r.kind == "marker_reference"]
    ledger = bundle.ledger.model_copy(update={"review": kept})
    assert not _passed(dataclasses.replace(bundle, ledger=ledger), truth, "G15")


@pytest.mark.parametrize(
    "client", _clients_where(lambda b, t: any(r.blocking for r in t.expected_review_items()))
)
def test_g15_blocking_flag_dropped(client: str) -> None:
    bundle, truth = BUILT[client]
    review = [r.model_copy(update={"blocking": False}) for r in bundle.ledger.review]
    ledger = bundle.ledger.model_copy(update={"review": review})
    assert not _passed(dataclasses.replace(bundle, ledger=ledger), truth, "G15")


@pytest.mark.parametrize("client", CLIENTS)
def test_g15_marker_without_a_review_row(client: str) -> None:
    bundle, truth = BUILT[client]
    first = bundle.ledger.markers[0].key
    kept = [r for r in bundle.ledger.review if first not in r.refs]
    ledger = bundle.ledger.model_copy(update={"review": kept})
    assert not _passed(dataclasses.replace(bundle, ledger=ledger), truth, "G15")


# --- P6 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("client", _clients_where(lambda b, t: bool(t.tangent_subjects())))
def test_p6_a_tangent_appears_in_the_report(client: str) -> None:
    bundle, truth = BUILT[client]
    subject = sorted(truth.tangent_subjects())[0]
    mutated = _edit_section(
        bundle, "recommendations", lambda s: s + f" We also discussed {subject}."
    )
    assert not _passed(mutated, truth, "P6")


@pytest.mark.parametrize("client", _clients_where(lambda b, t: bool(t.excluded_item_subjects())))
def test_p6_an_aspiration_appears_twice(client: str) -> None:
    bundle, truth = BUILT[client]
    subject = sorted(truth.excluded_item_subjects())[0]
    mutated = _edit_section(
        bundle, "background_objectives", lambda s: s + f" They mentioned {subject} again."
    )
    assert not _passed(mutated, truth, "P6")


@pytest.mark.parametrize("client", _clients_where(lambda b, t: bool(t.excluded_item_subjects())))
def test_p6_an_aspiration_appears_outside_background(client: str) -> None:
    bundle, truth = BUILT[client]
    subject = sorted(truth.excluded_item_subjects())[0]
    mutated = _edit_section(
        bundle, "recommendations", lambda s: s + f" We also discussed {subject}."
    )
    assert not _passed(mutated, truth, "P6")
