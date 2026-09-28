"""R1, R9: account existence and ownership.

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

R9 (T19, client 02's joint GIA): an account_id appearing in more than one holder's own
`accounts` list is deduplicated to one `Account`, first-write-wins (holder iteration
order). Where a copy's `owner` field literally reads "Joint", the owners are every holder
whose own records contain that same account_id (SCOPING.md section 3.1 rule 1) -- not the
literal string "Joint", which the field naively fell through to before this. Two copies
disagreeing on value or date is always a review-sheet conflict (SCOPING R9); resolving
*which* value wins is R3's job (`reconcile/values.py`) against whichever copy first-write-
wins keeps -- a same-date value clash narrowing that to a value-cell marker instead needs a
real client with that exact shape to test against (none yet has it), so it stays a flagged
conflict, never a silent pick, until then.
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
    conflicts: list[ReviewItemInput] = field(default_factory=list)


def _missing_field(record: AccountRecord) -> str | None:
    if record.account_id is None:
        return "account_id"
    if record.type is None:
        return "type"
    if record.status is not None and record.status not in _VALID_STATUSES:
        return "status"
    return None


def _joint_owners(account_id: str, data: AccountData) -> list[str]:
    """R9: every holder whose own `accounts` list contains this account_id, in holder
    iteration order, deduplicated."""
    owners: list[str] = []
    for holder in data.holders.values():
        if holder.name in owners:
            continue
        if any(r.account_id == account_id for r in holder.accounts):
            owners.append(holder.name)
    return owners


def _copies_conflict(account_id: str, copies: list[AccountRecord]) -> ReviewItemInput | None:
    """R9: two copies of the same account_id disagreeing on value or date is a review-sheet
    conflict, whatever the `owner` field says -- flagged, never silently resolved here."""
    if len(copies) <= 1:
        return None
    values = {c.value for c in copies}
    dates = {c.valuation_date for c in copies}
    if len(values) <= 1 and len(dates) <= 1:
        return None
    return ReviewItemInput(
        kind="joint_value_conflict",
        blocking=False,
        detail=(
            f"account {account_id}: joint copies disagree "
            f"(values {sorted(str(v) for v in values)}, dates {sorted(str(d) for d in dates)})"
        ),
        refs=[account_id],
    )


def resolve_ownership(data: AccountData) -> OwnershipResult:
    accounts: dict[str, Account] = {}
    set_aside: list[ReviewItemInput] = []
    conflicts: list[ReviewItemInput] = []
    checked_for_conflict: set[str] = set()
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
            if record.account_id not in checked_for_conflict:
                checked_for_conflict.add(record.account_id)
                copies = [
                    r
                    for h in data.holders.values()
                    for r in h.accounts
                    if r.account_id == record.account_id
                ]
                conflict = _copies_conflict(record.account_id, copies)
                if conflict is not None:
                    conflicts.append(conflict)
            if record.account_id in accounts:
                continue
            if record.owner == "Joint":
                owners = _joint_owners(record.account_id, data)
            else:
                owners = [record.owner or holder.name]
            status: Literal["open", "closed"] = (
                "open" if record.status is None else cast(Literal["open", "closed"], record.status)
            )
            accounts[record.account_id] = Account(
                id=record.account_id,
                owners=owners,
                type=record.type,
                platform=record.platform,
                status=status,
                in_scope=False,
            )
    return OwnershipResult(
        accounts=list(accounts.values()), set_aside=set_aside, conflicts=conflicts
    )
