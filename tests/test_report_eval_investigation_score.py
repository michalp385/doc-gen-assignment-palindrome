"""Scoring the investigation agent against a case's expectations (DESIGN.md section 5.2 and
10.4), tests first.

`accepted_and_wrong` is the headline: a finding code accepted that contradicts the expected
facts. It is reported on its own, and an accepted link with no expectation to check it against
counts as wrong, since nothing shows it right. A question left unresolved when an answer was
expected is neither correct nor wrong: it only counts as raised.
"""

from __future__ import annotations

from agent_pipeline.ledger import Question
from report_eval.expected import InvestigationExpectation
from report_eval.investigation_score import score_investigation


def _question(qid: str, accepted: bool, resolved_to: str | None = None) -> Question:
    return Question(
        id=qid,
        kind="account_link",
        subject_ref="m",
        status="resolved" if accepted else "unresolved",
        accepted=accepted,
        resolved_to=resolved_to,
    )


ANSWER = InvestigationExpectation(question="which account", expected="Y-GIA")
STAYS = InvestigationExpectation(question="which certificate", stays_unresolved=True)


def test_an_accepted_link_to_the_expected_account_is_correct() -> None:
    score = score_investigation([_question("q1", True, "Y-GIA")], [ANSWER])
    assert (score.questions_raised, score.answered_correctly, score.accepted_and_wrong) == (1, 1, 0)


def test_an_accepted_link_to_another_account_is_accepted_and_wrong() -> None:
    score = score_investigation([_question("q1", True, "Y-ISA")], [ANSWER])
    assert (score.answered_correctly, score.accepted_and_wrong) == (0, 1)


def test_an_unresolved_question_that_should_stay_unresolved_is_correct() -> None:
    score = score_investigation([_question("q1", False)], [STAYS])
    assert (score.stayed_unresolved_correctly, score.accepted_and_wrong) == (1, 0)


def test_accepting_a_question_that_should_stay_unresolved_is_wrong() -> None:
    score = score_investigation([_question("q1", True, "O-GIA-01")], [STAYS])
    assert (score.stayed_unresolved_correctly, score.accepted_and_wrong) == (0, 1)


def test_inconclusive_when_an_answer_was_expected_is_only_raised() -> None:
    score = score_investigation([_question("q1", False)], [ANSWER])
    assert score.model_dump() == {
        "questions_raised": 1,
        "answered_correctly": 0,
        "stayed_unresolved_correctly": 0,
        "accepted_and_wrong": 0,
    }


def test_an_accepted_link_with_no_expectation_counts_as_wrong() -> None:
    score = score_investigation([_question("q1", True, "Y-GIA")], [])
    assert (score.questions_raised, score.accepted_and_wrong) == (1, 1)


def test_no_questions_scores_zero_even_when_something_was_expected() -> None:
    assert score_investigation([], [ANSWER]).model_dump() == {
        "questions_raised": 0,
        "answered_correctly": 0,
        "stayed_unresolved_correctly": 0,
        "accepted_and_wrong": 0,
    }


def test_questions_are_paired_with_expectations_in_order() -> None:
    questions = [_question("q1", True, "Y-GIA"), _question("q2", False)]
    score = score_investigation(questions, [ANSWER, STAYS])
    assert (score.answered_correctly, score.stayed_unresolved_correctly) == (1, 1)
