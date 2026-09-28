"""Extraction scoring (T17, DESIGN.md section 10.7): standalone fixtures, no LLM and no
client data -- actual and expected items built by hand so precision/recall/label-accuracy
arithmetic is exercised directly."""

from __future__ import annotations

from agent_pipeline.extract.schemas import (
    Disposal,
    LabelEvidence,
    MeetingExtraction,
    MoneyItem,
    OpenAction,
    Quote,
    ValueObservation,
)
from report_eval.expected import Disposal as ExpectedDisposal
from report_eval.expected import Extraction
from report_eval.expected import MoneyItem as ExpectedMoneyItem
from report_eval.expected import OpenAction as ExpectedOpenAction
from report_eval.expected import ValueObservation as ExpectedValueObservation
from report_eval.extraction_score import score_extraction


def _category(score, name: str):
    return next(c for c in score.categories if c.category == name)


def _label(score, name: str):
    return next((label for label in score.labels if label.label == name), None)


def test_perfect_match_scores_full_precision_recall_and_label_accuracy() -> None:
    expected = Extraction(
        value_observations=[
            ExpectedValueObservation(
                account="GIA",
                amount_quote="£61,000",
                basis="viewed_in_meeting",
                evidence_quote="I pulled the account up live",
            )
        ],
        open_actions=[
            ExpectedOpenAction(
                description="confirm charges once issued",
                blocking=False,
                evidence_quote="confirm charges once issued",
            )
        ],
    )
    actual = MeetingExtraction(
        value_observations=[
            ValueObservation(
                account_reference="GIA",
                amount=Quote(paragraph_id="p1", text="£61,000"),
                basis="viewed_in_meeting",
                basis_evidence=LabelEvidence(
                    paragraph_id="p1", text="I pulled the account up live"
                ),
            )
        ],
        open_actions=[
            OpenAction(
                text=Quote(paragraph_id="p2", text="confirm charges once issued"),
                blocking=False,
                blocking_evidence=LabelEvidence(
                    paragraph_id="p2", text="confirm charges once issued"
                ),
            )
        ],
    )

    score = score_extraction(actual, expected)

    vo = _category(score, "value_observations")
    assert (vo.expected_count, vo.actual_count, vo.matched) == (1, 1, 1)
    assert vo.precision == 1.0
    assert vo.recall == 1.0
    basis = _label(score, "basis")
    assert basis is not None
    assert (basis.correct, basis.total, basis.accuracy) == (1, 1, 1.0)

    oa = _category(score, "open_actions")
    assert (oa.expected_count, oa.actual_count, oa.matched) == (1, 1, 1)
    blocking = _label(score, "blocking")
    assert blocking is not None
    assert (blocking.correct, blocking.total, blocking.accuracy) == (1, 1, 1.0)


def test_missed_expected_item_lowers_recall_not_precision() -> None:
    expected = Extraction(
        open_actions=[
            ExpectedOpenAction(
                description="confirm charges once issued",
                blocking=False,
                evidence_quote="confirm charges once issued",
            ),
            ExpectedOpenAction(
                description="chase the missing paperwork",
                blocking=True,
                evidence_quote="chase the missing paperwork",
            ),
        ]
    )
    actual = MeetingExtraction(
        open_actions=[
            OpenAction(
                text=Quote(paragraph_id="p2", text="confirm charges once issued"),
                blocking=False,
                blocking_evidence=LabelEvidence(
                    paragraph_id="p2", text="confirm charges once issued"
                ),
            )
        ]
    )

    score = score_extraction(actual, expected)
    oa = _category(score, "open_actions")
    assert (oa.expected_count, oa.actual_count, oa.matched) == (2, 1, 1)
    assert oa.precision == 1.0
    assert oa.recall == 0.5


def test_extra_actual_item_lowers_precision_not_recall() -> None:
    expected = Extraction(
        open_actions=[
            ExpectedOpenAction(
                description="confirm charges once issued",
                blocking=False,
                evidence_quote="confirm charges once issued",
            )
        ]
    )
    actual = MeetingExtraction(
        open_actions=[
            OpenAction(
                text=Quote(paragraph_id="p2", text="confirm charges once issued"),
                blocking=False,
                blocking_evidence=LabelEvidence(
                    paragraph_id="p2", text="confirm charges once issued"
                ),
            ),
            OpenAction(
                text=Quote(paragraph_id="p9", text="a fabricated action nobody agreed to"),
                blocking=False,
                blocking_evidence=LabelEvidence(
                    paragraph_id="p9", text="a fabricated action nobody agreed to"
                ),
            ),
        ]
    )

    score = score_extraction(actual, expected)
    oa = _category(score, "open_actions")
    assert (oa.expected_count, oa.actual_count, oa.matched) == (1, 2, 1)
    assert oa.precision == 0.5
    assert oa.recall == 1.0


def test_matched_pair_with_wrong_label_counts_against_accuracy_not_recall() -> None:
    expected = Extraction(
        disposals=[
            ExpectedDisposal(account="GIA", extent="full", evidence_quote="sold the whole holding")
        ]
    )
    actual = MeetingExtraction(
        disposals=[
            Disposal(
                account_reference="GIA",
                quote=Quote(paragraph_id="p3", text="sold part of the holding"),
                extent="portion",  # wrong label, but the item still matches on text overlap
                extent_evidence=LabelEvidence(paragraph_id="p3", text="sold the whole holding"),
            )
        ]
    )

    score = score_extraction(actual, expected)
    disposals = _category(score, "disposals")
    assert disposals.matched == 1
    assert disposals.recall == 1.0
    extent = _label(score, "extent")
    assert extent is not None
    assert (extent.correct, extent.total, extent.accuracy) == (0, 1, 0.0)


def test_unrelated_items_do_not_match_across_categories_or_text() -> None:
    expected = Extraction(
        money_items=[
            ExpectedMoneyItem.model_validate(
                {
                    "class": "received",
                    "amount_quote": "£10,000",
                    "evidence_quote": "an inheritance came through last month",
                }
            )
        ]
    )
    actual = MeetingExtraction(
        money_items=[
            MoneyItem(
                money_class="committed",
                purpose="a house deposit",
                amount=Quote(paragraph_id="p4", text="£40,000"),
                class_evidence=LabelEvidence(
                    paragraph_id="p4", text="already committed to the house purchase"
                ),
            )
        ]
    )

    score = score_extraction(actual, expected)
    money = _category(score, "money_items")
    assert money.matched == 0
    assert money.precision == 0.0
    assert money.recall == 0.0
    money_class = _label(score, "money_class")
    assert money_class is not None
    assert (money_class.correct, money_class.total, money_class.accuracy) == (0, 0, None)


def test_nothing_expected_and_nothing_extracted_scores_none_not_zero() -> None:
    score = score_extraction(MeetingExtraction(), Extraction())
    for category in score.categories:
        assert category.expected_count == 0
        assert category.actual_count == 0
        assert category.matched == 0
        assert category.precision is None
        assert category.recall is None
    assert score.labels == []
