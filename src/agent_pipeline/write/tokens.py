"""Token substitution (DESIGN.md section 7.2, D1): fills `{fact:<id>}` with
`render_prose(fact.value)` and `{marker:<key>}` with the marker's P1-format bracket text.
The writer never sees a number; code fills every figure from the ledger.
"""

from __future__ import annotations

import re

from agent_pipeline.ledger import Ledger, render_prose

TOKEN_RE = re.compile(r"\{(fact|marker):([^{}]+)\}")


class TokenError(Exception):
    """A token names an id/key that isn't in the ledger -- should already be caught by the
    writer's pre-substitution check; this is the defensive fallback, never a silent blank."""


def fill_tokens(text: str, ledger: Ledger) -> str:
    marker_by_key = {marker.key: marker for marker in ledger.markers}

    def _sub(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        if kind == "fact":
            fact = ledger.facts.get(name)
            if fact is None or fact.value is None:
                raise TokenError(f"fact {name!r} has no value to render")
            return render_prose(fact.value)
        marker = marker_by_key.get(name)
        if marker is None:
            raise TokenError(f"marker {name!r} not found")
        return f"[ADVISER TO CONFIRM {marker.id}: {marker.text}]"

    return TOKEN_RE.sub(_sub, text)
