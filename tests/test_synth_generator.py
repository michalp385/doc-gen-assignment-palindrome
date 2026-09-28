"""The synthetic client generator (T27, D4, DESIGN.md section 10.8), tests first and offline.

A seeded scenario sampler varies the SCOPING section 5 patterns; from a scenario, code writes
the account JSON, the report-instruction table and the statement image, and derives the
expected facts. An LLM writes the meeting note around required phrases (not exercised here:
the live one-off generation is out of scope); code checks every required phrase is present
verbatim and no unplanned figure appears (`check_prose`). The phrase bank has no six-word
overlap with the real clients' documents.
"""

from __future__ import annotations

import filecmp
import json
from pathlib import Path

import pytest

from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.json_accounts import read_accounts
from report_eval.expected import ExpectedFacts
from report_eval.synth.phrases import PHRASE_BANK, bank_overlap, corpus_texts
from report_eval.synth.prose import ProseRejected, check_prose, generate_prose
from report_eval.synth.scenario import (
    Scenario,
    account_data,
    brief,
    distractor_text,
    expected_facts,
    instruction_fields,
    required_phrases,
    sample_scenario,
)
from report_eval.synth.writers import write_client

SEEDS = list(range(1, 41))


def _good_note(scenario: Scenario) -> str:
    """What a well-behaved prose model returns: every required phrase, nothing else with a
    figure."""
    phrases = [p.text for p in required_phrases(scenario)]
    return "\n\n".join(["Review meeting held.", *phrases, "Next steps: prepare the report."])


# --- the sampler ---------------------------------------------------------------------------


def test_the_same_seed_gives_the_same_scenario() -> None:
    assert sample_scenario(7) == sample_scenario(7)


def test_different_seeds_give_different_clients() -> None:
    assert len({sample_scenario(s).client_id for s in SEEDS}) == len(SEEDS)


def test_the_sampler_covers_the_patterns_the_pipeline_must_handle() -> None:
    scenarios = [sample_scenario(s) for s in SEEDS]
    assert {s.advice for s in scenarios} == {"topup", "gia_sale"}
    assert any(len(s.holders) == 2 for s in scenarios)
    assert any(len(s.holders) == 1 for s in scenarios)
    assert any(s.new_account for s in scenarios)
    assert any(s.null_cash for s in scenarios)
    assert any(s.closed_cash for s in scenarios)
    assert any(s.money for s in scenarios)
    assert any(s.tangent for s in scenarios)
    assert any(s.aspiration for s in scenarios)
    assert any(s.recalled_decoy for s in scenarios)


def test_the_generator_holds_no_real_client_names() -> None:
    real = {
        "Margaret Hughes",
        "David Clarke",
        "Susan Clarke",
        "Robert Fletcher",
        "Jean Fletcher",
        "James Whitmore",
        "Caroline Whitmore",
        "Daniel Reeves",
    }
    for seed in SEEDS:
        s = sample_scenario(seed)
        assert not real & set(s.holders)
        assert s.adviser not in real


# --- account data and the instruction ------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_account_data_is_readable_and_joint_accounts_sit_under_both_holders(
    seed: int, tmp_path: Path
) -> None:
    scenario = sample_scenario(seed)
    path = tmp_path / "client_data_db.json"
    path.write_text(json.dumps(account_data(scenario)), encoding="utf-8")
    data = read_accounts(path)
    assert {h.name for h in data.holders.values()} == set(scenario.holders)
    joint = [a for a in scenario.accounts if len(a.owners) > 1]
    for account in joint:
        copies = [
            r for h in data.holders.values() for r in h.accounts if r.account_id == account.id
        ]
        assert len(copies) == len(account.owners)
        assert {r.owner for r in copies} == {"Joint"}


@pytest.mark.parametrize("seed", SEEDS)
def test_the_instruction_carries_the_fields_a_real_request_does(seed: int) -> None:
    fields = dict(instruction_fields(sample_scenario(seed)))
    for label in (
        "Adviser",
        "Accounts covered",
        "Investment amount",
        "Source of funds",
        "Selling existing investments?",
        "Product recommended",
        "Held in single or joint name?",
        "Agreed risk profile",
        "Initial charge",
    ):
        assert fields[label]


# --- expected facts ------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_expected_facts_are_valid_and_deterministic(seed: int) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    assert isinstance(facts, ExpectedFacts)
    assert facts.client == scenario.client_id
    assert facts == expected_facts(scenario)
    assert ExpectedFacts.model_validate_json(facts.model_dump_json(by_alias=True)) == facts


@pytest.mark.parametrize("seed", SEEDS)
def test_every_table_row_is_a_real_account_or_a_new_one(seed: int) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    ids = {a.id for a in scenario.accounts}
    for row in facts.table_rows:
        assert row.account in ids or row.account.startswith("new:")
    for excluded in facts.not_in_table:
        assert excluded.account in ids


