"""The eval's table parser maps a new account's "To be opened" label back to its ledger id
(tests first). The client-facing table no longer prints a synthetic `new:` id, but G1 still
checks one row per in-scope account: the label is matched to the ledger's new accounts in
order, and a label beyond their number stays unmatched so G1 reports it as unexpected.
"""

from __future__ import annotations

from agent_pipeline.gates.deterministic import TABLE_HEADER
from report_eval.run import _parse_table_rows

TABLE = "\n".join(
    [
        TABLE_HEADER,
        "|---|---|---|---|",
        "| X-1 | Ann Poe | Stocks & Shares ISA | £9,500 |",
        "| To be opened | Ann Poe & Bob Poe | New joint account | To be opened |",
        "| To be opened | Bob Poe | New account | To be opened |",
    ]
)


def test_labels_map_to_new_account_ids_in_order() -> None:
    rows = _parse_table_rows(TABLE, ["new:a", "new:b"])
    assert [r.account_id for r in rows] == ["X-1", "new:a", "new:b"]


def test_a_label_with_no_matching_new_account_stays_unmatched() -> None:
    rows = _parse_table_rows(TABLE, ["new:a"])
    assert [r.account_id for r in rows] == ["X-1", "new:a", "To be opened"]


def test_no_new_accounts_leaves_rows_as_printed() -> None:
    rows = _parse_table_rows(TABLE, [])
    assert [r.account_id for r in rows] == ["X-1", "To be opened", "To be opened"]
