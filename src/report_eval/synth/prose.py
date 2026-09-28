"""The prose checks for the synthetic clients' meeting notes (D4, DESIGN.md section 10.8).

An LLM writes the meeting note around required phrases; code checks the note and rejects it
otherwise: every required phrase must appear verbatim, and no figure the scenario did not plan
may appear (a money amount, a percentage, or a figure written in words). The model is
injected (`ProseModel`), so the loop is exercised offline with a scripted one; the live model
and its prompt belong to the one-off generation of the frozen clients, not to this module.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from agent_pipeline.gates.deterministic import (
    MONEY_RE,
    PERCENT_RE,
    WORD_FIGURE_RE,
    WORD_PERCENT_RE,
)
from agent_pipeline.gates.truth import figure_core
from report_eval.synth.phrases import RequiredPhrase


class ProseModel(Protocol):
    def write(self, brief: str, required: list[str], feedback: str | None) -> str: ...


class ProseRejected(Exception):
    """The model never produced a note that passes the checks; nothing is written."""


def check_prose(
    text: str, required: list[RequiredPhrase], extra_allowed: Iterable[str] = ()
) -> list[str]:
    """Every problem with a note, empty when it passes. A planned figure may repeat with any
    qualifier ("around", "a little over"); an unplanned one never appears."""
    problems = [
        f"missing required phrase: {phrase.text!r}"
        for phrase in required
        if phrase.text not in text
    ]
    allowed = {figure for phrase in required for figure in phrase.figures} | set(extra_allowed)
    found = {re.sub(r"£\s+", "£", f) for f in MONEY_RE.findall(text)}
    for figure in sorted(found):
        if figure_core(figure) not in allowed:
            problems.append(f"unplanned figure: {figure}")
    for percent in sorted(set(PERCENT_RE.findall(text))):
        problems.append(f"unplanned figure: {percent}")
    for pattern in (WORD_FIGURE_RE, WORD_PERCENT_RE):
        if match := pattern.search(text):
            problems.append(f"unplanned figure written in words: {match.group(0)!r}")
    return problems


def generate_prose(
    model: ProseModel, brief: str, required: list[RequiredPhrase], max_rounds: int = 3
) -> str:
    """Ask the model for a note, feeding each round's problems back, up to `max_rounds`. A
    note that never passes is rejected, never patched by code."""
    required_text = [phrase.text for phrase in required]
    feedback: str | None = None
    problems: list[str] = []
    for _ in range(max_rounds):
        text = model.write(brief, required_text, feedback)
        problems = check_prose(text, required)
        if not problems:
            return text
        feedback = "; ".join(problems)
    raise ProseRejected(f"no acceptable note after {max_rounds} rounds: {problems}")
