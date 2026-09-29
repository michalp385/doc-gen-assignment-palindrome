"""An aspiration keeps the rest of its sentence (tests first; verifier finding 3).

The extractor's quote of an aspiration can stop before the caveat that makes it an
aspiration ("... but was clear that is not for today"). Code extends the quote to the end of
its own sentence in the source paragraph, verbatim, so the writer always sees the caveat.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.extract.schemas import ExcludedItem, LabelEvidence, Quote
from agent_pipeline.pipeline import _build_excluded
from agent_pipeline.sources.document import SourceDoc

SENTENCE = (
    "She mentioned she may want to discuss a future gift, but was clear that is not for "
    "today and nothing should be actioned on it now."
)
PARAGRAPH = f"Otherwise nothing changed. {SENTENCE} We closed the meeting."


def _item(item_class: str, text: str) -> ExcludedItem:
    return ExcludedItem(
        item_class=item_class,  # type: ignore[arg-type]  # test passes the literal by name
        text=Quote(paragraph_id="p1", text=text),
        class_evidence=LabelEvidence(paragraph_id="p1", text=text),
    )


def _doc() -> SourceDoc:
    return SourceDoc(path=Path("m.docx"), paragraphs={"p1": PARAGRAPH})


def test_truncated_aspiration_quote_is_extended_to_the_sentence_end() -> None:
    truncated = "She mentioned she may want to discuss a future gift"
    [built] = _build_excluded([_item("aspiration", truncated)], "m.docx", _doc())
    assert built.quote == SENTENCE
    assert built.description == SENTENCE


def test_a_whole_sentence_quote_is_unchanged() -> None:
    [built] = _build_excluded([_item("aspiration", SENTENCE)], "m.docx", _doc())
    assert built.quote == SENTENCE


def test_a_quote_not_found_in_its_paragraph_is_unchanged() -> None:
    [built] = _build_excluded([_item("aspiration", "something else")], "m.docx", _doc())
    assert built.quote == "something else"


def test_other_classes_are_left_alone() -> None:
    truncated = "She mentioned she may want to discuss a future gift"
    [built] = _build_excluded([_item("tangent", truncated)], "m.docx", _doc())
    assert built.quote == truncated
