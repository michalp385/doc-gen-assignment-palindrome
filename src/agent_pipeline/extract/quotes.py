"""Verify extraction quotes and decisive labels against their source (T5, DESIGN.md 4.1-4.2).

Two checks, both against the specific paragraph a quote claims to be from, never "appears
somewhere in the document":

- `verify_quote` proves a fact's quote is real.
- `verify_label` additionally requires a decisive label's own evidence quote to sit in the
  *same* paragraph as the fact it labels; evidence from elsewhere, or that doesn't verify,
  falls back to a conservative default rather than letting the model's word alone select a
  value or decide what the report includes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_pipeline.sources.document import SourceDoc

# What an unclear or unverified label becomes, for each label client 01 exercises. The rest
# (money class, blocking, disposal extent) are added in M2 as clients that use them arrive.
CONSERVATIVE_DEFAULTS: dict[str, str] = {
    "basis": "recalled",  # never selects a value; only confirms or conflicts (R3)
    "excluded_class": "tangent",  # never appears at all; omitting beats wrongly including (P6)
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Verified:
    paragraph_id: str
    quote: str


@dataclass(frozen=True)
class Rejected:
    paragraph_id: str
    quote: str
    reason: str


def verify_quote(doc: SourceDoc, paragraph_id: str, quote: str) -> Verified | Rejected:
    """Check that `quote` occurs verbatim (whitespace-normalised) in paragraph `paragraph_id`."""
    text = doc.paragraph_text(paragraph_id)
    if text is None:
        return Rejected(paragraph_id, quote, f"no paragraph {paragraph_id!r} in {doc.path}")
    if _normalize(quote) not in _normalize(text):
        return Rejected(paragraph_id, quote, f"quote not found in paragraph {paragraph_id!r}")
    return Verified(paragraph_id, quote)


@dataclass(frozen=True)
class LabelEvidence:
    paragraph_id: str
    quote: str


@dataclass(frozen=True)
class Accepted:
    label: str


@dataclass(frozen=True)
class Defaulted:
    label: str
    reason: str


def verify_label(
    doc: SourceDoc,
    *,
    fact_paragraph_id: str,
    label: str,
    evidence: LabelEvidence,
    default: str,
) -> Accepted | Defaulted:
    """Accept `label` only with verified evidence in the fact's own paragraph; else default."""
    verified = verify_quote(doc, evidence.paragraph_id, evidence.quote)
    if isinstance(verified, Rejected):
        return Defaulted(default, f"label evidence unverified: {verified.reason}")
    if evidence.paragraph_id != fact_paragraph_id:
        return Defaulted(
            default,
            f"label evidence is in paragraph {evidence.paragraph_id!r}, "
            f"not the fact's own paragraph {fact_paragraph_id!r}",
        )
    return Accepted(label)
