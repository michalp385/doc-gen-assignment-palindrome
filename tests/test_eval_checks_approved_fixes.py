"""Two eval-harness fixes the user approved after the hand-written run (tests first).

1. G6: a value cell that is a bracketed adviser marker is read as "marker", which is how the
   pipeline's own truth (`LedgerTruth`) names a marker cell. Without it the eval compared
   "[ADVISER TO CONFIRM #1: ...]" with "marker" and failed a correct table.
2. G15: an expected review item's `must_mention` terms match case-insensitively, since the ledger
   uses an account type's own capitalisation ("Cash Account") and an expected file does not have
   to guess it. Every term must still appear, and kind and blocking are still exact.
"""

from __future__ import annotations

from agent_pipeline.gates.deterministic import TABLE_HEADER, GateResult, ReportBundle, _check_g15
from agent_pipeline.gates.truth import ReviewSpec
from agent_pipeline.ledger import Ledger, Marker, ReviewItem
from report_eval.run import _parse_table_rows

TABLE = "\n".join(
    [
        TABLE_HEADER,
        "|---|---|---|---|",
        "| X-1 | Ann Poe | Stocks & Shares ISA | £9,500 |",
        "| X-2 | Ann Poe | SIPP | [ADVISER TO CONFIRM #1: current value of Ann Poe's SIPP] |",
        "| X-3 | Ann Poe | Cash Account | c. £1,200 |",
    ]
)


def test_a_bracketed_marker_cell_is_read_as_marker() -> None:
    rows = _parse_table_rows(TABLE, [])
    assert [r.value_text for r in rows] == ["£9,500", "marker", "c. £1,200"]


def _g15(
    detail: str, terms: list[str], *, blocking: bool = True, kind: str = "conflict"
) -> GateResult:
    marker = Marker(id="#1", key="k", text="t", reason="r", section="recommendations")
    ledger = Ledger(
        client="c",
        markers=[marker],
        review=[
            ReviewItem(id="r1", kind="conflict", blocking=True, detail=detail, refs=[]),
            ReviewItem(id="r2", kind="marker_reference", detail="see marker k", refs=["k"]),
        ],
    )

    class Truth:
        def expected_review_items(self):  # type: ignore[no-untyped-def]
            return [ReviewSpec(key="x", kind=kind, blocking=blocking, must_mention=terms)]

    return _check_g15(ReportBundle(report_text="", ledger=ledger), Truth())  # type: ignore[arg-type]


def test_terms_match_regardless_of_case() -> None:
    detail = "Cash Account (Holloway) is closed but the scope names it."
    assert _g15(detail, ["closed", "cash account", "Holloway"]).passed


def test_every_term_must_still_appear() -> None:
    detail = "Cash Account (Holloway) is closed but the scope names it."
    result = _g15(detail, ["closed", "pension"])
    assert not result.passed and "missing review item" in result.detail


def test_kind_and_blocking_are_still_exact() -> None:
    detail = "Cash Account is closed."
    assert not _g15(detail, ["closed"], blocking=False).passed
    assert not _g15(detail, ["closed"], kind="ambiguity").passed
