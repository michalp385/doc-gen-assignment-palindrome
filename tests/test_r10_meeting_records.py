"""R10: several meeting records (tests first; hand-written case 14).

SCOPING rule 10: the latest-dated record governs decisions; earlier ones contribute dated values
only, under rule 3. An undated record is the earliest of all (it never outranks a dated one), and
records sharing the latest date fall back to input order. A single record is unchanged, and no
review item is raised for it.
"""

from __future__ import annotations

from datetime import date

from agent_pipeline.reconcile.meetings import govern_meeting_records, several_records_review_item


def test_a_single_record_governs_and_nothing_is_earlier() -> None:
    assert govern_meeting_records([date(2026, 4, 1)]) == (0, [])
    assert govern_meeting_records([None]) == (0, [])


def test_the_latest_dated_record_governs() -> None:
    assert govern_meeting_records([date(2026, 4, 1), date(2026, 5, 20)]) == (1, [0])
    assert govern_meeting_records([date(2026, 5, 20), date(2026, 4, 1)]) == (0, [1])


def test_an_undated_record_never_outranks_a_dated_one() -> None:
    assert govern_meeting_records([None, date(2026, 4, 1)]) == (1, [0])
    assert govern_meeting_records([date(2026, 4, 1), None]) == (0, [1])


def test_earlier_records_are_listed_oldest_first() -> None:
    dates = [date(2026, 3, 1), date(2026, 5, 1), date(2026, 1, 1)]
    assert govern_meeting_records(dates) == (1, [2, 0])


def test_the_same_latest_date_falls_back_to_input_order() -> None:
    same = date(2026, 5, 1)
    assert govern_meeting_records([same, same]) == (1, [0])


def test_the_review_item_names_which_record_governs_and_which_are_earlier() -> None:
    item = several_records_review_item(
        ["meeting_notes.docx", "meeting_notes_followup.docx"],
        [date(2026, 4, 1), date(2026, 5, 20)],
        governing=1,
    )
    assert item is not None and item.kind == "degradation" and not item.blocking
    assert "meeting_notes_followup.docx" in item.detail and "20 May 2026" in item.detail
    assert "meeting_notes.docx" in item.detail and "1 April 2026" in item.detail
    assert "governs" in item.detail


def test_a_single_record_has_no_review_item() -> None:
    assert several_records_review_item(["m.docx"], [date(2026, 4, 1)], governing=0) is None