@pytest.mark.parametrize("seed", SEEDS)
def test_the_table_and_not_in_table_cover_every_account_but_ignored_closed_ones(
    seed: int,
) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    named = {r.account for r in facts.table_rows} | {n.account for n in facts.not_in_table}
    for account in scenario.accounts:
        assert account.id in named


@pytest.mark.parametrize("seed", SEEDS)
def test_the_tax_section_is_expected_exactly_when_a_taxable_account_is_sold(seed: int) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    assert facts.sections.get("tax_implications", False) is (scenario.advice == "gia_sale")
    has_cgt = any(m.key == "cgt" for m in facts.markers)
    assert has_cgt is (scenario.advice == "gia_sale")


@pytest.mark.parametrize("seed", SEEDS)
def test_every_charge_marker_is_expected_and_no_cgt_figure_is_reportable(seed: int) -> None:
    facts = expected_facts(sample_scenario(seed))
    keys = {m.key for m in facts.markers}
    assert "advice_charge" in keys
    assert any(k.startswith("platform_charge_") for k in keys)
    assert all("cgt" not in f.value.lower() for f in facts.reportable_figures)


@pytest.mark.parametrize("seed", SEEDS)
def test_reportable_figures_are_account_values_planned_phrase_figures_or_derived(
    seed: int,
) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    phrase_figures = {f for p in required_phrases(scenario) for f in p.figures}
    account_figures = {f"£{int(a.value):,}" for a in scenario.accounts if a.value is not None}
    for figure in facts.reportable_figures:
        if "%" in figure.value or figure.derived_from:
            continue
        core = figure.value.removeprefix("c. ").removeprefix("up to ")
        assert core in phrase_figures | account_figures, figure.value


@pytest.mark.parametrize("seed", SEEDS)
def test_evidence_quotes_come_from_the_required_phrases(seed: int) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    text = " ".join(p.text for p in required_phrases(scenario))
    for obs in facts.extraction.value_observations:
        assert obs.evidence_quote in text
        assert obs.amount_quote in text
    for item in facts.extraction.money_items:
        assert item.evidence_quote in text
    for disposal in facts.extraction.disposals:
        assert disposal.evidence_quote in text
    for action in facts.extraction.open_actions:
        assert action.evidence_quote in text


@pytest.mark.parametrize("seed", SEEDS)
def test_a_recalled_figure_never_becomes_a_reportable_figure(seed: int) -> None:
    scenario = sample_scenario(seed)
    if not scenario.recalled_decoy:
        return
    facts = expected_facts(scenario)
    recalled = [o for o in facts.extraction.value_observations if o.basis == "recalled"]
    assert len(recalled) == 1
    decoy = recalled[0].amount_quote
    assert all(f.value not in decoy for f in facts.reportable_figures)


@pytest.mark.parametrize("seed", SEEDS)
def test_must_not_appear_figures_really_occur_in_the_distractor(seed: int) -> None:
    scenario = sample_scenario(seed)
    facts = expected_facts(scenario)
    text = distractor_text(scenario)
    assert facts.must_not_appear
    for item in facts.must_not_appear:
        assert item in text
    reportable = {f.value for f in facts.reportable_figures}
    assert not reportable & set(facts.must_not_appear)


# --- the phrase bank -----------------------------------------------------------------------


def test_every_pattern_has_several_wordings() -> None:
    assert len(PHRASE_BANK) >= 10
    for pattern, wordings in PHRASE_BANK.items():
        assert len(wordings) >= 3, pattern
        assert len(set(wordings)) == len(wordings), pattern


def test_the_phrase_bank_shares_no_six_word_run_with_the_real_documents() -> None:
    corpus = corpus_texts(Path("data"))
    assert len(corpus) >= 20  # the four clients' notes, requests, guidance and general documents
    assert bank_overlap(corpus) == []


def test_the_overlap_check_actually_detects_an_overlap() -> None:
    # "no_sale" wordings carry no placeholder, so their whole sentence is fixed text
    wording = PHRASE_BANK["no_sale"][0]
    assert "{" not in wording
    found = bank_overlap([f"Earlier note. {wording} Later note."])
    assert {pattern for pattern, _ in found} == {"no_sale"}
    assert bank_overlap(["Nothing at all in common with the bank."]) == []


@pytest.mark.parametrize("seed", SEEDS)
def test_required_phrases_render_every_field(seed: int) -> None:
    for phrase in required_phrases(sample_scenario(seed)):
        assert "{" not in phrase.text and "}" not in phrase.text, phrase.text
        for figure in phrase.figures:
            assert figure in phrase.text


