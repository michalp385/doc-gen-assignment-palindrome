"""An open-action review item names what is to be confirmed (tests first). The extractor's
quote is often a bare pronoun sentence ("she will confirm it for us"); the adviser reading the
review sheet needs the subject, which is in the same meeting-note paragraph. Code appends that
paragraph verbatim -- no model wording, no invented detail.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.extract.schemas import LabelEvidence, OpenAction, Quote
from agent_pipeline.pipeline import _open_action_item
from agent_pipeline.sources.document import SourceDoc

PARAGRAPH = (
    "Ann also has a cash account, but she could not remember the balance; "
    "she will confirm it for us."
)


def _action(text: str, paragraph_id: str = "p1", blocking: bool = False) -> OpenAction:
    return OpenAction(
        text=Quote(paragraph_id=paragraph_id, text=text),
        blocking=blocking,
        blocking_evidence=LabelEvidence(paragraph_id=paragraph_id, text=text),
    )


def _doc() -> SourceDoc:
    return SourceDoc(path=Path("meeting.docx"), paragraphs={"p1": PARAGRAPH})


def test_detail_carries_the_source_paragraph() -> None:
    item = _open_action_item(_action("she will confirm it for us."), _doc())
    assert item.kind == "open_action"
    assert "she will confirm it for us." in item.detail
    assert "cash account" in item.detail
    assert "Ann" in item.detail


def test_detail_is_the_quote_alone_when_it_is_the_whole_paragraph() -> None:
    item = _open_action_item(_action(PARAGRAPH), _doc())
    assert item.detail == PARAGRAPH


def test_blocking_flag_is_kept() -> None:
    assert _open_action_item(_action("she will confirm it for us.", blocking=True), _doc()).blocking


def test_unknown_paragraph_falls_back_to_the_quote() -> None:
    item = _open_action_item(_action("confirm the timing.", paragraph_id="p9"), _doc())
    assert item.detail == "confirm the timing."
