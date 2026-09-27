"""Source adapters (T7): read each file format into a common, quote-addressable shape.

Reads are tolerant of anything a real or unseen client's files might omit; only a file
with no safe basis at all (unreadable account data) stops the run (DESIGN.md section 8.4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.json_accounts import AccountDataError, read_accounts
from agent_pipeline.sources.adapters.markdown import read_markdown

CLIENT_01 = Path("data/client_01_clean")


def test_read_docx_reads_every_paragraph_of_client_01s_meeting_notes() -> None:
    doc = read_docx(CLIENT_01 / "meeting_notes.docx")
    assert len(doc.paragraphs) == 8
    joined = " ".join(doc.paragraphs.values())
    assert "held 12 May 2026" in joined
    assert "We agreed she would move £20,000" in joined


def test_read_docx_reads_the_instruction_table() -> None:
    doc = read_docx(CLIENT_01 / "report_request.docx")
    assert len(doc.paragraphs) == 1  # "Report Requirement Summary"
    assert len(doc.tables) == 1
    assert len(doc.tables[0]) == 9  # nine label/value rows
    assert doc.tables[0][0] == ["Adviser", "Daniel Reeves"]
    assert doc.tables[0][-1] == ["Initial charge", "0%"]


def test_read_docx_paragraph_ids_are_stable_and_addressable() -> None:
    doc = read_docx(CLIENT_01 / "meeting_notes.docx")
    first_id = next(iter(doc.paragraphs))
    assert doc.paragraph_text(first_id) == doc.paragraphs[first_id]
    assert doc.paragraph_text("no-such-id") is None


def test_read_accounts_reads_client_01() -> None:
    data = read_accounts(CLIENT_01 / "client_data_db.json")
    assert data.snapshot_date is not None
    assert "client" in data.holders
    accounts = data.holders["client"].accounts
    assert {a.account_id for a in accounts} == {"H-ISA-01", "H-CASH-01"}


def test_read_accounts_tolerates_a_missing_optional_field(tmp_path: Path) -> None:
    payload = {
        "snapshot_date": "2026-05-01",
        "holders": {
            "client": {
                "name": "Mildred Sowerby",
                "accounts": [
                    {
                        "account_id": "S-ISA-01",
                        # "platform" deliberately omitted, like case_18
                        "type": "Stocks & Shares ISA",
                        "owner": "Mildred Sowerby",
                        "status": "open",
                        "value": 29000.0,
                        "currency": "GBP",
                        "valuation_date": "2026-05-01",
                    }
                ],
            }
        },
    }
    path = tmp_path / "client_data_db.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    data = read_accounts(path)

    account = data.holders["client"].accounts[0]
    assert account.platform is None
    assert account.account_id == "S-ISA-01"


def test_read_accounts_ignores_unknown_fields(tmp_path: Path) -> None:
    payload = {
        "snapshot_date": "2026-05-01",
        "future_field_nobody_expects": "some value",
        "holders": {
            "client": {
                "name": "Test Person",
                "accounts": [
                    {
                        "account_id": "T-ISA-01",
                        "type": "Stocks & Shares ISA",
                        "owner": "Test Person",
                        "status": "open",
                        "value": 1000.0,
                        "currency": "GBP",
                        "valuation_date": "2026-05-01",
                        "another_unknown_field": 42,
                    }
                ],
            }
        },
    }
    path = tmp_path / "client_data_db.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    data = read_accounts(path)  # must not raise

    assert data.holders["client"].accounts[0].account_id == "T-ISA-01"


def test_read_accounts_raises_on_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "client_data_db.json"
    path.write_text("{ not valid json at all", encoding="utf-8")
    with pytest.raises(AccountDataError):
        read_accounts(path)


def test_read_accounts_raises_when_there_are_no_holders(tmp_path: Path) -> None:
    path = tmp_path / "client_data_db.json"
    path.write_text(json.dumps({"snapshot_date": "2026-05-01", "holders": {}}), encoding="utf-8")
    with pytest.raises(AccountDataError):
        read_accounts(path)


def test_read_markdown_splits_into_paragraphs() -> None:
    doc = read_markdown(CLIENT_01 / "fde_notes.md")
    assert len(doc.paragraphs) > 1
    joined = " ".join(doc.paragraphs.values())
    assert "The capital gains tax on any disposal" in joined
