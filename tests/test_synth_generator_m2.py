"""The synthetic generator's verifier-checkpoint fixes (T27), tests first.

A single client's note must not say "both ISAs"; a top-up scenario's source cash account
must not be ambiguous with an open, valueless cash account (SCOPING R8 flags a reference that
matches more accounts than it names); `check_prose` must catch "GBP 45,000", "45,000 pounds"
and "5 per cent"; the phrase-bank overlap check must see a run that spans a placeholder;
and the name pools must not collide with any name already under `data/`.

These tests check the generator's internal consistency. The scenario's expected facts and its
required phrases come from the same code, so they cannot show the SCOPING rules are right --
the hand-written cases do that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from report_eval.synth import scenario as scenario_module
from report_eval.synth.phrases import PHRASE_BANK, bank_overlap, corpus_texts
from report_eval.synth.prose import check_prose
from report_eval.synth.scenario import required_phrases, sample_scenario

SEEDS = list(range(1, 61))


# --- the part-funded phrase fits the number of clients --------------------------------------


def test_a_single_clients_note_never_says_both_isas() -> None:
    checked = 0
    for seed in SEEDS:
        s = sample_scenario(seed)
        if s.advice != "gia_sale" or len(s.holders) != 1:
            continue
        checked += 1
        text = next(p.text for p in required_phrases(s) if p.pattern.startswith("part_funded"))
        assert "Both" not in text and "ISAs" not in text, text
    assert checked >= 3


def test_a_couples_note_may_say_the_isas_plural() -> None:
    couples = [
        s for s in map(sample_scenario, SEEDS) if s.advice == "gia_sale" and len(s.holders) == 2
    ]
    assert couples
    for s in couples:
        pattern = next(p.pattern for p in required_phrases(s) if p.pattern.startswith("part_f"))
        assert pattern == "part_funded"


def test_every_bank_pattern_is_used_by_some_scenario() -> None:
    used = {p.pattern for s in map(sample_scenario, SEEDS) for p in required_phrases(s)}
    assert set(PHRASE_BANK) - used == set()


# --- no ambiguous cash reference -----------------------------------------------------------


def test_no_two_open_cash_accounts_share_a_platform() -> None:
    for seed in SEEDS:
        s = sample_scenario(seed)
        open_cash = [a for a in s.accounts if a.type == "Cash Account" and a.status == "open"]
        platforms = [a.platform for a in open_cash]
        assert len(platforms) == len(set(platforms)), (seed, platforms)


def test_the_dormant_accounts_platform_differs_from_the_main_platform() -> None:
    dormant = [(s, s.account("dormant")) for s in map(sample_scenario, SEEDS) if s.null_cash]
    assert dormant
    for s, account in dormant:
        assert account.platform != s.platform


# --- check_prose catches more ways to write a figure ---------------------------------------


def _problems(extra: str) -> list[str]:
    s = sample_scenario(3)
    note = "\n\n".join(p.text for p in required_phrases(s)) + "\n\n" + extra
    return check_prose(note, required_phrases(s))


@pytest.mark.parametrize(
    "extra",
    [
        "They also hold GBP 45,000 elsewhere.",
        "They also hold GBP45000 elsewhere.",
        "They also hold 45,000 pounds elsewhere.",
        "Growth was 5 per cent last year.",
        "They also hold 45 grand elsewhere.",
        "They also hold 2 million elsewhere.",
        "They also hold 45k elsewhere.",
    ],
)
def test_unplanned_figures_in_other_forms_are_rejected(extra: str) -> None:
    assert _problems(extra), extra


def test_ordinary_prose_with_no_figure_still_passes() -> None:
    assert _problems("They were pleased with the service and had no further questions.") == []


def test_a_year_or_a_date_is_not_mistaken_for_a_figure() -> None:
    assert _problems("The next review will be in the spring of 2027, on the 3rd.") == []


# --- the overlap check sees a run that spans a placeholder ---------------------------------


def test_a_run_spanning_a_placeholder_is_detected() -> None:
    # "{names} chose to transfer {amount} from the {source} to {destination}." has only short
    # fixed runs, but with the placeholders filled by real words it shares a six-word run.
    corpus = ["Last year they chose to transfer ten thousand from the old account to savings."]
    assert "topup" in {pattern for pattern, _ in bank_overlap(corpus)}


def test_a_run_that_only_matches_because_a_placeholder_is_a_wildcard_needs_enough_fixed_words() -> (
    None
):
    corpus = ["Nothing relevant appears in this short text at all."]
    assert bank_overlap(corpus) == []


def test_the_corpus_includes_the_hand_written_cases_and_leaves_out_the_spec(tmp_path: Path) -> None:
    texts = corpus_texts(Path("data"))
    joined = " ".join(texts)
    assert "Report Requirement Summary" in joined  # a request table
    spec = Path("data/client_01_clean/template_spec.md").read_text(encoding="utf-8")
    assert spec.strip()[:80] not in joined
    handwritten = list(Path("data/synthetic/handwritten").glob("case_*/meeting_notes.docx"))
    assert handwritten and len(texts) > 26


def test_the_phrase_bank_still_shares_no_run_with_the_real_documents() -> None:
    assert bank_overlap(corpus_texts(Path("data"))) == []


# --- the name pools do not collide with names already in the repo ---------------------------


def _existing_name_parts() -> set[str]:
    parts: set[str] = set()
    for db in Path("data").rglob("client_data_db.json"):
        data = json.loads(db.read_text(encoding="utf-8"))
        for holder in data.get("holders", {}).values():
            parts.update(p.lower() for p in holder.get("name", "").split() if len(p) > 2)
    for expected in Path("eval/expected").glob("*.json"):
        text = expected.read_text(encoding="utf-8")
        for pool in (scenario_module.FIRST_NAMES, scenario_module.SURNAMES):
            parts.update(name.lower() for name in pool if name in text)
    return parts


def test_no_pool_name_is_a_name_already_used_by_a_real_or_hand_written_client() -> None:
    pool = {n.lower() for n in [*scenario_module.FIRST_NAMES, *scenario_module.SURNAMES]}
    assert pool & _existing_name_parts() == set()


def test_the_advisers_platforms_and_funds_are_not_already_in_the_data() -> None:
    corpus = " ".join(corpus_texts(Path("data"))).lower()
    for value in [
        *scenario_module.ADVISERS,
        *scenario_module.PLATFORMS,
        *scenario_module.FUNDS,
    ]:
        assert value.lower() not in corpus, value
