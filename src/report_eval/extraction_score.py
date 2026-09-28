"""Extraction scoring (DESIGN.md section 10.7): per-category precision/recall and per-label
accuracy (basis, money class, blocking, disposal extent), so extraction can be measured on its
own rather than only through whether the final report came out right.

Expected items (`report_eval.expected.Extraction`) and actual items
(`agent_pipeline.extract.schemas.MeetingExtraction`) don't share field names or an id space --
neither has a stable identifier a fixture and a live model call could agree on -- so matching is
by text overlap between each expected item's quotes and each actual item's quotes, greedy
best-match per category, never reused. This is approximate by nature (a scoring tool, not a
gate); the reference bundle would score itself perfectly by construction, and that's the
calibration check in `tests/test_extraction_score.py`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypeVar

from agent_pipeline.extract.schemas import MeetingExtraction
from report_eval.expected import Extraction
from report_eval.results import CategoryScore, ExtractionScore, LabelScore

MATCH_THRESHOLD = 0.3  # share of the smaller item's significant words that must overlap

E = TypeVar("E")
A = TypeVar("A")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def _overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _score_category(
    category: str,
    expected: list[E],
    actual: list[A],
    expected_text: Callable[[E], str],
    actual_text: Callable[[A], str],
    label: str | None = None,
    expected_label: Callable[[E], object] | None = None,
    actual_label: Callable[[A], object] | None = None,
) -> tuple[CategoryScore, LabelScore | None]:
    matched_actual: set[int] = set()
    pairs: list[tuple[E, A]] = []
    for exp in expected:
        best_idx: int | None = None
        best_score = 0.0
        for i, act in enumerate(actual):
            if i in matched_actual:
                continue
            score = _overlap(expected_text(exp), actual_text(act))
            if score > best_score:
                best_score, best_idx = score, i
        if best_idx is not None and best_score >= MATCH_THRESHOLD:
            matched_actual.add(best_idx)
            pairs.append((exp, actual[best_idx]))

    matched = len(pairs)
    expected_count = len(expected)
    actual_count = len(actual)
    category_score = CategoryScore(
        category=category,
        expected_count=expected_count,
        actual_count=actual_count,
        matched=matched,
        precision=(matched / actual_count) if actual_count else None,
        recall=(matched / expected_count) if expected_count else None,
    )

    # Suppressed only when the category itself is entirely empty on both sides -- there is
    # nothing to say about a label's accuracy then, same as CategoryScore's None precision/
    # recall. A category with items on either side keeps its LabelScore even with 0 matched
    # pairs, since "extraction missed this category completely" (accuracy: None, total: 0)
    # is itself the informative result.
    label_score = None
    if (
        label is not None
        and expected_label is not None
        and actual_label is not None
        and (expected_count or actual_count)
    ):
        correct = sum(1 for exp, act in pairs if str(expected_label(exp)) == str(actual_label(act)))
        total = len(pairs)
        label_score = LabelScore(
            label=label, correct=correct, total=total, accuracy=(correct / total) if total else None
        )
    return category_score, label_score


def score_extraction(actual: MeetingExtraction, expected: Extraction) -> ExtractionScore:
    categories: list[CategoryScore] = []
    labels: list[LabelScore] = []

    cat, lab = _score_category(
        "value_observations",
        expected.value_observations,
        actual.value_observations,
        expected_text=lambda e: f"{e.account} {e.amount_quote} {e.evidence_quote}",
        actual_text=lambda a: f"{a.account_reference} {a.amount.text} {a.basis_evidence.text}",
        label="basis",
        expected_label=lambda e: e.basis,
        actual_label=lambda a: a.basis,
    )
    categories.append(cat)
    if lab:
        labels.append(lab)

    cat, lab = _score_category(
        "money_items",
        expected.money_items,
        actual.money_items,
        expected_text=lambda e: f"{e.amount_quote or ''} {e.evidence_quote}",
        actual_text=lambda a: (
            f"{a.purpose} {a.amount.text if a.amount else ''} {a.class_evidence.text}"
        ),
        label="money_class",
        expected_label=lambda e: e.item_class,
        actual_label=lambda a: a.money_class,
    )
    categories.append(cat)
    if lab:
        labels.append(lab)

    cat, lab = _score_category(
        "disposals",
        expected.disposals,
        actual.disposals,
        expected_text=lambda e: f"{e.account} {e.evidence_quote}",
        actual_text=lambda a: f"{a.account_reference} {a.quote.text} {a.extent_evidence.text}",
        label="extent",
        expected_label=lambda e: e.extent,
        actual_label=lambda a: a.extent,
    )
    categories.append(cat)
    if lab:
        labels.append(lab)

    cat, lab = _score_category(
        "open_actions",
        expected.open_actions,
        actual.open_actions,
        expected_text=lambda e: f"{e.description} {e.evidence_quote}",
        actual_text=lambda a: f"{a.text.text} {a.blocking_evidence.text}",
        label="blocking",
        expected_label=lambda e: e.blocking,
        actual_label=lambda a: a.blocking,
    )
    categories.append(cat)
    if lab:
        labels.append(lab)

    return ExtractionScore(categories=categories, labels=labels)
