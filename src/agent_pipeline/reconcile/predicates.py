"""The named predicate registry for section inclusion (D11, DESIGN.md section 7.1).

`use_if` stays plain language (PROJECT_GUIDANCE.md's contract), and a section may add an
optional `predicate` naming a ledger decision registered here. Config loading (T10) fails
on an unknown predicate name, never silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
