"""The bounded investigation loop (DESIGN section 5.2), tests first.

At most 5 questions and 6 tool calls each, in the order given. The loop only reads: it runs
the model's requested read-only tool and feeds the result back. A model failure of any kind
leaves the question inconclusive and never fails the run (an optional stage, section 8.4).
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.investigate.agent import MAX_QUESTIONS, MAX_TOOL_CALLS, investigate
from agent_pipeline.investigate.schemas import AgentStep, Evidence, Finding
from agent_pipeline.investigate.tools import ReadOnlyTools
from agent_pipeline.reconcile.questions import OpenQuestion
from agent_pipeline.sources.document import SourceDoc


def _tools() -> ReadOnlyTools:
    doc = SourceDoc(path=Path("m.docx"), paragraphs={"p1": "Her other account is on Holloway."})
    return ReadOnlyTools({"m.docx": doc}, [], {})


def _question(n: int) -> OpenQuestion:
    return OpenQuestion(
        id=f"q{n}",
        kind="account_link",
        mention="m",
        candidate_ids=("A", "B"),
        claimed_ids=(),
        in_scope_ids=("A", "B"),
    )


def _finish(question_id: str = "q1", answer: str = "inconclusive") -> AgentStep:
    return AgentStep(
        tool="finish",
        finding=Finding(
            question_id=question_id,
            answer=answer,  # type: ignore[arg-type]  # the test passes the literal by name
            proposed_account_id=None,
            proposed_label=None,
            evidence=[Evidence(source="m.docx", paragraph_id="p1", quote="Her other account")],
            explanation="",
        ),
    )


def _read() -> AgentStep:
    return AgentStep(tool="list_sources")


class Scripted:
    """Answers each step from a per-question script; records what it was shown."""

    def __init__(self, scripts: dict[str, list[AgentStep]]) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self.seen: list[tuple[str, int]] = []

    def step(self, question: OpenQuestion, observations: list[dict]) -> AgentStep:  # type: ignore[type-arg]
        self.seen.append((question.id, len(observations)))
        script = self._scripts[question.id]
        return script.pop(0) if script else _read()


def test_a_tool_result_is_fed_back_and_the_finding_is_returned() -> None:
    model = Scripted({"q1": [_read(), _finish("q1", "supports")]})
    [result] = investigate([_question(1)], _tools(), model)
    assert result.finding is not None and result.finding.answer == "supports"
    assert result.tool_calls == 1
    assert model.seen == [("q1", 0), ("q1", 1)]  # the second step saw one observation


def test_a_model_that_never_finishes_is_stopped_at_the_tool_budget() -> None:
    model = Scripted({"q1": []})  # always asks for another tool
    [result] = investigate([_question(1)], _tools(), model)
    assert result.tool_calls == MAX_TOOL_CALLS == 6
    assert result.finding is None and "budget" in result.note
    assert len(model.seen) <= MAX_TOOL_CALLS + 1  # six tool steps and one forced last step


def test_only_the_first_five_questions_are_investigated_in_order() -> None:
    questions = [_question(n) for n in range(1, 8)]
    model = Scripted({q.id: [_finish(q.id)] for q in questions})
    results = investigate(questions, _tools(), model)
    assert MAX_QUESTIONS == 5
    assert [r.question.id for r in results] == [f"q{n}" for n in range(1, 8)]
    assert {qid for qid, _ in model.seen} == {f"q{n}" for n in range(1, 6)}
    assert all(r.finding is None and "limit" in r.note for r in results[5:])


def test_a_model_failure_leaves_the_question_inconclusive_and_the_rest_running() -> None:
    class Flaky(Scripted):
        def step(self, question, observations):  # type: ignore[no-untyped-def]
            if question.id == "q1":
                raise RuntimeError("API down")
            return super().step(question, observations)

    model = Flaky({"q2": [_finish("q2", "supports")]})
    results = investigate([_question(1), _question(2)], _tools(), model)
    assert results[0].finding is None and "model failure" in results[0].note
    assert results[1].finding is not None


def test_a_replay_cache_miss_and_a_cost_guard_are_never_swallowed() -> None:
    import pytest

    from agent_pipeline.llm import RunawayCostError

    class Raising(Scripted):
        def __init__(self, error: Exception) -> None:
            super().__init__({})
            self._error = error

        def step(self, question, observations):  # type: ignore[no-untyped-def]
            raise self._error

    for error in (AssertionError("live call in a replay"), RunawayCostError("over the ceiling")):
        with pytest.raises(type(error)):
            investigate([_question(1)], _tools(), Raising(error))


def test_a_request_for_an_unknown_tool_is_an_error_observation_not_a_write() -> None:
    model = Scripted({"q1": [AgentStep.model_construct(tool="write_ledger"), _finish()]})
    [result] = investigate([_question(1)], _tools(), model)
    assert result.finding is not None  # the loop carried on


def test_no_questions_means_no_model_call() -> None:
    model = Scripted({})
    assert investigate([], _tools(), model) == []
    assert model.seen == []
