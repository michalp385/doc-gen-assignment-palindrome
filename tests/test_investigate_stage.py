"""The investigation stage end to end, offline (DESIGN section 5.2, cases 16 and 17), tests first.

Reconciliation opens the questions, the agent gathers quoted evidence, code accepts or rejects
it, and the outcome is review-sheet items plus the ledger's question records. An accepted link
shows as "changed by investigation" with the default it replaced, the new value and the quote;
an unresolved one is an ambiguity item that carries the note's own paragraph. Nothing the agent
says reaches the report, and a failure leaves the defaults.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.investigate.schemas import AgentStep, Evidence, Finding
from agent_pipeline.investigate.stage import locate_mention, run_investigation
from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.questions import OpenQuestion
from agent_pipeline.sources.document import SourceDoc

NOTE_LINK = "Yvonne also asked about her other account on the Holloway platform."
NOTE_ISA = "We discussed her Stocks & Shares ISA, which she is happy to leave as it is."
NOTE_CERT = (
    "Bernard mentioned an old paper share certificate relating to one of his General "
    "Investment Accounts on Holloway, but could not recall which one."
)


def _doc(*paragraphs: str) -> dict[str, SourceDoc]:
    return {
        "meeting_notes.docx": SourceDoc(
            path=Path("meeting_notes.docx"),
            paragraphs={f"p{i}": text for i, text in enumerate(paragraphs, start=1)},
        )
    }


def _acct(account_id: str, type_: str) -> Account:
    return Account(
        id=account_id, type=type_, owners=["Yvonne Pascoe"], platform="Holloway", in_scope=True
    )


class Answering:
    def __init__(self, account: str | None, paragraph: str, quote: str) -> None:
        self.calls = 0
        self._step = AgentStep(
            tool="finish",
            finding=Finding(
                question_id="q1",
                answer="supports",
                proposed_account_id=account,
                proposed_label=None,
                evidence=[
                    Evidence(source="meeting_notes.docx", paragraph_id=paragraph, quote=quote)
                ],
                explanation="",
            ),
        )

    def step(self, question: OpenQuestion, observations: list[dict]) -> AgentStep:  # type: ignore[type-arg]
        self.calls += 1
        return self._step


class Failing:
    def step(self, question, observations):  # type: ignore[no-untyped-def]
        raise RuntimeError("API down")


def test_case_16_one_remaining_candidate_is_linked_and_shown_as_changed() -> None:
    docs = _doc(NOTE_ISA, NOTE_LINK)
    accounts = [_acct("Y-ISA", "Stocks & Shares ISA"), _acct("Y-GIA", "General Investment Account")]
    mentions = ["her Stocks & Shares ISA", "her other account on the Holloway platform"]
    model = Answering("Y-GIA", "p2", "her other account on the Holloway platform")

    outcome = run_investigation(mentions, accounts, docs, "meeting_notes.docx", model)

    [question] = outcome.questions
    assert question.status == "resolved" and question.accepted and question.resolved_to == "Y-GIA"
    [item] = outcome.review_items
    assert item.kind == "investigation" and not item.blocking
    assert "changed by investigation" in item.detail
    assert "Y-GIA" in item.detail and "her other account on the Holloway platform" in item.detail
    assert item.refs == ["Y-GIA"]


def test_case_17_two_candidates_stay_unresolved_and_carry_the_paragraph() -> None:
    docs = _doc(NOTE_CERT)
    accounts = [
        _acct("O-GIA-01", "General Investment Account"),
        _acct("O-GIA-02", "General Investment Account"),
    ]
    mentions = ["one of his General Investment Accounts on Holloway"]
    model = Answering("O-GIA-01", "p1", "one of his General Investment Accounts on Holloway")

    outcome = run_investigation(mentions, accounts, docs, "meeting_notes.docx", model)

    [question] = outcome.questions
    assert question.status == "unresolved" and not question.accepted
    [item] = outcome.review_items
    assert item.kind == "ambiguity" and not item.blocking
    assert "paper share certificate" in item.detail
    assert "General Investment Account" in item.detail


def test_a_mention_is_located_on_word_boundaries_and_only_if_unique() -> None:
    doc = SourceDoc(
        path=Path("m.docx"),
        paragraphs={
            "p1": "This is advisable.",
            "p2": "Her ISA was discussed.",
            "p3": "Her ISA again, later.",
        },
    )
    assert (
        locate_mention(
            "ISA",
            SourceDoc(
                path=Path("m.docx"),
                paragraphs={"p1": doc.paragraphs["p1"], "p2": doc.paragraphs["p2"]},
            ),
        )
        == "p2"
    )
    assert locate_mention("her isa was discussed", doc) == "p2"
    assert locate_mention("Her ISA", doc) is None  # in two paragraphs: not located
    assert locate_mention("not there", doc) is None
    assert locate_mention("   ", doc) is None


def test_a_model_failure_leaves_the_default_and_never_raises() -> None:
    docs = _doc(NOTE_ISA, NOTE_LINK)
    accounts = [_acct("Y-ISA", "Stocks & Shares ISA"), _acct("Y-GIA", "General Investment Account")]
    mentions = ["her other account on the Holloway platform"]
    outcome = run_investigation(mentions, accounts, docs, "meeting_notes.docx", Failing())
    [item] = outcome.review_items
    assert item.kind == "ambiguity"
    assert outcome.questions[0].status == "unresolved"


def test_without_a_model_the_defaults_stand() -> None:
    docs = _doc(NOTE_ISA, NOTE_LINK)
    accounts = [_acct("Y-ISA", "Stocks & Shares ISA"), _acct("Y-GIA", "General Investment Account")]
    outcome = run_investigation(
        ["her other account on the Holloway platform"], accounts, docs, "meeting_notes.docx", None
    )
    assert [i.kind for i in outcome.review_items] == ["ambiguity"]


def test_no_open_question_means_no_model_call_and_nothing_emitted() -> None:
    docs = _doc(NOTE_ISA)
    model = Answering(None, "p1", "x")
    outcome = run_investigation(
        ["her Stocks & Shares ISA"],
        [_acct("Y-ISA", "Stocks & Shares ISA")],
        docs,
        "meeting_notes.docx",
        model,
    )
    assert outcome.questions == [] and outcome.review_items == [] and model.calls == 0
