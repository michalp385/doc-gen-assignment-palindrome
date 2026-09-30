"""A handling instruction must carry no figure. Digits and currency symbols were already refused;
an amount or share written in words reaches the writer just as well ("half into each ISA"), so the
same check refuses those, using the writer gate's own word-form patterns. An ordinary "one"
(one short sentence) is not a figure."""

from __future__ import annotations

import pytest

from agent_pipeline.extract.guidance import (
    RawDirective,
    RawGuidanceProposal,
    extract_directives,
)

EVIDENCE = "Treat the money's origin with appropriate sensitivity for this client."
GUIDANCE = f"General notes.\n\n{EVIDENCE}\n"


class _Model:
    def __init__(self, instruction: str) -> None:
        self.instruction = instruction

    def propose(self, guidance_text: str, people: list[str], sections: list[str]):
        return RawGuidanceProposal(
            directives=[
                RawDirective(
                    sections=["background_objectives"],
                    instruction=self.instruction,
                    person=None,
                    evidence=EVIDENCE,
                )
            ]
        )


def _run(instruction: str):
    return extract_directives(
        GUIDANCE, ["Jean Fletcher"], ["background_objectives"], _Model(instruction)
    )


@pytest.mark.parametrize(
    "instruction",
    [
        "Say that half goes into each ISA, stated gently.",
        "Mention the forty thousand pounds only briefly.",
        "Refer to the fifty per cent share carefully.",
        "Describe a quarter of the money as already spent.",
    ],
)
def test_an_instruction_carrying_a_figure_in_words_is_not_passed_on(instruction: str) -> None:
    result = _run(instruction)

    assert result.directives == []
    (item,) = result.review_items
    assert item.kind == "ambiguity" and "figure" in item.detail


def test_an_ordinary_number_word_is_not_a_figure() -> None:
    result = _run("Keep the reference to where the money came from to one short sentence.")

    assert len(result.directives) == 1
