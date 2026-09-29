"""A slot may start with a capital when its first word is a name (tests first; case 03).

The writer's boundary check refuses a slot that starts capitalised where the template continues
a lowercase sentence, so "in relation to The accounts ..." is caught. But "in relation to
<first name>'s ISA ..." is correct English: a client's first name or a platform the ledger knows
is a proper noun, and the check must not fail a correct sentence. Anything else that starts
capitalised is still refused.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.config import load_report_config
from agent_pipeline.write.writer import _check_g12_pre

SECTION = next(
    s
    for s in load_report_config(Path("config/template_config.json")).sections
    if s.id == "introduction"
)
NAMES = frozenset({"ian", "priya", "holloway"})


def _check(text: str, names: frozenset[str] = NAMES) -> str | None:
    return _check_g12_pre(SECTION, "scope", text, names)


def test_a_slot_starting_with_a_clients_first_name_is_fine() -> None:
    assert _check("Ian's Stocks & Shares ISA held with Holloway and your joint account") is None


def test_a_possessive_and_a_plain_name_both_count() -> None:
    assert _check("Priya's ISA") is None
    assert _check("Priya and Ian's accounts") is None


def test_a_platform_name_counts() -> None:
    assert _check("Holloway accounts held by you") is None


def test_any_other_capital_is_still_refused() -> None:
    reason = _check("The accounts comprising your ISA")
    assert reason is not None and "capitalised" in reason


def test_an_unknown_name_is_refused_when_no_names_are_given() -> None:
    assert _check("Ian's ISA", frozenset()) is not None


def test_lowercase_is_always_fine() -> None:
    assert _check("your Stocks & Shares ISA") is None
