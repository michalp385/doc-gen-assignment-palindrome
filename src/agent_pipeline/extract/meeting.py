"""Meeting extraction, with the verification loop (DESIGN.md section 4.1, D18).

Every fact's quote is checked with T5's `verify_quote`; a decisive label's evidence is
checked with T5's `verify_label`, which requires it to be in the fact's own paragraph or
falls back to a conservative default. A round that leaves any fact unverified re-asks the
model, once per round, up to two more times (three rounds total): the loop itself searches
the document with `find_in_source` (D18: code-driven, not a real model tool call) and folds
the candidate paragraphs into the next round's correction text. A fact still unverified after
round three is dropped from the result and recorded as a review item, never a report fact.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from agent_pipeline.config import PromptSpec
from agent_pipeline.extract.quotes import (
    CONSERVATIVE_DEFAULTS,
    Accepted,
    Rejected,
    Verified,
    verify_label,
    verify_quote,
)
from agent_pipeline.extract.quotes import (
    LabelEvidence as VerifyLabelEvidence,
)
from agent_pipeline.extract.schemas import (
    AgreedAction,
    Disposal,
    DroppedFact,
    ExcludedItem,
    LabelEvidence,
    MeetingExtraction,
    MoneyItem,
    ObjectiveStatement,
    OpenAction,
    Quote,
    RawMeetingProposal,
    ValueObservation,
)
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.document import SourceDoc

MAX_ROUNDS = 3


class MeetingModel(Protocol):
    def propose(self, doc_text: str, corrections: list[str]) -> RawMeetingProposal: ...


class LLMMeetingModel:
    """The real `MeetingModel`, wrapping T11's `LLMClient` and
    `config/prompts/extract_meeting.md`."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def propose(self, doc_text: str, corrections: list[str]) -> RawMeetingProposal:
        result = self._llm.structured(
            stage="extract",
            prompt=self._prompt,
            inputs={"text": doc_text, "corrections": corrections},
            schema=RawMeetingProposal,
        )
        return result.output


def _doc_text(doc: SourceDoc) -> str:
    return "\n".join(f"[{pid}] {text}" for pid, text in doc.paragraphs.items())


def find_in_source(doc: SourceDoc, text: str, limit: int = 3) -> list[Quote]:
    """A deterministic word-overlap search over doc's paragraphs -- code-driven, not a real
    model tool call (D18). Ranks paragraphs by shared-word count with `text`."""
    words = set(re.findall(r"[A-Za-z']+", text.lower()))
    if not words:
        return []
    scored = []
    for paragraph_id, paragraph_text in doc.paragraphs.items():
        candidate_words = set(re.findall(r"[A-Za-z']+", paragraph_text.lower()))
        overlap = len(words & candidate_words)
        if overlap:
            scored.append((overlap, paragraph_id, paragraph_text))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [Quote(paragraph_id=pid, text=text) for _, pid, text in scored[:limit]]


@dataclass(frozen=True)
class _Rejection:
    description: str
    quote: str
    reason: str


def _verify_evidence_label(
    doc: SourceDoc, *, fact_paragraph_id: str, raw_value: str, evidence: LabelEvidence, default: str
) -> tuple[str, bool]:
    """Runs T5's verify_label; returns (resolved_value, was_defaulted)."""
    result = verify_label(
        doc,
        fact_paragraph_id=fact_paragraph_id,
        label=raw_value,
        evidence=VerifyLabelEvidence(paragraph_id=evidence.paragraph_id, quote=evidence.text),
        default=default,
    )
    if isinstance(result, Accepted):
        return result.label, False
    return result.label, True


def _verify_quote_of(doc: SourceDoc, quote: Quote) -> Verified | Rejected:
    return verify_quote(doc, quote.paragraph_id, quote.text)


def _verify_value_observation(
    doc: SourceDoc, obs: ValueObservation
) -> tuple[ValueObservation | None, _Rejection | None]:
    verified = _verify_quote_of(doc, obs.amount)
    if isinstance(verified, Rejected):
        return None, _Rejection(
            f"value observation for {obs.account_reference!r}", obs.amount.text, verified.reason
        )
    basis, _ = _verify_evidence_label(
        doc,
        fact_paragraph_id=obs.amount.paragraph_id,
        raw_value=obs.basis,
        evidence=obs.basis_evidence,
        default=CONSERVATIVE_DEFAULTS["basis"],
    )
    return obs.model_copy(update={"basis": basis}), None


def _verify_money_item(
    doc: SourceDoc, item: MoneyItem
) -> tuple[MoneyItem | None, _Rejection | None]:
    if item.amount is not None:
        verified = _verify_quote_of(doc, item.amount)
        if isinstance(verified, Rejected):
            return None, _Rejection(
                f"money item ({item.purpose!r})", item.amount.text, verified.reason
            )
    fact_paragraph_id = (
        item.amount.paragraph_id if item.amount else item.class_evidence.paragraph_id
    )
    result = verify_label(
        doc,
        fact_paragraph_id=fact_paragraph_id,
        label=item.money_class or "",
        evidence=VerifyLabelEvidence(
            paragraph_id=item.class_evidence.paragraph_id, quote=item.class_evidence.text
        ),
        default="",  # DESIGN section 4.2: unclear money class -> "not available", not a guess
    )
    money_class = item.money_class if isinstance(result, Accepted) else None
    return item.model_copy(update={"money_class": money_class}), None


