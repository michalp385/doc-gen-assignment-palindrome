"""Type matching in `intro_scope_problems` and the file-name pattern (verifier checkpoint on the
code-first judge change), tests first.

Account types are matched as whole words with an optional plural, longest in-scope type first,
so a type that is a substring of another (or of an ordinary word) is neither missed nor
falsely flagged. The file-name pattern covers more extensions.
"""

from __future__ import annotations

import dataclasses

import pytest

from agent_pipeline.gates.deterministic import run_gates
from agent_pipeline.gates.judge import intro_scope_problems
from agent_pipeline.ledger import Account, Ledger
from report_eval.reference import build_reference_bundle


def _ledger(**types: bool) -> Ledger:
    """type wording -> in scope?"""
    return Ledger(
        client="c",
        accounts=[
            Account(id=f"A{i}", owners=["A Client"], type=t, in_scope=in_scope)
            for i, (t, in_scope) in enumerate(types.items())
        ],
    )


def test_a_plural_type_counts_as_naming_it() -> None:
    ledger = _ledger(**{"Stocks & Shares ISA": True, "General Investment Account": True})
    assert (
        intro_scope_problems("Your Stocks & Shares ISAs and General Investment Accounts.", ledger)
        == []
    )


def test_a_plural_alias_counts_as_naming_it() -> None:
    ledger = _ledger(**{"Stocks & Shares ISA": True, "General Investment Account": True})
    assert intro_scope_problems("Your Stocks & Shares ISA and your GIAs.", ledger) == []


def test_an_out_of_scope_type_is_flagged_even_in_the_plural() -> None:
    ledger = _ledger(**{"Stocks & Shares ISA": True, "Cash Account": False})
    problems = intro_scope_problems("Your Stocks & Shares ISA and your cash accounts.", ledger)
    assert any("Cash Account" in p for p in problems)


def test_a_type_inside_an_ordinary_word_is_not_a_mention() -> None:
    # "ISA" occurs inside "visa" and "Cash" inside "cashmere": neither names an account
    ledger = _ledger(**{"Stocks & Shares ISA": True, "ISA": False})
    assert intro_scope_problems("Your Stocks & Shares ISA, for a visa holiday.", ledger) == []


def test_an_out_of_scope_type_inside_a_longer_in_scope_type_is_not_a_false_fail() -> None:
    ledger = _ledger(**{"Cash ISA": True, "ISA": False})
    assert intro_scope_problems("Our advice covers your Cash ISA.", ledger) == []


def test_the_longer_in_scope_type_does_not_hide_a_real_mention_of_the_shorter_one() -> None:
    ledger = _ledger(**{"Cash ISA": True, "ISA": False})
    problems = intro_scope_problems("Our advice covers your Cash ISA and your ISA.", ledger)
    assert any("out of scope" in p for p in problems)


# --- internal file names -------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["notes.txt", "page.html", "config.yaml", "config.yml", "data.xml", "old.doc", "x.pptx"]
)
def test_more_extensions_are_recognised_as_internal_file_names(name: str) -> None:
    bundle, truth = build_reference_bundle("client_01_clean")
    mutated = dataclasses.replace(bundle, report_text=bundle.report_text + f" See {name} here.")
    assert not {r.gate: r for r in run_gates(mutated, truth)}["G10"].passed
