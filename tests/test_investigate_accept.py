"""Code decides what the investigation agent's findings are worth (DESIGN section 5.2), tests first.

Every quote is verified against its own paragraph. A proposed account link is accepted only if
exactly one in-scope account passes code's checks, and only on evidence that is about the
mention: a verified quote in the mention's own paragraph or the one next to it. Where several
accounts pass, the mention stays unresolved whatever the agent proposes (R8: flagged, not
guessed). A proposed label is accepted only with evidence in the same paragraph as the fact it
labels.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.investigate.accept import (
    Accepted,
    NotAccepted,
    accept_account_link,
    accept_label,
)
from agent_pipeline.investigate.schemas import Evidence, Finding
from agent_pipeline.reconcile.questions import OpenQuestion
from agent_pipeline.sources.document import SourceDoc

SOURCE = "meeting_notes.docx"
DOCS = {
    SOURCE: SourceDoc(
        path=Path(SOURCE),
        paragraphs={
            "p1": "Opening remarks about the review.",
            "p2": "She discussed her Stocks & Shares ISA.",
            "p3": "She asked about her other account on the Holloway platform.",
            "p4": "George recalled the ISA being around a certain amount.",
            "p5": "Nothing else was raised.",
            "p6": "Hello world, an unrelated remark far from the mention.",
        },
    )
}
MENTION_PARAGRAPH = "p3"


def _question(candidates=("Y-ISA", "Y-GIA"), claimed=("Y-ISA",), in_scope=None) -> OpenQuestion:  # type: ignore[no-untyped-def]
    return OpenQuestion(
        id="q1",
        kind="account_link",
        mention="her other account on the Holloway platform",
        candidate_ids=tuple(candidates),
        claimed_ids=tuple(claimed),
        in_scope_ids=tuple(candidates if in_scope is None else in_scope),
    )


def _finding(
    account: str | None = "Y-GIA",
    answer: str = "supports",
    quote: str = "her other account on the Holloway platform",
    paragraph: str = "p3",
    label: str | None = None,
) -> Finding:
    return Finding(
        question_id="q1",
        answer=answer,  # type: ignore[arg-type]  # the test passes the literal by name
        proposed_account_id=account,
        proposed_label=label,
        evidence=[Evidence(source=SOURCE, paragraph_id=paragraph, quote=quote)],
        explanation="the only other Holloway account",
    )


def _accept(finding: Finding, question: OpenQuestion | None = None, near: str | None = "p3"):  # type: ignore[no-untyped-def]
    return accept_account_link(
        finding, question or _question(), DOCS, meeting_source=SOURCE, mention_paragraph=near
    )


def test_a_supported_link_to_the_one_remaining_candidate_is_accepted() -> None:
    result = _accept(_finding())
    assert isinstance(result, Accepted) and result.account_id == "Y-GIA"
    assert result.evidence.paragraph_id == "p3"


def test_evidence_in_the_paragraph_next_to_the_mention_is_enough() -> None:
    finding = _finding(quote="her Stocks & Shares ISA", paragraph="p2")
    assert isinstance(_accept(finding), Accepted)


def test_a_verified_quote_far_from_the_mention_is_not_evidence_about_it() -> None:
    finding = _finding(quote="an unrelated remark far from", paragraph="p6")
    result = _accept(finding)
    assert isinstance(result, NotAccepted) and "mention" in result.reason


def test_a_mention_that_cannot_be_located_is_never_accepted() -> None:
    result = _accept(_finding(), near=None)
    assert isinstance(result, NotAccepted) and "locate" in result.reason


def test_several_candidates_left_stay_unresolved_whatever_the_agent_proposes() -> None:
    result = _accept(_finding(), _question(claimed=()))
    assert isinstance(result, NotAccepted) and "several" in result.reason


def test_a_proposal_that_is_not_a_candidate_is_rejected() -> None:
    result = _accept(_finding(account="Z-OTHER"))
    assert isinstance(result, NotAccepted) and "not a candidate" in result.reason


def test_a_proposal_for_a_claimed_account_is_rejected() -> None:
    assert isinstance(_accept(_finding(account="Y-ISA")), NotAccepted)


def test_an_out_of_scope_account_is_never_the_accepted_link() -> None:
    question = _question(candidates=("Y-ISA", "Y-GIA", "Y-OLD"), claimed=("Y-ISA", "Y-GIA"))
    question = question.__class__(
        id="q1",
        kind="account_link",
        mention=question.mention,
        candidate_ids=question.candidate_ids,
        claimed_ids=question.claimed_ids,
        in_scope_ids=("Y-ISA", "Y-GIA"),
    )
    result = _accept(_finding(account="Y-OLD"), question)
    assert isinstance(result, NotAccepted) and "scope" in result.reason


def test_an_unverifiable_quote_makes_the_finding_inconclusive() -> None:
    result = _accept(_finding(quote="words that are not in the note"))
    assert isinstance(result, NotAccepted) and "verif" in result.reason


def test_an_empty_or_trivial_quote_is_not_evidence() -> None:
    """An empty string is "in" every paragraph; a word or two shows nothing about an account."""
    for quote in ("", "   ", "a", "her ISA"):
        result = _accept(_finding(quote=quote))
        assert isinstance(result, NotAccepted) and "verif" in result.reason, quote


def test_three_real_words_are_enough_and_the_boundary_is_pinned() -> None:
    assert isinstance(_accept(_finding(quote="the Holloway platform")), Accepted)
    assert isinstance(_accept(_finding(quote="Holloway platform")), NotAccepted)
    assert isinstance(_accept(_finding(quote="... --- !!!")), NotAccepted)


def test_a_label_needs_a_real_quote_too() -> None:
    finding = _finding(account=None, label="recalled", paragraph="p4", quote="")
    assert isinstance(accept_label(finding, "p4", DOCS, {"recalled"}), NotAccepted)


def test_a_quote_from_the_wrong_paragraph_does_not_verify() -> None:
    assert isinstance(_accept(_finding(paragraph="p1")), NotAccepted)


def test_an_answer_other_than_supports_is_never_accepted() -> None:
    for answer in ("contradicts", "inconclusive"):
        assert isinstance(_accept(_finding(answer=answer)), NotAccepted)


def test_a_finding_with_no_evidence_is_not_accepted() -> None:
    finding = _finding().model_copy(update={"evidence": []})
    assert isinstance(_accept(finding), NotAccepted)


def test_a_label_is_accepted_with_evidence_in_the_facts_own_paragraph() -> None:
    finding = _finding(
        account=None, label="viewed_in_meeting", paragraph="p4", quote="George recalled the ISA"
    )
    result = accept_label(finding, "p4", DOCS, {"viewed_in_meeting", "recalled"})
    assert isinstance(result, Accepted) and result.label == "viewed_in_meeting"


def test_label_evidence_from_another_paragraph_is_rejected() -> None:
    finding = _finding(
        account=None, label="viewed_in_meeting", paragraph="p2", quote="Stocks & Shares ISA"
    )
    result = accept_label(finding, "p4", DOCS, {"viewed_in_meeting", "recalled"})
    assert isinstance(result, NotAccepted) and "same paragraph" in result.reason


def test_a_label_outside_the_allowed_set_is_rejected() -> None:
    finding = _finding(account=None, label="made_up", paragraph="p4", quote="George recalled")
    assert isinstance(accept_label(finding, "p4", DOCS, {"recalled"}), NotAccepted)


def test_an_unverifiable_label_quote_is_rejected() -> None:
    finding = _finding(account=None, label="recalled", paragraph="p4", quote="not in the note")
    assert isinstance(accept_label(finding, "p4", DOCS, {"recalled"}), NotAccepted)
