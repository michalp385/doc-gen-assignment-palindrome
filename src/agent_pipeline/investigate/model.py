"""The real `InvestigationModel`: `LLMClient` plus `config/prompts/investigate.md`.

Each call is one structured step (a read-only tool request, or a finding), so the loop is
cacheable and replays exactly like every other stage. The model sees the question, the
candidates code left it, the accounts other mentions already pin down, and what its earlier
tool calls returned.
"""

from __future__ import annotations

from typing import Any

from agent_pipeline.config import PromptSpec
from agent_pipeline.investigate.agent import MAX_TOOL_CALLS
from agent_pipeline.investigate.schemas import AgentStep
from agent_pipeline.llm import LLMClient
from agent_pipeline.reconcile.questions import OpenQuestion


class LLMInvestigationModel:
    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def step(self, question: OpenQuestion, observations: list[dict[str, Any]]) -> AgentStep:
        result = self._llm.structured(
            stage="investigate",
            prompt=self._prompt,
            inputs={
                "question": {
                    "id": question.id,
                    "kind": question.kind,
                    "mention": question.mention,
                    "candidate_account_ids": list(question.candidate_ids),
                    "in_scope_account_ids": list(question.in_scope_ids),
                    "already_claimed_account_ids": list(question.claimed_ids),
                },
                "tool_calls_left": MAX_TOOL_CALLS - len(observations),
                "observations": observations,
            },
            schema=AgentStep,
        )
        return result.output
