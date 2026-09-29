"""Code decides what an investigation finding is worth (DESIGN.md section 5.2, D14).

The agent only proposes. Every quote is verified against its own paragraph, and a finding whose
quotes do not verify is inconclusive. A proposed account link is accepted only if exactly one
account passes the checks: a candidate, not already pinned down by another mention. Where
several pass, the mention stays unresolved whatever the agent proposes (R8: flagged, not
guessed). A proposed label is accepted only as label evidence, and only from the same paragraph
as the fact it labels (section 4.2).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from agent_pipeline.extract.quotes import Verified, verify_quote
from agent_pipeline.investigate.schemas import Evidence, Finding
from agent_pipeline.reconcile.questions import OpenQuestion
from agent_pipeline.sources.document import SourceDoc


@dataclass(frozen=True)
class Accepted:
    evidence: Evidence
    account_id: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class NotAccepted:
    reason: str


# Fewer words than this cannot show anything about an account. `verify_quote` alone would
# accept an empty string, which is a substring of every paragraph.
MIN_QUOTE_WORDS = 3


def _verified(finding: Finding, docs: Mapping[str, SourceDoc]) -> list[Evidence]:
    """The evidence items whose quote is real, in the paragraph they claim."""
    verified = []
    for item in finding.evidence:
        if len(re.findall(r"\w+", item.quote)) < MIN_QUOTE_WORDS:
            continue
        doc = docs.get(item.source)
        if doc is not None and isinstance(
            verify_quote(doc, item.paragraph_id, item.quote), Verified
        ):
            verified.append(item)
    return verified


def _near_the_mention(
    evidence: Sequence[Evidence],
    docs: Mapping[str, SourceDoc],
    meeting_source: str,
    mention_paragraph: str,
) -> list[Evidence]:
    """The evidence in the meeting note, in the mention's own paragraph or the one either side
    of it. A quote that verifies somewhere else in the note proves nothing about the mention."""
    doc = docs.get(meeting_source)
    if doc is None or mention_paragraph not in doc.paragraphs:
        return []
    ids = list(doc.paragraphs)
    here = ids.index(mention_paragraph)
    return [
        e
        for e in evidence
        if e.source == meeting_source
        and e.paragraph_id in doc.paragraphs
        and abs(ids.index(e.paragraph_id) - here) <= 1
    ]


def accept_account_link(
    finding: Finding,
    question: OpenQuestion,
    docs: Mapping[str, SourceDoc],
    *,
    meeting_source: str,
    mention_paragraph: str | None,
) -> Accepted | NotAccepted:
    if finding.answer != "supports":
        return NotAccepted(f"the finding is {finding.answer!r}, not 'supports'")
    proposed = finding.proposed_account_id
    if proposed is None:
        return NotAccepted("no account was proposed")
    if proposed not in question.candidate_ids:
        return NotAccepted(f"the proposed account {proposed!r} is not a candidate")
    if proposed not in question.in_scope_ids:
        return NotAccepted(f"the proposed account {proposed!r} is not in scope")
    verified = _verified(finding, docs)
    if not verified:
        return NotAccepted("no evidence quote verified against its paragraph")
    if mention_paragraph is None:
        return NotAccepted("the mention could not be located in the meeting note")
    verified = _near_the_mention(verified, docs, meeting_source, mention_paragraph)
    if not verified:
        return NotAccepted(
            "no verified quote is in or next to the mention's paragraph; none is evidence about it"
        )
    passing = [c for c in question.candidate_ids if c not in question.claimed_ids]
    if len(passing) > 1:
        return NotAccepted(
            f"several accounts pass the checks ({', '.join(passing)}); R8 keeps the mention flagged"
        )
    if passing != [proposed]:
        return NotAccepted("the proposed account is not the one account that passes the checks")
    return Accepted(evidence=verified[0], account_id=proposed)


def accept_label(
    finding: Finding,
    fact_paragraph_id: str,
    docs: Mapping[str, SourceDoc],
    allowed: Collection[str],
) -> Accepted | NotAccepted:
    if finding.answer != "supports":
        return NotAccepted(f"the finding is {finding.answer!r}, not 'supports'")
    label = finding.proposed_label
    if label is None or label not in allowed:
        return NotAccepted(f"the proposed label {label!r} is not an allowed label")
    verified = _verified(finding, docs)
    if not verified:
        return NotAccepted("no evidence quote verified against its paragraph")
    same = [e for e in verified if e.paragraph_id == fact_paragraph_id]
    if not same:
        return NotAccepted("label evidence must be in the same paragraph as the fact it labels")
    return Accepted(evidence=same[0], label=label)
