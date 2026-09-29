"""The investigation stage (stage 3a, DESIGN.md section 5.2, D14): questions in, review items out.

Reconciliation opens the questions; the agent gathers quoted evidence; code accepts or rejects
it. The stage returns the ledger's question records and review-sheet items, and never touches
the ledger's facts or the report: an accepted link is shown as "changed by investigation" with
the default it replaced, the new value and the quote, and an unresolved mention is an ambiguity
item carrying the note's own paragraph. With no model, or a model that fails, the defaults stand.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from agent_pipeline.extract.meeting import find_in_source
from agent_pipeline.investigate.accept import Accepted, NotAccepted, accept_account_link
from agent_pipeline.investigate.agent import InvestigationModel, QuestionResult, investigate
from agent_pipeline.investigate.tools import ReadOnlyTools
from agent_pipeline.ledger import Account, Question
from agent_pipeline.reconcile.questions import OpenQuestion, open_questions
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.sources.document import SourceDoc


@dataclass
class InvestigationOutcome:
    questions: list[Question] = field(default_factory=list)
    review_items: list[ReviewItemInput] = field(default_factory=list)


def _describe(account: Account | None, account_id: str) -> str:
    if account is None:
        return account_id
    where = f" ({account.platform})" if account.platform else ""
    return f"{account.type}{where}, {account_id}"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def locate_mention(mention: str, doc: SourceDoc | None) -> str | None:
    """The id of the one paragraph containing the mention's words verbatim (whitespace and case
    aside, whole words), or None. Exact, not fuzzy, and None when it appears in several
    paragraphs: acceptance ties the evidence to this paragraph, so it must be the right one."""
    if doc is None or not mention.strip():
        return None
    pattern = re.compile(rf"(?<!\w){re.escape(_normalise(mention))}(?!\w)")
    found = [pid for pid, text in doc.paragraphs.items() if pattern.search(_normalise(text))]
    return found[0] if len(found) == 1 else None


def _paragraph_of(mention: str, doc: SourceDoc | None) -> str:
    if doc is None:
        return ""
    located = locate_mention(mention, doc)
    if located is not None:
        return doc.paragraphs[located]
    hits = find_in_source(doc, mention, limit=1)  # display only; never used to accept
    return hits[0].text if hits else ""


def _decide(
    result: QuestionResult, docs: Mapping[str, SourceDoc], meeting_source: str
) -> Accepted | NotAccepted:
    if result.finding is None:
        return NotAccepted(result.note or "no finding")
    return accept_account_link(
        result.finding,
        result.question,
        docs,
        meeting_source=meeting_source,
        mention_paragraph=locate_mention(result.question.mention, docs.get(meeting_source)),
    )


def run_investigation(
    mentions: Sequence[str],
    accounts: Sequence[Account],
    docs: Mapping[str, SourceDoc],
    meeting_source: str,
    model: InvestigationModel | None,
    ledger_entries: Mapping[str, object] | None = None,
) -> InvestigationOutcome:
    questions = open_questions(mentions, accounts)
    outcome = InvestigationOutcome()
    if not questions:
        return outcome
    if model is None:
        results = [QuestionResult(q, None, 0, "investigation not run") for q in questions]
    else:
        tools = ReadOnlyTools(docs, accounts, ledger_entries)
        results = investigate(questions, tools, model)

    by_id = {a.id: a for a in accounts}
    for result in results:
        question: OpenQuestion = result.question
        decision = _decide(result, docs, meeting_source)
        if isinstance(decision, Accepted) and decision.account_id is not None:
            account_id = decision.account_id
            explanation = result.finding.explanation if result.finding else ""
            outcome.questions.append(
                Question(
                    id=question.id,
                    kind=question.kind,
                    subject_ref=question.mention,
                    status="resolved",
                    accepted=True,
                    reason=explanation,
                    resolved_to=account_id,
                )
            )
            evidence = decision.evidence
            outcome.review_items.append(
                ReviewItemInput(
                    kind="investigation",
                    blocking=False,
                    detail=(
                        f"changed by investigation: {question.mention!r} was unresolved (the "
                        f"default: not linked to any account); it is now linked to "
                        f"{_describe(by_id.get(account_id), account_id)} on the evidence "
                        f'"{evidence.quote}" ({evidence.source}, {evidence.paragraph_id}).'
                    ),
                    refs=[account_id],
                )
            )
            continue
        reason = decision.reason if isinstance(decision, NotAccepted) else "not accepted"
        outcome.questions.append(
            Question(
                id=question.id,
                kind=question.kind,
                subject_ref=question.mention,
                status="unresolved",
                accepted=False,
                reason=reason,
            )
        )
        options = "; ".join(_describe(by_id.get(c), c) for c in question.candidate_ids)
        paragraph = _paragraph_of(question.mention, docs.get(meeting_source))
        outcome.review_items.append(
            ReviewItemInput(
                kind="ambiguity",
                blocking=False,
                detail=(
                    f"{question.mention!r} could mean any of: {options}. The sources do not say "
                    f"which ({reason}). Meeting note: {paragraph}"
                ),
                refs=[],
            )
        )
    return outcome
