"""R1: account existence and ownership.

The account data wins on which accounts exist and who holds them; owners come from the
`owner` field (falling back to the holder whose JSON section contains the record, per
SCOPING.md section 3, table row "Account data"), never inferred from how an account id
happens to be spelled. An account missing one of its identifying fields -- `account_id`,
`type` or `status` -- has no safe basis to include in the table, so it is set aside as a
review item instead (DESIGN.md section 8.4/134), never given a guessed value (an invalid
`status` used to be passed straight to a `Literal["open", "closed"]` field, silenced with
an unexplained `# type: ignore`, and crashed on anything else -- verifier report, T8
checkpoint, finding #2). Escalating a set-aside item to a blocking conflict when the
account turns out to be in scope needs `resolve_scope`'s result, which doesn't exist yet at
this stage; that escalation is T10 pipeline-assembly work (verifier report, finding #2).
Joint-account merging when `owner` reads "Joint" (R9) arrives in M2 with client 02's first
joint account and its own test; client 01 has none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, cast

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.review import ReviewItemInput
from agent_pipeline.sources.adapters.json_accounts import AccountData, AccountRecord

_VALID_STATUSES = {"open", "closed"}


@dataclass(frozen=True)
class OwnershipResult:
    accounts: list[Account] = field(default_factory=list)
    set_aside: list[ReviewItemInput] = field(default_factory=list)


def _missing_field(record: AccountRecord) -> str | None:
    if record.account_id is None:
        return "account_id"
    if record.type is None:
        return "type"
    if record.status is not None and record.status not in _VALID_STATUSES:
        return "status"
    return None


def resolve_ownership(data: AccountData) -> OwnershipResult:
    accounts: dict[str, Account] = {}
    set_aside: list[ReviewItemInput] = []
    for holder in data.holders.values():
        for record in holder.accounts:
            missing = _missing_field(record)
            if missing is not None:
                ref = record.account_id or "(no account_id)"
                set_aside.append(
                    ReviewItemInput(
                        kind="account_missing_field",
                        blocking=False,
                        detail=f"account {ref}: missing or unrecognised {missing}",
                        refs=[ref],
                    )
                )
                continue
            # _missing_field already confirmed account_id, type and status are all usable.
            assert record.account_id is not None
            assert record.type is not None
            if record.account_id in accounts:
                continue
            owner = record.owner or holder.name
            status: Literal["open", "closed"] = (
                "open" if record.status is None else cast(Literal["open", "closed"], record.status)
            )
            accounts[record.account_id] = Account(
                id=record.account_id,
                owners=[owner],
                type=record.type,
                platform=record.platform,
                status=status,
                in_scope=False,
            )
    return OwnershipResult(accounts=list(accounts.values()), set_aside=set_aside)