# --- the prose checks (D4) -----------------------------------------------------------------


def test_a_good_note_passes_the_checks() -> None:
    scenario = sample_scenario(3)
    assert check_prose(_good_note(scenario), required_phrases(scenario)) == []


def test_a_missing_required_phrase_is_rejected() -> None:
    scenario = sample_scenario(3)
    required = required_phrases(scenario)
    note = _good_note(scenario).replace(required[0].text, "")
    problems = check_prose(note, required)
    assert problems
    assert "missing" in problems[0]


def test_a_reworded_required_phrase_is_rejected() -> None:
    scenario = sample_scenario(3)
    required = required_phrases(scenario)
    reworded = required[0].text[:-1] + ";"  # same words, one character different
    note = _good_note(scenario).replace(required[0].text, reworded)
    assert note != _good_note(scenario)
    assert any("missing" in problem for problem in check_prose(note, required))


def test_an_unplanned_figure_is_rejected() -> None:
    scenario = sample_scenario(3)
    note = _good_note(scenario) + " We also discussed an extra £999 fee."
    problems = check_prose(note, required_phrases(scenario))
    assert any("999" in p for p in problems)


def test_an_unplanned_percentage_is_rejected() -> None:
    scenario = sample_scenario(3)
    note = _good_note(scenario) + " Growth was 7% last year."
    assert any("7%" in p for p in check_prose(note, required_phrases(scenario)))


def test_a_figure_written_in_words_is_rejected() -> None:
    scenario = sample_scenario(3)
    note = _good_note(scenario) + " They also hold twenty thousand pounds elsewhere."
    assert check_prose(note, required_phrases(scenario))


def test_a_planned_figure_may_repeat_but_not_change() -> None:
    scenario = sample_scenario(3)
    required = required_phrases(scenario)
    figure = next(f for p in required for f in p.figures)
    assert check_prose(_good_note(scenario) + f" Again, {figure}.", required) == []


class _ScriptedModel:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[str | None] = []

    def write(self, brief: str, required: list[str], feedback: str | None) -> str:
        self.calls.append(feedback)
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]


def test_generate_prose_retries_with_the_problems_as_feedback() -> None:
    scenario = sample_scenario(3)
    required = required_phrases(scenario)
    model = _ScriptedModel(["a note with no required phrases", _good_note(scenario)])
    text = generate_prose(model, brief(scenario), required)
    assert text == _good_note(scenario)
    assert model.calls[0] is None
    assert model.calls[1] is not None and "missing" in model.calls[1]


def test_generate_prose_gives_up_after_its_rounds_and_never_returns_a_bad_note() -> None:
    scenario = sample_scenario(3)
    model = _ScriptedModel(["never right"])
    with pytest.raises(ProseRejected):
        generate_prose(model, brief(scenario), required_phrases(scenario), max_rounds=3)
    assert len(model.calls) == 3


def test_the_brief_states_no_figures_the_model_could_copy() -> None:
    text = brief(sample_scenario(3))
    assert "£" not in text and "%" not in text


# --- writers -------------------------------------------------------------------------------

EXPECTED_FILES = {
    "client_data_db.json",
    "meeting_notes.docx",
    "report_request.docx",
    "platform_market_update.docx",
    "statement_summary.png",
    "fde_notes.md",
    "template_spec.md",
}


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_write_client_writes_every_source_a_real_client_has(seed: int, tmp_path: Path) -> None:
    scenario = sample_scenario(seed)
    write_client(scenario, _good_note(scenario), tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == EXPECTED_FILES
    assert (tmp_path / "statement_summary.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    note = read_docx(tmp_path / "meeting_notes.docx")
    assert all(p.text in " ".join(note.paragraphs.values()) for p in required_phrases(scenario))
    request = read_docx(tmp_path / "report_request.docx")
    assert request.tables


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_write_client_is_byte_for_byte_reproducible(seed: int, tmp_path: Path) -> None:
    scenario = sample_scenario(seed)
    a, b = tmp_path / "a", tmp_path / "b"
    write_client(scenario, _good_note(scenario), a)
    write_client(scenario, _good_note(scenario), b)
    match, mismatch, errors = filecmp.cmpfiles(a, b, sorted(EXPECTED_FILES), shallow=False)
    assert (mismatch, errors) == ([], [])
    assert set(match) == EXPECTED_FILES


def test_the_distractor_document_is_written_from_the_scenario(tmp_path: Path) -> None:
    scenario = sample_scenario(2)
    write_client(scenario, _good_note(scenario), tmp_path)
    doc = read_docx(tmp_path / "platform_market_update.docx")
    assert distractor_text(scenario).split("\n\n")[0] in " ".join(doc.paragraphs.values())
