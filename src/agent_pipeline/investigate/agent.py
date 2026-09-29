"""The bounded investigation loop (DESIGN.md section 5.2, D14).

For each open question the model is asked for one step at a time: a read-only tool to run, or
`finish` with a finding. Code runs the tool and hands the result back. At most `MAX_QUESTIONS`
questions per report and `MAX_TOOL_CALLS` tool calls each; the rest stay unresolved. The loop
only reads. Any model failure leaves the question inconclusive and never fails the run: this is
an optional stage (section 8.4), and the conservative default it leaves is always safe.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agent_pipeline.investigate.schemas import AgentStep, Finding
from agent_pipeline.investigate.tools import ReadOnlyTools
from agent_pipeline.llm import RunawayCostError
from agent_pipeline.reconcile.questions import OpenQuestion

MAX_QUESTIONS = 5
MAX_TOOL_CALLS = 6


class InvestigationModel(Protocol):
    def step(self, question: OpenQuestion, observations: list[dict[str, Any]]) -> AgentStep: ...


@dataclass(frozen=True)
class QuestionResult:
    question: OpenQuestion
    finding: Finding | None
    tool_calls: int
    note: str = ""


def _arguments(step: AgentStep) -> dict[str, Any]:
    """The arguments the requested tool takes, read from the step's fields."""
    if step.tool == "read_paragraphs":
        return {"source": step.source, "start": step.start, "end": step.end}
    if step.tool == "find_in_source":
        return {"text": step.text or "", "source": step.source}
    if step.tool == "get_accounts":
        return {"platform": step.platform, "holder": step.holder, "account_type": step.account_type}
    if step.tool == "get_ledger_entry":
        return {"entry_id": step.entry_id or ""}
    return {}


def _investigate_one(
    question: OpenQuestion, tools: ReadOnlyTools, model: InvestigationModel
) -> QuestionResult:
    observations: list[dict[str, Any]] = []
    calls = 0
    while True:
        try:
            step = model.step(question, list(observations))
        except (AssertionError, RunawayCostError):
            # A replay transport raising on a live call, and the per-run cost guard, are
            # not model failures: hiding them would let a cache miss pass an offline test.
            raise
        except Exception as exc:  # noqa: BLE001  # optional stage: any failure keeps the defaults
            return QuestionResult(question, None, calls, f"model failure: {exc}")
        if step.tool == "finish":
            if step.finding is None:
                return QuestionResult(question, None, calls, "finished without a finding")
            return QuestionResult(question, step.finding, calls)
        if calls >= MAX_TOOL_CALLS:
            return QuestionResult(question, None, calls, "tool-call budget spent")
        arguments = _arguments(step)
        observations.append(
            {"tool": step.tool, "arguments": arguments, "result": tools.call(step.tool, arguments)}
        )
        calls += 1


def investigate(
    questions: Sequence[OpenQuestion], tools: ReadOnlyTools, model: InvestigationModel
) -> list[QuestionResult]:
    results: list[QuestionResult] = []
    for index, question in enumerate(questions):
        if index >= MAX_QUESTIONS:
            results.append(
                QuestionResult(question, None, 0, f"over the limit of {MAX_QUESTIONS} questions")
            )
            continue
        results.append(_investigate_one(question, tools, model))
    return results
