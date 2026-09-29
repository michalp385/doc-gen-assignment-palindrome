"""G7 does not fire on permitted disposal-proceeds wording (tests first).

SCOPING P5: full-disposal proceeds count toward the plan's funding once the amount and
destination are known, described as gross, before any CGT and not yet realised. So a
Recommendations sentence that states the ledger's own counted-proceeds figure, immediately
followed by the standard timing caveat ("... becomes available once the disposal completes"),
is permitted, and a release-judge G7 finding that quotes it is dropped in code. G7's real
target is external or contingent money and money treated as available when it is not.

The carve-out is narrow: the figure must be a ledger proceeds fact's own rendering, and the
caveat sentence must follow directly. Every other G7 finding is kept.
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.gates.deterministic import ReportBundle
from agent_pipeline.gates.judge import (
    JudgeActionCoverage,
    JudgeFinding,
    JudgeRecommendationMapping,
    RawJudgeVerdict,
    release_judge,
)
from agent_pipeline.ledger import Action, Fact, Ledger, Value

CAVEAT = "This figure is gross before any CGT and becomes available once the disposal completes."
PROCEEDS = "We recommend using the gross proceeds of c. £38,000 to fund both ISAs."
OTHER = "We recommend using the earnout of £400,000 to fund the ISAs."


def _ledger() -> Ledger:
    value = Value(
        amount=Decimal("38000"),
        currency="GBP",
        precision="approximate",
        qualifier="around",
        date=None,
        source_id="m",
        quote="around £38,000",
        selected_by="R3",
    )
    return Ledger(
        client="c",
        actions=[Action(id="a1", description="disinvest the account", kind="action")],
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the gross sale proceeds",
                value=value,
                reportable=True,
                role="sale proceeds",
            )
        },
    )


def _bundle(recommendations: str) -> ReportBundle:
    return ReportBundle(report_text=recommendations, sections={"recommendations": recommendations})


class _Scripted:
    def __init__(self, recommendations: str, quotes: list[str]) -> None:
        self._verdict = RawJudgeVerdict(
            material_claims=[],
            action_coverage=[JudgeActionCoverage(action_id="a1", report_quote=PROCEEDS)],
            recommendation_mappings=[
                JudgeRecommendationMapping(report_quote=PROCEEDS, action_id="a1")
            ],
            findings=[
                JudgeFinding(gate="G7", detail="allocates unavailable money", quote=q)
                for q in quotes
            ],
        )

    def judge(self, bundle, ledger, sources, corrections) -> RawJudgeVerdict:  # type: ignore[no-untyped-def]
        return self._verdict


def _g7(recommendations: str, quotes: list[str]):  # type: ignore[no-untyped-def]
    model = _Scripted(recommendations, quotes)
    results = release_judge(_bundle(recommendations), _ledger(), {}, model)
    return next(r for r in results if r.gate == "G7")


def test_a_finding_on_proceeds_followed_by_the_caveat_is_dropped() -> None:
    assert _g7(f"{PROCEEDS} {CAVEAT}", [PROCEEDS]).passed


def test_the_same_finding_stands_without_the_caveat() -> None:
    assert not _g7(PROCEEDS, [PROCEEDS]).passed


def test_a_caveat_that_is_not_the_next_sentence_does_not_count() -> None:
    text = f"{PROCEEDS} We also recommend a review. {CAVEAT}"
    assert not _g7(text, [PROCEEDS]).passed


def test_a_figure_that_is_not_a_ledger_proceeds_figure_stands() -> None:
    assert not _g7(f"{OTHER} {CAVEAT}", [OTHER]).passed


def test_a_real_finding_is_kept_alongside_a_dropped_one() -> None:
    text = f"{PROCEEDS} {CAVEAT} {OTHER}"
    result = _g7(text, [PROCEEDS, OTHER])
    assert not result.passed and "earnout" in result.detail


def test_a_finding_without_a_quote_is_kept() -> None:
    model = _Scripted(f"{PROCEEDS} {CAVEAT}", [])
    model._verdict.findings.append(JudgeFinding(gate="G7", detail="vague"))
    results = release_judge(_bundle(f"{PROCEEDS} {CAVEAT}"), _ledger(), {}, model)
    assert not next(r for r in results if r.gate == "G7").passed
