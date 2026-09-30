"""D29: a handling note the pipeline applied, and one it could not apply ("check it by hand"), are
both in the ledger's review items -- and must both reach the adviser's review sheet. Recorded but
unprinted, the second is a silent drop: nothing tells the adviser a client-specific instruction
was not followed."""

from __future__ import annotations

from agent_pipeline.assemble import RunSummary, build_review_sheet
from agent_pipeline.config import ReportConfig, Section, StageConfig
from agent_pipeline.ledger import Ledger, ReviewItem


def _sheet(*items: ReviewItem) -> str:
    config = ReportConfig(
        document_title="Investment Advice Report",
        global_instructions="Write in British English.",
        stages={"write": StageConfig(model="gpt-6-luna", reasoning_effort="low")},
        sections=[Section(id="s", title="S", use_if="always", template="<<s>>")],
    )
    return build_review_sheet(
        config,
        Ledger(client="x", review=list(items)),
        "draft",
        RunSummary(client="x", release_state="draft"),
    )


def _notes_section(sheet: str) -> str:
    return sheet.split("## Notes\n\n", 1)[1].split("\n\n## ", 1)[0]


def test_an_applied_handling_note_is_on_the_review_sheet() -> None:
    sheet = _sheet(
        ReviewItem(
            id="r1",
            kind="handling_note",
            detail="a handling note was applied to background_objectives: be gentle",
        )
    )

    assert "a handling note was applied to background_objectives: be gentle" in _notes_section(
        sheet
    )


def test_a_handling_note_that_could_not_be_applied_is_on_the_review_sheet() -> None:
    sheet = _sheet(
        ReviewItem(
            id="r2",
            kind="ambiguity",
            detail="a handling note names 'Zed', who is not a holder; the note was not applied.",
        )
    )

    assert "the note was not applied" in _notes_section(sheet)
