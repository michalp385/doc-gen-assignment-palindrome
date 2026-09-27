"""R1: account existence and ownership.

The account data wins on which accounts exist and who holds them; owners come from the
`owner` field, never inferred from how an account id happens to be spelled. Joint-account
merging when `owner` reads "Joint" (R9) arrives in M2 with client 02's first joint account
and its own test; client 01 has none.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.sources.adapters.json_accounts import AccountData


def resolve_ownership(data: AccountData) -> list[Account]:
    accounts: dict[str, Account] = {}
    for holder in data.holders.values():
        for record in holder.accounts:
            if record.account_id is None or record.account_id in accounts:
                continue  # missing an identifying field; reconciliation flags this elsewhere
            owner = record.owner or holder.name
            accounts[record.account_id] = Account(
                id=record.account_id,
                owners=[owner],
                type=record.type or "",
                platform=record.platform,
                status=record.status or "open",  # type: ignore[arg-type]
                in_scope=False,
            )
    return list(accounts.values())
