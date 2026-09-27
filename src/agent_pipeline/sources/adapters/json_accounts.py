"""Read the account data JSON into typed records (T7).

Tolerant by design: an unrecognised field is ignored (a genuinely new field an unseen
client's system might add), and every field but the file's own holders/accounts structure
is optional, since a real snapshot doesn't always have every field populated at capture
time (client_03's and client_04's null-valued cash accounts; client_18's account missing a
platform). A per-account field that doesn't parse (e.g. a placeholder string like "N/A" in
a numeric or date field) degrades to that field being unset rather than failing the whole
file -- it is then reconciliation's job (T8) to treat a missing value/date as it would a
genuinely absent one. Only a file with no safe basis at all -- not JSON, or no holders --
stops the run (DESIGN.md section 8.4).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


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

    @field_validator("value", mode="before")
    @classmethod
    def _tolerant_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (int, float, Decimal)):
            return value
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None  # unparseable placeholder (e.g. "N/A"): treat as absent, not fatal

    @field_validator("valuation_date", mode="before")
    @classmethod
    def _tolerant_valuation_date(cls, value: Any) -> Any:
        if value is None or isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None  # unparseable placeholder (e.g. "unknown"): treat as absent, not fatal


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
