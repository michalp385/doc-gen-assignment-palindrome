"""T20/T21: `_apply_money` wires P5's `build_money_items` and `available_now` together for the
stage graph -- the ledger's money items, the available-now value, the marker when a
commitment has no stated amount, and the review rows -- and `build_facts` carries them into
the facts the writer draws on (`money.available`, `money.<id>.amount`)."""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.extract.schemas import MoneyItem as ExtractedMoneyItem
from agent_pipeline.pipeline import _apply_money
from agent_pipeline.reconcile.facts import build_facts


def _extracted(
    money_class: str | None, purpose: str, amount_text: str | None
) -> ExtractedMoneyItem:
    return ExtractedMoneyItem.model_validate(
        {
            "money_class": money_class,
            "purpose": purpose,
            "amount": {"paragraph_id": "p1", "text": amount_text} if amount_text else None,
            "class_evidence": {"paragraph_id": "p1", "text": "evidence"},
        }
    )


def _client_04_money() -> list[ExtractedMoneyItem]:
    return [
        _extracted("received", "completion payment", "£850,000"),
        _extracted("committed", "bridging loan", "£200,000"),
        _extracted("external", "earnout", "up to £400,000"),
    ]


def test_no_money_items_means_nothing_at_all() -> None:
    items, available, markers, review = _apply_money([], "meeting_notes.docx", 1)
    assert (items, available, markers, review) == ([], None, [], [])


def test_client_04_money_gives_the_650000_available_and_no_marker() -> None:
    items, available, markers, review = _apply_money(_client_04_money(), "meeting_notes.docx", 1)
    assert [m.money_class for m in items] == ["received", "committed", "external"]
    assert available is not None
    assert available.amount == Decimal("650000")
    assert markers == []
    assert review == []


def test_ids_continue_after_the_disposal_proceeds_items() -> None:
    items, _, _, _ = _apply_money(_client_04_money(), "meeting_notes.docx", 2)
    assert [m.id for m in items] == ["m2", "m3", "m4"]


def test_a_commitment_without_an_amount_makes_available_a_marker_and_a_review_row() -> None:
    items, available, markers, review = _apply_money(
        [
            _extracted("received", "completion payment", "£850,000"),
            _extracted("committed", "loan repayment", None),
        ],
        "meeting_notes.docx",
        1,
    )
    assert available is None
    (marker,) = markers
    assert marker.key == "available_to_invest"
    assert not any(ch.isdigit() for ch in marker.text)
    assert [r.kind for r in review] == ["ambiguity"]
    assert "commitment" in review[0].detail


def test_an_unverified_class_item_is_a_review_row_and_never_counted() -> None:
    items, available, markers, review = _apply_money(
        [_extracted("received", "payment", "£10,000"), _extracted(None, "another", "£5,000")],
        "meeting_notes.docx",
        1,
    )
    assert [m.money_class for m in items] == ["received"]
    assert available is not None and available.amount == Decimal("10000")
    assert markers == []
    assert [r.kind for r in review] == ["unverified"]


def test_facts_carry_the_available_amount_and_each_amount_bearing_item() -> None:
    items, available, _, _ = _apply_money(_client_04_money(), "meeting_notes.docx", 1)
    facts = build_facts([], {}, money_items=items, available=available)
    assert set(facts) == {
        "money.available",
        "money.m1.amount",
        "money.m2.amount",
        "money.m3.amount",
    }
    assert facts["money.available"].role == "available to invest"
    assert facts["money.m3.amount"].role == "excluded"


def test_build_facts_without_money_is_unchanged() -> None:
    assert build_facts([], {}) == {}
