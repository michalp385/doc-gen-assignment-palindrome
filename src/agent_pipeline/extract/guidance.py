"""Internal guidance to handling directives (DECISIONS.md D8).

G10 forbids internal guidance text in the report, yet a client-specific note (how to treat a
source of funds, who "the client" is) must shape the writing. So the model reads the notes once and
proposes directives (which sections, one instruction on how to write, the person, and the note's
own words as evidence); code then verifies each. A directive reaches the writer only when:

- its evidence is a verbatim quote of the guidance of at least four words (a proposal with no
  anchor, or one that is in every set of notes, is dropped),
- its sections are report sections that exist,
- a named person resolves to a holder on the account data (an unresolved name is a review item,
  never a guess), and
- its instruction shares no six-word run with the guidance (the same test G10 applies to the
  report, applied one step earlier so the writer is never handed the notes' wording), and
- its instruction carries no figure (every writer input is digit-free, D1).

Each directive that is applied gets an informational review item, so the adviser can see what the
notes changed.

The writer receives the instruction only, never the guidance text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from agent_pipeline.config import PromptSpec
from agent_pipeline.gates.deterministic import word_ngrams
from agent_pipeline.llm import LLMClient
from agent_pipeline.reconcile.marker_text import join_natural
from agent_pipeline.reconcile.review import ReviewItemInput

LEAK_RUN_WORDS = 6  # the same run length G10 uses for internal guidance text
MIN_EVIDENCE_WORDS = 4  # a shorter quote ("the", "client") is in every set of notes
_FIGURE_RE = re.compile(r"[0-9£$€%]")


class RawDirective(BaseModel):
    sections: list[str]  # report section ids the instruction applies to
    instruction: str  # how to write, in the model's own words, one sentence
    person: str | None = None  # a person the instruction is about, as the notes name them
    evidence: str  # the note's own words this rests on, copied verbatim


class RawGuidanceProposal(BaseModel):
    directives: list[RawDirective] = []


class GuidanceModel(Protocol):
    def propose(
        self, guidance_text: str, people: list[str], sections: list[str]
    ) -> RawGuidanceProposal: ...


class LLMGuidanceModel:
    """The real `GuidanceModel`, wrapping `LLMClient` and `config/prompts/extract_guidance.md`."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def propose(
        self, guidance_text: str, people: list[str], sections: list[str]
    ) -> RawGuidanceProposal:
        result = self._llm.structured(
            stage="extract",
            prompt=self._prompt,
            inputs={"guidance_text": guidance_text, "people": people, "sections": sections},
            schema=RawGuidanceProposal,
        )
        return result.output


@dataclass(frozen=True)
class Directive:
    sections: tuple[str, ...]
    instruction: str
    person: str | None = None  # the holder's full name, resolved against the account data

    def for_writer(self) -> str:
        """The one line a writer prompt reads: the person by first name, then the instruction."""
        if self.person is None:
            return self.instruction
        return f"About {self.person.split()[0]}: {self.instruction}"


@dataclass
class GuidanceResult:
    directives: list[Directive] = field(default_factory=list)
    review_items: list[ReviewItemInput] = field(default_factory=list)


def _squash(text: str) -> str:
    """Whitespace-collapsed, lower-cased, with curly quotes made straight, so a model that copies
    an apostrophe as a curly one still anchors."""
    plain = text.replace("\u2019", "'").replace("\u2018", "'")
    plain = plain.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", plain).strip().lower()


def _resolve_person(name: str, people: list[str]) -> str | None:
    wanted = name.strip().lower()
    for person in people:
        if wanted == person.lower() or wanted == person.split()[0].lower():
            return person
    return None


def extract_directives(
    guidance_text: str, people: list[str], sections: list[str], model: GuidanceModel
) -> GuidanceResult:
    result = GuidanceResult()
    if not guidance_text.strip():
        return result
    guidance_squashed = _squash(guidance_text)
    guidance_runs = word_ngrams(guidance_text, LEAK_RUN_WORDS)
    unique_people = list(dict.fromkeys(people))

    for raw in model.propose(guidance_text, unique_people, sections).directives:
        evidence = _squash(raw.evidence)
        if len(evidence.split()) < MIN_EVIDENCE_WORDS or evidence not in guidance_squashed:
            continue
        kept_sections = tuple(s for s in raw.sections if s in sections)
        if not kept_sections or not raw.instruction.strip():
            continue
        person = None
        if raw.person:
            person = _resolve_person(raw.person, unique_people)
            if person is None:
                result.review_items.append(
                    ReviewItemInput(
                        kind="ambiguity",
                        blocking=False,
                        detail=(
                            f"a handling note names {raw.person!r}, who is not a holder on the "
                            "account data; the note was not applied. Check it by hand."
                        ),
                        refs=[],
                    )
                )
                continue
        if _FIGURE_RE.search(raw.instruction):
            result.review_items.append(
                ReviewItemInput(
                    kind="ambiguity",
                    blocking=False,
                    detail=(
                        "a handling note could not be passed on without a figure, so it was "
                        "not applied. Check it by hand."
                    ),
                    refs=[],
                )
            )
            continue
        if word_ngrams(raw.instruction, LEAK_RUN_WORDS) & guidance_runs:
            result.review_items.append(
                ReviewItemInput(
                    kind="ambiguity",
                    blocking=False,
                    detail=(
                        "a handling note could not be passed on without repeating the notes' "
                        "own wording, so it was not applied. Check it by hand."
                    ),
                    refs=[],
                )
            )
            continue
        directive = Directive(
            sections=kept_sections, instruction=raw.instruction.strip(), person=person
        )
        result.directives.append(directive)
        result.review_items.append(
            ReviewItemInput(
                kind="handling_note",
                blocking=False,
                detail=(
                    f"a handling note was applied to {join_natural(list(kept_sections))}: "
                    f"{directive.for_writer()}"
                ),
                refs=[],
            )
        )
    return result
