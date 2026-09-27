"""Read the account data JSON into typed records (T7).

Tolerant by design: an unrecognised field is ignored (a genuinely new field an unseen
client's system might add), and every field but the file's own holders/accounts structure
is optional, since a real snapshot doesn't always have every field populated at capture
time (client_03's and client_04's null-valued cash accounts; client_18's account missing a
platform). Only a file with no safe basis at all -- not JSON, or no holders -- stops the run
(DESIGN.md section 8.4); everything else is reconciliation's job (T8), not this adapter's.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class AccountDataError(Exception):
    """No safe basis for which accounts exist or who owns them (DESIGN.md section 8.4)."""


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AccountRecord(_Tolerant):
    account_id: str | None = None
    platform: str | None = None
    type: str | None = None
    owner: str | None = None
    status: str | None = None
    value: Decimal | None = None
    currency: str | None = None
    valuation_date: date | None = None


class Holder(_Tolerant):
    name: str
    accounts: list[AccountRecord] = Field(default_factory=list)


class AccountData(_Tolerant):
    snapshot_date: date | None = None
    holders: dict[str, Holder] = Field(default_factory=dict)


def read_accounts(path: Path) -> AccountData:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AccountDataError(f"{path} is not readable JSON: {exc}") from exc

    try:
        data = AccountData.model_validate(raw)
    except ValidationError as exc:
        raise AccountDataError(f"{path} doesn't match the account data shape: {exc}") from exc

    if not data.holders:
        raise AccountDataError(f"{path} has no holders: no basis for which accounts exist")

    return data
