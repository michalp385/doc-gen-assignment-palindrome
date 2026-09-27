"""The named predicate registry for section inclusion (D11, DESIGN.md section 7.1).

`use_if` stays plain language (PROJECT_GUIDANCE.md's contract), and a section may add an
optional `predicate` naming a ledger decision registered here. Config loading (T10) fails
on an unknown predicate name, never silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agent_pipeline.ledger import Ledger

if TYPE_CHECKING:
    from agent_pipeline.config import Section

PREDICATES: dict[str, Callable[..., bool]] = {}


def predicate(name: str) -> Callable[[Callable[..., bool]], Callable[..., bool]]:
    def register(fn: Callable[..., bool]) -> Callable[..., bool]:
        PREDICATES[name] = fn
        return fn

    return register


def evaluate(name: str, *args: Any, **kwargs: Any) -> bool:
    if name not in PREDICATES:
        raise KeyError(f"no predicate named {name!r} is registered")
    return PREDICATES[name](*args, **kwargs)


# Ledger-stage resolution (write/plan.py stage 4; assemble.py's "Section decisions"): distinct
# from `evaluate`'s raw-SectionContext predicates above, which reconciliation runs once and
# caches onto a Ledger field (e.g. `taxable_disposal` -> `ledger.tax_section`). A section's
# `predicate` names one of these fields, not a `PREDICATES` entry.
_LEDGER_PREDICATES: dict[str, Callable[[Ledger], bool]] = {
    "taxable_disposal": lambda ledger: ledger.tax_section,
}


def section_included(section: Section, ledger: Ledger) -> bool:
    """Whether a section applies at the ledger stage. `None` predicate always includes; an
    unregistered predicate name raises `KeyError`, never a silent default."""
    if section.predicate is None:
        return True
    if section.predicate not in _LEDGER_PREDICATES:
        raise KeyError(f"no ledger-level resolution for predicate {section.predicate!r}")
    return _LEDGER_PREDICATES[section.predicate](ledger)
