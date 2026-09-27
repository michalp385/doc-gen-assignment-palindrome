"""The account table (P9, DESIGN.md section 3.4/7.1): built from the ledger in code, never
by the model. Columns Account | Owner | Type | Value, one row per in-scope account;
`render_table` for a value (always "c." for approximate), "To be opened" for a new account,
a marker's bracket text where the value itself is unknown. A superseded value appears only
in the footnote, never the table cell (G2/G6).
"""

from __future__ import annotations

from agent_pipeline.gates.deterministic import TABLE_HEADER
from agent_pipeline.ledger import Account, Ledger, Marker, render_prose, render_table


def _value_cell(account: Account, marker_by_key: dict[str, Marker]) -> str:
    if account.is_new:
        return "To be opened"
    if account.value_marker is not None:
        marker = marker_by_key.get(account.value_marker)
        if marker is not None:
            return f"[ADVISER TO CONFIRM {marker.id}: {marker.text}]"
        return "marker"
    if account.value is not None:
        return render_table(account.value)
    return "marker"


def build_table(ledger: Ledger) -> str:
    marker_by_key = {marker.key: marker for marker in ledger.markers}
    rows = [account for account in ledger.accounts if account.in_scope]

    lines = [TABLE_HEADER, "|---|---|---|---|"]
    footnotes: list[str] = []
    for account in rows:
        owner = " & ".join(account.owners)
        value_cell = _value_cell(account, marker_by_key)
        lines.append(f"| {account.id} | {owner} | {account.type} | {value_cell} |")
        for superseded in account.superseded:
            footnotes.append(
                f"{account.id}: {superseded.source_id}, {superseded.date}: "
                f'"{superseded.quote}". {render_prose(superseded)}.'
            )

    table = "\n".join(lines)
    if footnotes:
        table += "\n\n" + "\n".join(footnotes)
    return table
