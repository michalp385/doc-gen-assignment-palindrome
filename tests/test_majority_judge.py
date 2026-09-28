"""The majority-vote release judge (D22 option 1), tests first.

The judge model rejects `temperature`, so one sample per report can fail a correct report
(three different false positives in three passes). `majority_release_judge` runs an odd
number of independent judge runs -- each a full `release_judge` pass with its own coverage
re-ask -- and each gate passes or fails by the majority of them. G7, G8 and G16 stay hard
gates; one dissenting sample no longer decides. Code does the vote; the model only opines.

Each sample must be a separate model call, so `LLMJudgeModel` gives sample `i > 0` its own
cache key (an extra input); sample 0 keeps the key a single-sample run already has.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from agent_pipeline.config import PromptSpec, StageConfig, load_report_config
from agent_pipeline.gates.deterministic import ReportBundle
from agent_pipeline.gates.judge import (
    JudgeActionCoverage,
    JudgeFinding,
    JudgeMaterialClaim,
    JudgeRecommendationMapping,
    LLMJudgeModel,
    RawJudgeVerdict,
    judge_models,
    majority_release_judge,
    release_judge,
)
from agent_pipeline.ledger import Account, Action, Ledger
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.document import SourceDoc

RECOMMENDATIONS = (
    "We recommend moving £20,000 from the Holloway cash account into the Stocks & Shares ISA."
)
GOOD_CLAIM = JudgeMaterialClaim(
    claim="agreed to move £20,000",
    report_quote=RECOMMENDATIONS,
    source_id="meeting_notes.docx",
    paragraph_id="p1",
    quote="We agreed she would move £20,000 from the cash account into the Stocks & Shares ISA.",
)
BAD_CLAIM = JudgeMaterialClaim(
    claim="invented",
    report_quote=RECOMMENDATIONS,
    source_id="meeting_notes.docx",
    paragraph_id="p1",
    quote="a quote that is not in the source",
)


class Scripted:
    def __init__(self, verdict: RawJudgeVerdict) -> None:
        self._verdict = verdict
        self.calls = 0

    def judge(self, bundle, ledger, sources, corrections) -> RawJudgeVerdict:  # type: ignore[no-untyped-def]
        self.calls += 1
        return self._verdict


def _sources() -> dict[str, SourceDoc]:
    return {
        "meeting_notes.docx": SourceDoc(
            path=Path("m.docx"),
            paragraphs={
                "p1": "We agreed she would move £20,000 from the cash account into the "
                "Stocks & Shares ISA."
            },
        )
    }


def _ledger() -> Ledger:
    return Ledger(
        client="c",
        accounts=[Account(id="A", owners=["A Client"], type="Stocks & Shares ISA", in_scope=True)],
        actions=[Action(id="a1", description="move money", kind="action")],
    )


def _bundle() -> ReportBundle:
    sections = {
        "introduction": "This report covers your account.",
        "recommendations": RECOMMENDATIONS,
    }
    return ReportBundle(report_text="\n\n".join(sections.values()), sections=sections)


def _verdict(
    claims: list[JudgeMaterialClaim] | None = None,
    findings: list[JudgeFinding] | None = None,
    covered: bool = True,
) -> RawJudgeVerdict:
    return RawJudgeVerdict(
        material_claims=[GOOD_CLAIM] if claims is None else claims,
        action_coverage=[JudgeActionCoverage(action_id="a1", report_quote=RECOMMENDATIONS)]
        if covered
        else [],
        recommendation_mappings=[
            JudgeRecommendationMapping(report_quote=RECOMMENDATIONS, action_id="a1")
        ],
        findings=findings or [],
    )


GOOD = _verdict()
G7_FAIL = _verdict(findings=[JudgeFinding(gate="G7", detail="proceeds not available")])
G16_FAIL = _verdict(claims=[GOOD_CLAIM, BAD_CLAIM])
G8_FAIL = _verdict(covered=False)


def _run(*verdicts: RawJudgeVerdict) -> dict:
    results = majority_release_judge(
        _bundle(), _ledger(), _sources(), [Scripted(v) for v in verdicts]
    )
    return {r.gate: r for r in results}


def test_all_samples_agreeing_the_report_is_fine_passes_every_gate() -> None:
    assert all(r.passed for r in _run(GOOD, GOOD, GOOD).values())


def test_one_dissenting_finding_does_not_fail_the_gate_but_is_noted() -> None:
    results = _run(GOOD, GOOD, G7_FAIL)
    assert results["G7"].passed
    assert "1 of 3" in results["G7"].detail


def test_a_majority_finding_fails_that_gate_only() -> None:
    results = _run(GOOD, G7_FAIL, G7_FAIL)
    assert not results["G7"].passed
    assert "2 of 3" in results["G7"].detail
    assert "proceeds not available" in results["G7"].detail
    assert all(r.passed for gate, r in results.items() if gate != "G7")


def test_an_unsupported_claim_in_one_sample_does_not_fail_g16() -> None:
    assert _run(GOOD, GOOD, G16_FAIL)["G16"].passed


def test_an_unsupported_claim_in_a_majority_fails_g16() -> None:
    result = _run(GOOD, G16_FAIL, G16_FAIL)["G16"]
    assert not result.passed
    assert "unsupported" in result.detail


def test_g8_is_voted_the_same_way() -> None:
    assert _run(GOOD, GOOD, G8_FAIL)["G8"].passed
    assert not _run(G8_FAIL, G8_FAIL, GOOD)["G8"].passed


def test_each_gate_is_voted_independently() -> None:
    # no single gate has a majority against it, so nothing fails, though every sample fails one
    results = _run(G7_FAIL, G8_FAIL, G16_FAIL)
    assert all(r.passed for r in results.values())


def test_one_sample_is_exactly_the_plain_release_judge() -> None:
    plain = release_judge(_bundle(), _ledger(), _sources(), Scripted(G7_FAIL))
    voted = majority_release_judge(_bundle(), _ledger(), _sources(), [Scripted(G7_FAIL)])
    assert [(r.gate, r.passed) for r in voted] == [(r.gate, r.passed) for r in plain]


def test_results_keep_release_judges_gate_order() -> None:
    plain = release_judge(_bundle(), _ledger(), _sources(), Scripted(GOOD))
    voted = majority_release_judge(_bundle(), _ledger(), _sources(), [Scripted(GOOD)] * 3)
    assert [r.gate for r in voted] == [r.gate for r in plain]


@pytest.mark.parametrize("count", [0, 2, 4])
def test_an_even_or_empty_number_of_samples_is_refused(count: int) -> None:
    with pytest.raises(ValueError, match="odd"):
        majority_release_judge(_bundle(), _ledger(), _sources(), [Scripted(GOOD)] * count)


def test_every_sample_is_run() -> None:
    models = [Scripted(GOOD) for _ in range(3)]
    majority_release_judge(_bundle(), _ledger(), _sources(), models)
    assert all(m.calls >= 1 for m in models)


# --- separate cache entries per sample ----------------------------------------------------


class _RecordingLLM:
    def __init__(self) -> None:
        self.inputs: list[dict] = []

    def structured(self, *, stage: str, prompt: PromptSpec, inputs: dict, schema: type):  # type: ignore[no-untyped-def]
        self.inputs.append(inputs)

        class _Result:
            output = GOOD

        return _Result()


def _sample_inputs(sample: int) -> dict:
    llm = _RecordingLLM()
    model = LLMJudgeModel(cast(LLMClient, llm), PromptSpec(text="t", version="v"), sample=sample)
    model.judge(_bundle(), _ledger(), _sources(), [])
    return llm.inputs[0]


def test_sample_zero_keeps_the_single_sample_cache_key() -> None:
    assert "sample" not in _sample_inputs(0)


def test_later_samples_get_their_own_cache_key() -> None:
    assert _sample_inputs(1)["sample"] == 1
    assert _sample_inputs(2)["sample"] == 2
    assert _sample_inputs(1) != _sample_inputs(2) != _sample_inputs(0)


def test_judge_models_builds_one_model_per_sample() -> None:
    models = judge_models(cast(LLMClient, _RecordingLLM()), PromptSpec(text="t", version="v"), 3)
    assert len(models) == 3


# --- the setting ---------------------------------------------------------------------------


def test_stage_samples_default_to_one_and_must_be_odd() -> None:
    assert StageConfig(model="m", reasoning_effort="low").samples == 1
    assert StageConfig(model="m", reasoning_effort="low", samples=3).samples == 3
    for bad in (0, 2, 4):
        with pytest.raises(ValidationError):
            StageConfig(model="m", reasoning_effort="low", samples=bad)


def test_the_shipped_release_judge_stage_has_a_valid_sample_count() -> None:
    config = load_report_config(Path("config/template_config.json"))
    samples = config.stages["release_judge"].samples
    assert samples >= 1 and samples % 2 == 1