def _verify_agreed_action(
    doc: SourceDoc, action: AgreedAction
) -> tuple[AgreedAction | None, _Rejection | None]:
    verified = _verify_quote_of(doc, action.description)
    if isinstance(verified, Rejected):
        return None, _Rejection("agreed action", action.description.text, verified.reason)
    if action.amount is not None:
        verified_amount = _verify_quote_of(doc, action.amount)
        if isinstance(verified_amount, Rejected):
            return None, _Rejection(
                "agreed action amount", action.amount.text, verified_amount.reason
            )
    return action, None


def _verify_disposal(
    doc: SourceDoc, disposal: Disposal
) -> tuple[Disposal | None, _Rejection | None]:
    verified = _verify_quote_of(doc, disposal.quote)
    if isinstance(verified, Rejected):
        return None, _Rejection(
            f"disposal for {disposal.account_reference!r}", disposal.quote.text, verified.reason
        )
    extent, _ = _verify_evidence_label(
        doc,
        fact_paragraph_id=disposal.quote.paragraph_id,
        raw_value=disposal.extent,
        evidence=disposal.extent_evidence,
        default="unspecified",  # DESIGN section 4.2: unclear extent -> no proceeds counted (P5)
    )
    return disposal.model_copy(update={"extent": extent}), None


def _verify_open_action(
    doc: SourceDoc, action: OpenAction
) -> tuple[OpenAction | None, _Rejection | None]:
    verified = _verify_quote_of(doc, action.text)
    if isinstance(verified, Rejected):
        return None, _Rejection("open action", action.text.text, verified.reason)
    blocking_str, _ = _verify_evidence_label(
        doc,
        fact_paragraph_id=action.text.paragraph_id,
        raw_value="true" if action.blocking else "false",
        evidence=action.blocking_evidence,
        default="true",  # DESIGN section 4.2: unclear blocking -> blocking (an adviser sees it)
    )
    return action.model_copy(update={"blocking": blocking_str == "true"}), None


def _verify_excluded_item(
    doc: SourceDoc, item: ExcludedItem
) -> tuple[ExcludedItem | None, _Rejection | None]:
    verified = _verify_quote_of(doc, item.text)
    if isinstance(verified, Rejected):
        return None, _Rejection("excluded item", item.text.text, verified.reason)
    item_class, _ = _verify_evidence_label(
        doc,
        fact_paragraph_id=item.text.paragraph_id,
        raw_value=item.item_class,
        evidence=item.class_evidence,
        default=CONSERVATIVE_DEFAULTS["excluded_class"],
    )
    return item.model_copy(update={"item_class": item_class}), None


def _verify_objective(
    doc: SourceDoc, obj: ObjectiveStatement
) -> tuple[ObjectiveStatement | None, _Rejection | None]:
    verified = _verify_quote_of(doc, obj.text)
    if isinstance(verified, Rejected):
        return None, _Rejection("objective/circumstance statement", obj.text.text, verified.reason)
    return obj, None


def _verify_meeting_date(doc: SourceDoc, quote: Quote | None) -> Quote | None:
    if quote is None:
        return None
    verified = _verify_quote_of(doc, quote)
    return quote if isinstance(verified, Verified) else None


_F = TypeVar("_F")


def _verify_round(
    doc: SourceDoc, raw: RawMeetingProposal
) -> tuple[RawMeetingProposal, list[_Rejection]]:
    rejections: list[_Rejection] = []

    def _run(
        items: list[_F], verifier: Callable[[SourceDoc, _F], tuple[_F | None, _Rejection | None]]
    ) -> list[_F]:
        kept: list[_F] = []
        for item in items:
            result, rejection = verifier(doc, item)
            if rejection is not None:
                rejections.append(rejection)
            elif result is not None:
                kept.append(result)
        return kept

    value_observations = _run(raw.value_observations, _verify_value_observation)
    money_items = _run(raw.money_items, _verify_money_item)
    agreed_actions = _run(raw.agreed_actions, _verify_agreed_action)
    disposals = _run(raw.disposals, _verify_disposal)
    open_actions = _run(raw.open_actions, _verify_open_action)
    excluded_items = _run(raw.excluded_items, _verify_excluded_item)
    objectives = _run(raw.objectives_and_circumstances, _verify_objective)
    meeting_date = _verify_meeting_date(doc, raw.meeting_date)

    verified = raw.model_copy(
        update={
            "meeting_date": meeting_date,
            "value_observations": value_observations,
            "money_items": money_items,
            "agreed_actions": agreed_actions,
            "disposals": disposals,
            "open_actions": open_actions,
            "excluded_items": excluded_items,
            "objectives_and_circumstances": objectives,
            # limit_signals carry no verification-worthy label and their own quote isn't a
            # report fact (P4 screening only reads them); still dropped if unverifiable.
            "limit_signals": [
                ls
                for ls in raw.limit_signals
                if isinstance(_verify_quote_of(doc, ls.text), Verified)
            ],
        }
    )
    return verified, rejections


def extract_meeting(doc: SourceDoc, model: MeetingModel) -> MeetingExtraction:
    corrections: list[str] = []
    doc_text = _doc_text(doc)
    verified = RawMeetingProposal()
    rejections: list[_Rejection] = []

    for round_num in range(1, MAX_ROUNDS + 1):
        raw = model.propose(doc_text, corrections)
        verified, rejections = _verify_round(doc, raw)
        if not rejections or round_num == MAX_ROUNDS:
            break
        corrections = [
            f"{r.description}: {r.reason}. Candidate paragraphs: "
            f"{[(q.paragraph_id, q.text) for q in find_in_source(doc, r.quote)]}"
            for r in rejections
        ]

    dropped = [
        DroppedFact(
            description=r.description, last_quote=r.quote, reason=f"could not verify: {r.reason}"
        )
        for r in rejections
    ]
    return MeetingExtraction(**verified.model_dump(), dropped=dropped)
