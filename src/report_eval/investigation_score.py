"""Score the investigation agent against a case's expectations (DESIGN.md sections 5.2, 10.4).

Questions are paired with expectations in order (a hand-written case raises the questions it was
built to raise, in the order the note mentions them). An accepted link to the expected account
is correct; an unresolved question that was expected to stay unresolved is correct. A finding
code accepted that contradicts the expectation is **accepted-and-wrong**, the headline figure, and
so is an accepted link with no expectation to check it against, since nothing shows it right. A
question left unresolved when an answer was expected is neither correct nor wrong.
"""

from __future__ import annotations

from collections.abc import Sequence

from agent_pipeline.ledger import Question
from report_eval.expected import InvestigationExpectation
from report_eval.results import InvestigationScore


def score_investigation(
    questions: Sequence[Question], expectations: Sequence[InvestigationExpectation]
) -> InvestigationScore:
    correct = stayed = wrong = 0
    for index, question in enumerate(questions):
        expectation = expectations[index] if index < len(expectations) else None
        if expectation is None:
            wrong += question.accepted
        elif expectation.stays_unresolved:
            if question.accepted:
                wrong += 1
            else:
                stayed += 1
        elif question.accepted:
            if question.resolved_to == expectation.expected:
                correct += 1
            else:
                wrong += 1
    return InvestigationScore(
        questions_raised=len(questions),
        answered_correctly=correct,
        stayed_unresolved_correctly=stayed,
        accepted_and_wrong=wrong,
    )
