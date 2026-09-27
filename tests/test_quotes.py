"""Quote and label verification (T5, DESIGN.md section 4.2).

Every extracted fact carries a quote that code checks against the specific paragraph it
claims to be in; a decisive label (basis, excluded-item class, ...) additionally needs its
own evidence quote in that same paragraph, or it falls back to a conservative default that
never lets the model's word alone select a value or include something client-01-style
excluded items must stay out of.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.extract.quotes import (
    CONSERVATIVE_DEFAULTS,
    Accepted,
    Defaulted,
    LabelEvidence,
    Rejected,
    Verified,
    verify_label,
    verify_quote,
)

from agent_pipeline.sources.document import SourceDoc


def _doc() -> SourceDoc:
    return SourceDoc(
        path=Path("meeting_notes.docx"),
        paragraphs={
            "p1": "Annual review meeting with Margaret Hughes,\nheld   12 May 2026 at our offices.",
            "p2": "We agreed she would move £20,000 from the cash account into the ISA.",
        },
    )


def test_verify_quote_normalises_whitespace() -> None:
    doc = _doc()
    result = verify_quote(doc, "p1", "held 12 May 2026 at our offices.")
    assert isinstance(result, Verified)
    assert result.paragraph_id == "p1"


def test_verify_quote_rejects_when_quote_is_in_a_different_paragraph() -> None:
    doc = _doc()
    # This exact sentence is verbatim in p2, not p1: checking it against p1 must fail,
    # not fall back to searching the whole document.
    result = verify_quote(
        doc, "p1", "We agreed she would move £20,000 from the cash account into the ISA."
    )
    assert isinstance(result, Rejected)
    assert "p1" in result.reason


def test_verify_quote_rejects_unknown_paragraph() -> None:
    doc = _doc()
    result = verify_quote(doc, "p99", "anything")
    assert isinstance(result, Rejected)


def test_verify_quote_rejects_text_not_present_anywhere() -> None:
    doc = _doc()
    result = verify_quote(doc, "p1", "she would like to gift the whole portfolio")
    assert isinstance(result, Rejected)


def test_verify_label_accepted_when_evidence_verifies_in_the_same_paragraph() -> None:
    doc = _doc()
    evidence = LabelEvidence(paragraph_id="p2", quote="We agreed she would move £20,000")
    result = verify_label(
        doc,
        fact_paragraph_id="p2",
        label="viewed_in_meeting",
        evidence=evidence,
        default="recalled",
    )
    assert isinstance(result, Accepted)
    assert result.label == "viewed_in_meeting"


def test_verify_label_defaults_when_evidence_is_in_a_different_paragraph() -> None:
    doc = _doc()
    # The evidence quote is real and verifies fine, but against p1 -- not the fact's own
    # paragraph p2 -- so it must not be trusted to label the p2 fact.
    evidence = LabelEvidence(paragraph_id="p1", quote="held 12 May 2026 at our offices.")
    result = verify_label(
        doc,
        fact_paragraph_id="p2",
        label="viewed_in_meeting",
        evidence=evidence,
        default="recalled",
    )
    assert isinstance(result, Defaulted)
    assert result.label == "recalled"
    assert "paragraph" in result.reason


def test_verify_label_defaults_when_evidence_quote_is_unverified() -> None:
    doc = _doc()
    evidence = LabelEvidence(paragraph_id="p2", quote="this sentence does not appear anywhere")
    result = verify_label(
        doc,
        fact_paragraph_id="p2",
        label="viewed_in_meeting",
        evidence=evidence,
        default="recalled",
    )
    assert isinstance(result, Defaulted)
    assert result.label == "recalled"


def test_conservative_defaults_cover_the_client_01_labels() -> None:
    # basis: unclear -> "recalled", so it only confirms or conflicts, never selects (R3).
    assert CONSERVATIVE_DEFAULTS["basis"] == "recalled"
    # excluded_class: unclear -> "tangent", so it never appears at all -- omitting beats
    # wrongly including (P6).
    assert CONSERVATIVE_DEFAULTS["excluded_class"] == "tangent"
