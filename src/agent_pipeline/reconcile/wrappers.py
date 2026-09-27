"""Account-type wording -> wrapper class (DESIGN.md section 5.1).

G5, P4 and the scope checks need to know what KIND of account something is from free-text
type wording. The mapping lives in config/account_types.json: general vocabulary, not
client data. A type this doesn't recognise classifies as "unknown" -- never guessed, always
flagged -- rather than assumed to be one thing or another.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path("config/account_types.json")


@dataclass(frozen=True)
class WrapperInfo:
    wrapper_class: str  # "tax_exempt" | "taxable" | "cash" | "bond" | "unknown"
    allowance_family: str | None = None  # "isa" | "pension" | None


def _load_wrappers() -> dict[str, WrapperInfo]:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        type_text: WrapperInfo(
            wrapper_class=entry["class"], allowance_family=entry.get("allowance_family")
        )
        for type_text, entry in raw["wrappers"].items()
    }


_WRAPPERS = _load_wrappers()
_UNKNOWN = WrapperInfo(wrapper_class="unknown", allowance_family=None)


def classify_wrapper(type_text: str) -> WrapperInfo:
    return _WRAPPERS.get(type_text, _UNKNOWN)
