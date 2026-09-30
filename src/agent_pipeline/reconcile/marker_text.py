"""Words for marker descriptions, built in code from the ledger so a marker names what it
concerns (the account and platform, the holders) and never a figure. Marker keys are unchanged:
G14 matches on key, and there is one marker per key."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from agent_pipeline.ledger import Account

PLATFORM_NOT_STATED = "platform not stated"


def join_natural(items: Sequence[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _first_names(owners: Sequence[str]) -> list[str]:
    """First names, or full names when two distinct holders would share one."""
    holders = _unique(owners)
    firsts = [o.split()[0] for o in holders]
    return holders if len(set(firsts)) < len(firsts) else firsts


def holders_phrase(owners: Sequence[str]) -> str:
    """ "Ann and Ben"."""
    return join_natural(_first_names(owners))


def each_holder_phrase(owners: Sequence[str]) -> str:
    """ "for Ann" for one holder, "for Ann and for Ben, each" for several."""
    names = _first_names(owners)
    if len(names) <= 1:
        return f"for {names[0]}" if names else ""
    return f"{join_natural([f'for {n}' for n in names])}, each"


def account_phrase(account: Account) -> str:
    """ "the joint <type>, <platform>" or "Ann's <type>, <platform>"; a missing
    platform is said, not left out, because the adviser needs to know it is missing."""
    where = account.platform or PLATFORM_NOT_STATED
    if len(account.owners) > 1:
        return f"the joint {account.type}, {where}"
    if account.owners:
        return f"{account.owners[0].split()[0]}'s {account.type}, {where}"
    return f"{account.type}, {where}"


def accounts_phrase(accounts: Iterable[Account]) -> str:
    """Each distinct account once, in order, separated by "; " (a phrase has commas inside)."""
    seen: dict[tuple[tuple[str, ...], str, str | None], Account] = {}
    for account in accounts:
        seen.setdefault((tuple(account.owners), account.type, account.platform), account)
    return "; ".join(account_phrase(a) for a in seen.values())
