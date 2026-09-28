"""T17: the eval judge's Q1-Q5 scoring -- a scripted `EvalJudgeModel`, offline, no network
(same discipline as `tests/test_gates_judge.py` for the release judge). What's tested here is
the wiring: quote verification against the report text, a missing criterion defaulting to the
worst score rather than vanishing, and Q6's derivation from G14 rather than a judge call.
"""

from __future__ import annotations

from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from report_eval.judge_rubric import (
    MarkerSummary,
    RawEvalJudgeVerdict,
    RawQFinding,
    derive_q6,
    score_q1_to_q5,
)

REPORT_TEXT = (
    "## Recommendations\n\nWe recommend moving £20,000 into the ISA.\n\n"
    "## Fees & Charges\n\n[ADVISER TO CONFIRM #1: ongoing platform charge rate, the platform]."
)


class ScriptedEvalJudge:
    def __init__(self, verdict: RawEvalJudgeVerdict) -> None:
        self._verdict = verdict
        self.calls = 0

    def judge(self, report_text, spec_text, sources, internal_guidance_text, markers):
        self.calls += 1
        return self._verdict


def _bundle(report_text: str = REPORT_TEXT) -> ReportBundle:
    return ReportBundle(report_text=report_text)


def _clean_verdict() -> RawEvalJudgeVerdict:
    return RawEvalJudgeVerdict(
        findings=[RawQFinding(criterion=c, score=5) for c in ("Q1", "Q2", "Q3", "Q4", "Q5")]
    )


def test_a_clean_verdict_scores_every_criterion_five_with_no_evidence_needed() -> None:
    model = ScriptedEvalJudge(_clean_verdict())
    scores = score_q1_to_q5(_bundle(), spec_text="", sources={}, markers=[], model=model)
    assert {s.criterion for s in scores} == {"Q1", "Q2", "Q3", "Q4", "Q5"}
    assert all(s.score == 5 for s in scores)
    assert all(s.evidence == [] for s in scores)


def test_a_verified_quote_survives_into_the_scored_evidence() -> None:
    verdict = RawEvalJudgeVerdict(
        findings=[
            RawQFinding(
                criterion="Q4",
                score=3,
                report_quote=["We recommend moving £20,000 into the ISA."],
                detail="a little repetitive",
            ),
            *[RawQFinding(criterion=c, score=5) for c in ("Q1", "Q2", "Q3", "Q5")],
        ]
    )
    model = ScriptedEvalJudge(verdict)
    scores = score_q1_to_q5(_bundle(), spec_text="", sources={}, markers=[], model=model)
    q4 = next(s for s in scores if s.criterion == "Q4")
    assert q4.score == 3
    assert q4.evidence == ["We recommend moving £20,000 into the ISA."]
    assert q4.detail == "a little repetitive"


def test_an_unverifiable_quote_is_dropped_but_the_score_is_kept() -> None:
    """The model's score is a judgement call, kept regardless; only the *evidence* it
    offered has to actually be in the report, same discipline as the release judge's claim
    verification (`agent_pipeline.gates.judge._verify_claims`) -- never trusted on the
    model's word alone."""
    verdict = RawEvalJudgeVerdict(
        findings=[
            RawQFinding(
                criterion="Q2",
                score=2,
                report_quote=["a sentence that was never actually written"],
                detail="drifts from the source",
            ),
            *[RawQFinding(criterion=c, score=5) for c in ("Q1", "Q3", "Q4", "Q5")],
        ]
    )
    model = ScriptedEvalJudge(verdict)
    scores = score_q1_to_q5(_bundle(), spec_text="", sources={}, markers=[], model=model)
    q2 = next(s for s in scores if s.criterion == "Q2")
    assert q2.score == 2
    assert q2.evidence == []


def test_a_missing_criterion_defaults_to_the_worst_score_not_silently_absent() -> None:
    verdict = RawEvalJudgeVerdict(
        findings=[RawQFinding(criterion=c, score=5) for c in ("Q1", "Q2", "Q3", "Q4")]
    )
    model = ScriptedEvalJudge(verdict)
    scores = score_q1_to_q5(_bundle(), spec_text="", sources={}, markers=[], model=model)
    q5 = next(s for s in scores if s.criterion == "Q5")
    assert q5.score == 1
    assert "omitted" in q5.detail


def test_markers_are_passed_through_to_the_model() -> None:
    model = ScriptedEvalJudge(_clean_verdict())
    markers = [MarkerSummary(key="advice_charge", description="ongoing advice charge rate")]
    score_q1_to_q5(_bundle(), spec_text="", sources={}, markers=markers, model=model)
    assert model.calls == 1


def test_q6_derives_from_a_passing_g14_result() -> None:
    q6 = derive_q6(GateResult("G14", True))
    assert q6.criterion == "Q6"
    assert q6.score == 5
    assert q6.evidence == []


def test_q6_derives_from_a_failing_g14_result() -> None:
    q6 = derive_q6(GateResult("G14", False, "missing required marker(s): ['advice_charge']"))
    assert q6.criterion == "Q6"
    assert q6.score == 1
    assert q6.detail == "missing required marker(s): ['advice_charge']"
