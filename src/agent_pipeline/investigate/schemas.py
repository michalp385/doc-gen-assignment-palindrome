"""The investigation agent's structured output (DESIGN.md section 5.2).

One `AgentStep` per model call: either a request for one read-only tool, or `finish` with a
`Finding`. The finding is only a proposal: quotes are verified and a proposed account or label
is accepted or rejected by code (`accept.py`); nothing here reaches the report.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(_Strict):
    source: str
    paragraph_id: str
    quote: str


class Finding(_Strict):
    question_id: str
    answer: Literal["supports", "contradicts", "inconclusive"]
    proposed_account_id: str | None = None
    proposed_label: str | None = None
    evidence: list[Evidence]
    explanation: str


class AgentStep(_Strict):
    """`tool` names the read-only tool to run next, or `finish`. Only the arguments that tool
    takes are read; the rest stay null."""

    tool: Literal[
        "list_sources",
        "read_paragraphs",
        "find_in_source",
        "get_accounts",
        "get_ledger_entry",
        "finish",
    ]
    source: str | None = None
    start: str | None = None
    end: str | None = None
    text: str | None = None
    platform: str | None = None
    holder: str | None = None
    account_type: str | None = None
    entry_id: str | None = None
    finding: Finding | None = None
