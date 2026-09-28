"""The account table (P9, DESIGN.md section 3.4/7.1): built from the ledger in code, never
by the model. Columns Account | Owner | Type | Value, one row per in-scope account;
`render_table` for a value (always "c." for approximate), "To be opened" for a new account,
a marker's bracket text where the value itself is unknown. A superseded value appears only
in the footnote, never the table cell (G2/G6).
"""

from __future__ import annotations

from agent_pipeline.gates.deterministic import TABLE_HEADER
from agent_pipeline.ledger import Account, Ledger, Marker, render_date, render_prose, render_table


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


def _account_label(account: Account) -> str:
    """A footnote reads as one grammatical, client-facing sentence, never a raw account_id
    or a "label: value" caption (T19, two live-judge checkpoints: G10 flagged an "<id>:
    <filename>, <date>:" footnote as internal source material; G12 then flagged the
    colon-led caption format itself as an ungrammatical fragment once the filename was
    fixed). A single owner gets their first name; a jointly-held account reads "Your joint
    <type>", never the bare id -- both stand as the subject of a full sentence."""
    if len(account.owners) == 1:
        return f"{account.owners[0].split()[0]}'s {account.type}"
    return f"Your joint {account.type}"


def _source_label(source_id: str) -> str:
    """TODO(T20): a live release-judge run on client 02 flagged this footnote's raw
    filename ("...shown in client_data_db.json...") as reading like internal system
    information rather than client-facing text (G10, a hard gate) -- verified by generating
    a real report and running `report_eval.run --judge` against it. Humanising by file
    *format* (general vocabulary: "our records" for .json, "our meeting note" for .docx,
    "your statement" for an image -- never a per-client filename) fixed it, confirmed the
    same way. That fix is reverted here only because `tests/test_write_tokens_table.py`'s
    committed `test_build_table_footnotes_a_superseded_value_never_the_cell` still asserts
    the raw filename appears verbatim, and this repo's own guard requires the user to
    approve changing a committed test, which wasn't obtained this session. Whoever picks
    this up next: update that one assertion (it should check for the humanised label, e.g.
    "our records", not the filename), then restore the mapping below -- both the fix and
    the corrected test assertion are already written up in the session's own handover."""
    return source_id


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
            # T19: a db-sourced candidate (`reconcile/values.py::select_values`) has no
            # natural quote -- it's a structured field, not a paragraph -- so quoting an
            # empty string ('""') was a real, if minor, defect no client before client 02
            # exposed (its GIA is the first superseded value ever sourced from the db
            # rather than the meeting record).
            quoted = f' ("{superseded.quote}")' if superseded.quote else ""
            when = f" ({render_date(superseded.date)})" if superseded.date else ""
            source = _source_label(superseded.source_id)
            footnotes.append(
                f"{_account_label(account)} was previously shown in {source}"
                f"{when} as {render_prose(superseded)}{quoted}."
            )

    table = "\n".join(lines)
    if footnotes:
        table += "\n\n" + "\n".join(footnotes)
    return table
