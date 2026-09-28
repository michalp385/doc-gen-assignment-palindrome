"""The table footnote never names an internal file (P9), tests first.

A superseded value's footnote says where it came from in client terms -- "our records", "our
meeting note", "your statement" -- never a filename such as `client_data_db.json`, which the
release judge rightly flags as internal system information (G10). The wording is chosen by the
source's file format, general vocabulary rather than a per-client filename.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from agent_pipeline.ledger import Account, Ledger, Value
from agent_pipeline.write.table import build_table

FILE_NAME_RE = re.compile(r"\b[\w-]+\.(?:json|docx|md|png|jpe?g|pdf)\b", re.IGNORECASE)


def _ledger(source_id: str) -> Ledger:
    def value(amount: str, source: str, day: date) -> Value:
        return Value(
            amount=Decimal(amount),
            currency="GBP",
            precision="exact",
            qualifier="exact",
            date=day,
            source_id=source,
            quote="",
            selected_by="R3",
        )

    account = Account(
        id="X-GIA",
        owners=["A Client", "B Client"],
        type="General Investment Account",
        platform="Holloway",
        in_scope=True,
        value=value("45000", "meeting_notes.docx", date(2026, 5, 14)),
        superseded=[value("40000", source_id, date(2026, 3, 15))],
    )
    return Ledger(client="c", accounts=[account])


@pytest.mark.parametrize(
    ("source_id", "wording"),
    [
        ("client_data_db.json", "our records"),
        ("meeting_notes.docx", "our meeting note"),
        ("statement_summary.png", "your statement"),
        ("anything_else.pdf", "our records"),
    ],
)
def test_the_footnote_names_the_source_in_client_terms(source_id: str, wording: str) -> None:
    footnote = build_table(_ledger(source_id)).split("\n\n", 1)[1]
    assert wording in footnote
    assert source_id not in footnote
    assert FILE_NAME_RE.search(footnote) is None


def test_the_footnote_still_carries_the_superseded_figure_and_date() -> None:
    footnote = build_table(_ledger("client_data_db.json")).split("\n\n", 1)[1]
    assert "£40,000" in footnote
    assert "15 March" in footnote
