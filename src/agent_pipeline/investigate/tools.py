"""The investigation agent's tools: read-only by construction (DESIGN.md section 5.2).

Five tools, and no way to write, select a value or change a rule. `ReadOnlyTools` keeps its own
copies of what it was given and only ever returns fresh plain data; `call` dispatches a tool by
name and refuses any other name. Errors come back as `{"error": ...}` for the model to read,
never as an exception.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from agent_pipeline.extract.meeting import find_in_source
from agent_pipeline.ledger import Account
from agent_pipeline.sources.document import SourceDoc

TOOL_NAMES = (
    "list_sources",
    "read_paragraphs",
    "find_in_source",
    "get_accounts",
    "get_ledger_entry",
)


class ReadOnlyTools:
    def __init__(
        self,
        sources: Mapping[str, SourceDoc],
        accounts: Sequence[Account],
        ledger_entries: Mapping[str, object] | None = None,
    ) -> None:
        self._sources = copy.deepcopy(dict(sources))
        self._accounts = copy.deepcopy(list(accounts))
        self._entries = copy.deepcopy(dict(ledger_entries or {}))

    def list_sources(self) -> list[dict[str, Any]]:
        return [
            {"source": name, "paragraphs": len(doc.paragraphs)}
            for name, doc in self._sources.items()
        ]

    def read_paragraphs(self, source: str, start: str, end: str) -> dict[str, str]:
        doc = self._sources.get(source)
        if doc is None:
            return {"error": f"no source {source!r}"}
        ids = list(doc.paragraphs)
        if start not in ids or end not in ids:
            return {"error": f"paragraph ids must be among {ids}"}
        lo, hi = sorted((ids.index(start), ids.index(end)))
        return {pid: doc.paragraphs[pid] for pid in ids[lo : hi + 1]}

    def find_in_source(self, text: str, source: str | None = None) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        for name, doc in self._sources.items():
            if source is not None and name != source:
                continue
            for hit in find_in_source(doc, text):
                found.append({"source": name, "paragraph_id": hit.paragraph_id, "text": hit.text})
        return found

    def get_accounts(
        self,
        platform: str | None = None,
        holder: str | None = None,
        account_type: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = []
        for account in self._accounts:
            if platform and (account.platform or "").lower() != platform.lower():
                continue
            if holder and not any(holder.lower() in o.lower() for o in account.owners):
                continue
            if account_type and account_type.lower() not in account.type.lower():
                continue
            rows.append(
                {
                    "id": account.id,
                    "type": account.type,
                    "platform": account.platform,
                    "owners": list(account.owners),
                    "status": account.status,
                    "in_scope": account.in_scope,
                }
            )
        return rows

    def get_ledger_entry(self, entry_id: str) -> Any:
        if entry_id not in self._entries:
            return {"error": f"no ledger entry {entry_id!r}"}
        return copy.deepcopy(self._entries[entry_id])

    def call(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if name not in TOOL_NAMES:
            return {"error": f"unknown tool {name!r}; the tools are {list(TOOL_NAMES)}"}
        try:
            return getattr(self, name)(**arguments)
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
