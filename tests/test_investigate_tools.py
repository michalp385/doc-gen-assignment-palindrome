"""The investigation agent's tools are read-only (DESIGN section 5.2), tests first.

Five tools, and no way to write, select a value or change a rule: the dispatcher refuses
anything else, and calling every tool leaves the sources, accounts and ledger entries as they
were.
"""

from __future__ import annotations

import copy
from pathlib import Path

from agent_pipeline.investigate.tools import TOOL_NAMES, ReadOnlyTools
from agent_pipeline.ledger import Account
from agent_pipeline.sources.document import SourceDoc


def _tools() -> ReadOnlyTools:
    doc = SourceDoc(
        path=Path("meeting_notes.docx"),
        paragraphs={
            "p1": "Annual review meeting held 18 May 2026.",
            "p2": "She also asked about her other account on the Holloway platform.",
            "p3": "We agreed to confirm the value of that account.",
        },
    )
    accounts = [
        Account(
            id="Y-ISA", type="Stocks & Shares ISA", owners=["Yvonne Pascoe"], platform="Holloway"
        ),
        Account(
            id="Y-GIA",
            type="General Investment Account",
            owners=["Yvonne Pascoe"],
            platform="Holloway",
        ),
        Account(
            id="B-ISA", type="Stocks & Shares ISA", owners=["Bob Pascoe"], platform="Brightwell"
        ),
    ]
    return ReadOnlyTools({"meeting_notes.docx": doc}, accounts, {"fact.a": {"value": "1"}})


def test_exactly_five_tools_and_no_public_method_beyond_them() -> None:
    assert TOOL_NAMES == (
        "list_sources",
        "read_paragraphs",
        "find_in_source",
        "get_accounts",
        "get_ledger_entry",
    )
    public = {n for n in dir(_tools()) if not n.startswith("_") and callable(getattr(_tools(), n))}
    assert public == set(TOOL_NAMES) | {"call"}


def test_list_sources_gives_roles_and_paragraph_counts() -> None:
    assert _tools().list_sources() == [{"source": "meeting_notes.docx", "paragraphs": 3}]


def test_read_paragraphs_returns_the_range_by_id() -> None:
    result = _tools().read_paragraphs("meeting_notes.docx", "p2", "p3")
    assert list(result) == ["p2", "p3"]
    assert "other account" in result["p2"]


def test_find_in_source_ranks_by_shared_words() -> None:
    [best, *_] = _tools().find_in_source("other account on the Holloway platform")
    assert best["paragraph_id"] == "p2" and best["source"] == "meeting_notes.docx"


def test_get_accounts_filters_by_platform_holder_and_type() -> None:
    tools = _tools()
    assert {a["id"] for a in tools.get_accounts(platform="Holloway")} == {"Y-ISA", "Y-GIA"}
    assert {a["id"] for a in tools.get_accounts(holder="Bob")} == {"B-ISA"}
    assert {a["id"] for a in tools.get_accounts(account_type="ISA")} == {"Y-ISA", "B-ISA"}


def test_get_ledger_entry_returns_the_entry_or_a_clear_miss() -> None:
    tools = _tools()
    assert tools.get_ledger_entry("fact.a") == {"value": "1"}
    assert "error" in tools.get_ledger_entry("fact.missing")


def test_the_dispatcher_refuses_anything_that_is_not_a_read_tool() -> None:
    tools = _tools()
    for name in ("set_value", "write_ledger", "select_value", "__init__", "call"):
        assert "error" in tools.call(name, {}), name


def test_bad_arguments_are_an_error_not_a_crash() -> None:
    assert "error" in _tools().call("read_paragraphs", {"nonsense": 1})
    assert "error" in _tools().call(
        "read_paragraphs", {"source": "nope", "start": "p1", "end": "p2"}
    )


def test_calling_every_tool_leaves_the_inputs_unchanged() -> None:
    tools = _tools()
    before = copy.deepcopy(
        (tools._sources, tools._accounts, tools._entries)  # noqa: SLF001  # checking immutability
    )
    tools.call("list_sources", {})
    tools.call("read_paragraphs", {"source": "meeting_notes.docx", "start": "p1", "end": "p3"})
    tools.call("find_in_source", {"text": "account"})
    tools.call("get_accounts", {"platform": "Holloway"})
    tools.call("get_ledger_entry", {"entry_id": "fact.a"})
    after = (tools._sources, tools._accounts, tools._entries)  # noqa: SLF001
    assert after == before
