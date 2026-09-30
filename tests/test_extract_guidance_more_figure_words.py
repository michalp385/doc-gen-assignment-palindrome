"""More ways to write an amount or a share in words, which the first word-form check let through:
"forty thousand into each ISA", "ten pounds", "a third", "two thirds", "three quarters". A handling
instruction carrying one is refused like one carrying a digit. Ordinary tone instructions stay."""

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


def _kept(instruction: str) -> bool:
    result = extract_directives(
        GUIDANCE, ["Jean Fletcher"], ["background_objectives"], _Model(instruction)
    )
    return bool(result.directives)


@pytest.mark.parametrize(
    "instruction",
    [
        "Put forty thousand into each ISA, stated gently.",
        "Mention the ten pounds only briefly.",
        "Say a third goes into the new account.",
        "Describe two thirds of it as already spent.",
        "Refer to three quarters of the sum carefully.",
        "Mention the two hundred thousand received.",
    ],
)
def test_an_amount_or_share_in_words_is_refused(instruction: str) -> None:
    assert not _kept(instruction)


@pytest.mark.parametrize(
    "instruction",
    [
        "Treat both clients equally, in restrained and sensitive language.",
        "Keep the reference to where the money came from to one short sentence.",
        "Refer to the source of the new funds in restrained, sensitive language.",
    ],
)
def test_an_ordinary_tone_instruction_is_kept(instruction: str) -> None:
    assert _kept(instruction)
