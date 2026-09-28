"""The eval judge (DESIGN.md section 10.3, SCOPING.md Q1-Q6): one structured Sol call scoring
a report 1-5 on each of Q1-Q5, evidence quotes verified against the report text in code (never
trusted on the model's word, same discipline as `agent_pipeline.gates.judge`). Q6 is not a
judge call at all -- SCOPING.md says it's deterministic wherever expected facts exist, and
that's exactly G14 (`gates.deterministic._check_g14`), already computed -- `derive_q6` just
reads it off that `GateResult`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from agent_pipeline.config import PromptSpec
from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.document import SourceDoc
from report_eval.results import QCriterionScore

Criterion = Literal["Q1", "Q2", "Q3", "Q4", "Q5"]


class RawQFinding(BaseModel):
    criterion: Criterion
    score: int = Field(ge=1, le=5)
    report_quote: list[str] = Field(default_factory=list)
    detail: str = ""


class RawEvalJudgeVerdict(BaseModel):
    findings: list[RawQFinding]


class MarkerSummary(BaseModel):
    key: str
    description: str


class EvalJudgeModel(Protocol):
    def judge(
        self,
        report_text: str,
        spec_text: str,
        sources: Mapping[str, SourceDoc],
        internal_guidance_text: str,
        markers: list[MarkerSummary],
    ) -> RawEvalJudgeVerdict: ...


class LLMEvalJudgeModel:
    """The real `EvalJudgeModel`, wrapping T11's `LLMClient` and
    `config/prompts/eval_judge.md`. Stage `eval_judge` (Sol, DESIGN.md section 10.3) is a
    separate model from the pipeline's own `release_judge` stage (Luna by default) -- the eval
    judge is a measurement tool, not a pipeline stage, so it is never subject to the
    default-cheap-model constraint DESIGN.md section 10.9 places on the pipeline itself."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def judge(
        self,
        report_text: str,
        spec_text: str,
        sources: Mapping[str, SourceDoc],
        internal_guidance_text: str,
        markers: list[MarkerSummary],
    ) -> RawEvalJudgeVerdict:
        result = self._llm.structured(
            stage="eval_judge",
            prompt=self._prompt,
            inputs={
                "report_text": report_text,
                "spec_text": spec_text,
                "sources": {
                    source_id: [f"[{pid}] {text}" for pid, text in doc.paragraphs.items()]
                    for source_id, doc in sources.items()
                },
                "internal_guidance_text": internal_guidance_text,
                "markers": [m.model_dump() for m in markers],
            },
            schema=RawEvalJudgeVerdict,
        )
        return result.output


_ALL_CRITERIA: tuple[Criterion, ...] = ("Q1", "Q2", "Q3", "Q4", "Q5")


def score_q1_to_q5(
    bundle: ReportBundle,
    spec_text: str,
    sources: Mapping[str, SourceDoc],
    markers: list[MarkerSummary],
    model: EvalJudgeModel,
) -> list[QCriterionScore]:
    raw = model.judge(
        bundle.report_text, spec_text, sources, bundle.internal_guidance_text, markers
    )
    by_criterion = {f.criterion: f for f in raw.findings}
    scores = []
    for criterion in _ALL_CRITERIA:
        finding = by_criterion.get(criterion)
        if finding is None:
            # The model dropped a criterion it was told to always score -- treat as the
            # worst case rather than silently missing a headline number.
            scores.append(
                QCriterionScore(criterion=criterion, score=1, detail="judge omitted this criterion")
            )
            continue
        verified_quotes = [q for q in finding.report_quote if q in bundle.report_text]
        scores.append(
            QCriterionScore(
                criterion=criterion,
                score=finding.score,
                evidence=verified_quotes,
                detail=finding.detail,
            )
        )
    return scores


def derive_q6(g14_result: GateResult) -> QCriterionScore:
    return QCriterionScore(
        criterion="Q6",
        score=5 if g14_result.passed else 1,
        evidence=[],
        detail=g14_result.detail,
    )
