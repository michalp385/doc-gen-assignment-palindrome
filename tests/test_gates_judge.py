"""T15: `release_judge` -- G16 claim support + code-enforced sentence coverage (with its
one coverage re-ask), G8 action coverage, and the simple pass/fail findings (G2/G4/G7/G10/
G12/P6). A scripted `JudgeModel`; model behaviour itself is measured by the eval, not here.
"""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.gates.deterministic import ReportBundle
from agent_pipeline.gates.judge import (
    JudgeActionCoverage,
    JudgeFinding,
    JudgeMaterialClaim,
    JudgeRecommendationMapping,
    RawJudgeVerdict,
    release_judge,
)
from agent_pipeline.ledger import Account, Action, Ledger
from agent_pipeline.sources.document import SourceDoc

RECOMMENDATIONS_TEXT = (
    "We recommend moving £20,000 from the Holloway cash account into the Stocks & Shares ISA."
)

GOOD_CLAIM = JudgeMaterialClaim(
    claim="Margaret agreed to move £20,000 from the cash account into the ISA",
    report_quote=RECOMMENDATIONS_TEXT,
    source_id="meeting_notes.docx",
    paragraph_id="p1",
    quote="We agreed she would move £20,000 from the cash account into the Stocks & Shares ISA.",
)


class ScriptedJudge:
    def __init__(self, responses: list[RawJudgeVerdict]):
        self._responses = responses
        self.calls = 0

    def judge(self, bundle, ledger, sources, corrections) -> RawJudgeVerdict:
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[index]


def _sources() -> dict[str, SourceDoc]:
    return {
        "meeting_notes.docx": SourceDoc(
            path=Path("data/client_01_clean/meeting_notes.docx"),
            paragraphs={
                "p1": (
                    "We agreed she would move £20,000 from the cash account into the Stocks & "
                    "Shares ISA."
                )
            },
        )
    }


def _ledger() -> Ledger:
    return Ledger(
        client="client_01_clean",
        accounts=[
            Account(
                id="H-ISA-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                in_scope=True,
            )
        ],
        actions=[Action(id="a1", description="move £20,000 into the ISA", kind="action")],
    )


def _bundle() -> ReportBundle:
    sections = {
        "introduction": "This report covers your account.",
        "recommendations": RECOMMENDATIONS_TEXT,
    }
    return ReportBundle(report_text="\n\n".join(sections.values()), sections=sections)


def _verdict(**overrides) -> RawJudgeVerdict:
    base: dict = dict(
        material_claims=[GOOD_CLAIM],
        action_coverage=[JudgeActionCoverage(action_id="a1", report_quote=RECOMMENDATIONS_TEXT)],
        recommendation_mappings=[
            JudgeRecommendationMapping(report_quote=RECOMMENDATIONS_TEXT, action_id="a1")
        ],
        findings=[],
    )
    base.update(overrides)
    return RawJudgeVerdict(**base)


def test_a_fully_correct_verdict_passes_every_gate_on_the_first_call():
    model = ScriptedJudge([_verdict()])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    assert all(r.passed for r in results)
    assert model.calls == 1


def test_g16_fails_on_a_claim_whose_quote_does_not_verify():
    bad_claim = GOOD_CLAIM.model_copy(update={"quote": "this text is not in the paragraph"})
    model = ScriptedJudge([_verdict(material_claims=[bad_claim])])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g16 = next(r for r in results if r.gate == "G16")
    assert g16.passed is False
    assert "unsupported claim" in g16.detail


def test_g16_uncovered_sentence_fails_only_after_the_reask_also_misses_it():
    model = ScriptedJudge([_verdict(material_claims=[]), _verdict(material_claims=[])])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g16 = next(r for r in results if r.gate == "G16")
    assert g16.passed is False
    assert "uncovered clause" in g16.detail
    assert model.calls == 2


def test_g16_uncovered_sentence_recovers_if_the_reask_fixes_it():
    model = ScriptedJudge([_verdict(material_claims=[]), _verdict()])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g16 = next(r for r in results if r.gate == "G16")
    assert g16.passed is True
    assert model.calls == 2


def test_g8_fails_when_an_agreed_action_has_no_coverage():
    model = ScriptedJudge([_verdict(action_coverage=[])])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g8 = next(r for r in results if r.gate == "G8")
    assert g8.passed is False
    assert "agreed action not covered" in g8.detail


def test_g8_fails_when_a_recommendation_maps_to_no_agreed_action():
    model = ScriptedJudge(
        [
            _verdict(
                recommendation_mappings=[
                    JudgeRecommendationMapping(report_quote=RECOMMENDATIONS_TEXT, action_id=None)
                ]
            )
        ]
    )
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g8 = next(r for r in results if r.gate == "G8")
    assert g8.passed is False
    assert "not tied to an agreed action" in g8.detail


def test_g8_fails_when_a_recommendation_maps_to_an_action_id_not_in_the_ledger():
    model = ScriptedJudge(
        [
            _verdict(
                recommendation_mappings=[
                    JudgeRecommendationMapping(
                        report_quote=RECOMMENDATIONS_TEXT, action_id="not-a-real-action"
                    )
                ]
            )
        ]
    )
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g8 = next(r for r in results if r.gate == "G8")
    assert g8.passed is False
    assert "unknown action id" in g8.detail


def test_a_finding_fails_only_its_own_gate():
    model = ScriptedJudge(
        [_verdict(findings=[JudgeFinding(gate="G4", detail="risk warning paraphrased")])]
    )
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    by_gate = {r.gate: r for r in results}
    assert by_gate["G4"].passed is False
    assert "risk warning paraphrased" in by_gate["G4"].detail
    for gate in ("G2", "G7", "G10", "G12", "P6"):
        assert by_gate[gate].passed is True
    assert by_gate["G16"].passed is True
    assert by_gate["G8"].passed is True


def test_no_findings_means_every_simple_gate_passes():
    model = ScriptedJudge([_verdict()])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    by_gate = {r.gate: r for r in results}
    for gate in ("G2", "G4", "G7", "G10", "G12", "P6"):
        assert by_gate[gate].passed is True


def test_g16_cannot_be_gamed_by_one_oversized_claim_covering_the_whole_report():
    # Verifier report, T15 checkpoint, finding #1: a claim whose report_quote spans the
    # entire report used to "cover" every sentence, including a fabricated one with no
    # source backing at all.
    fabricated = (
        "The client agreed to sell the GIA for £999,999, creating a £140,000 CGT liability."
    )
    sections = {
        "introduction": "This report covers your account.",
        "recommendations": RECOMMENDATIONS_TEXT,
        "tax_implications": fabricated,
    }
    bundle = ReportBundle(report_text="\n\n".join(sections.values()), sections=sections)
    oversized_claim = GOOD_CLAIM.model_copy(update={"report_quote": bundle.report_text})
    model = ScriptedJudge([_verdict(material_claims=[oversized_claim])])

    results = release_judge(bundle, _ledger(), _sources(), model)
    g16 = next(r for r in results if r.gate == "G16")
    assert g16.passed is False
    assert "uncovered clause" in g16.detail
    assert "£999,999" in g16.detail or "CGT" in g16.detail


def test_g16_rejects_a_claim_whose_report_quote_is_not_real_report_text():
    invented_claim = GOOD_CLAIM.model_copy(
        update={"report_quote": "this sentence was never written in the report"}
    )
    model = ScriptedJudge([_verdict(material_claims=[invented_claim])])
    results = release_judge(_bundle(), _ledger(), _sources(), model)
    g16 = next(r for r in results if r.gate == "G16")
    assert g16.passed is False


def test_g8_fails_when_the_same_quote_covers_two_different_actions():
    # Verifier report, T15 checkpoint, finding #2: the same real quote reused for a second,
    # unagreed action made that action look covered without ever being recommended.
    ledger = _ledger().model_copy(
        update={
            "actions": [
                Action(id="a1", description="move £20,000 into the ISA", kind="action"),
                Action(id="a2", description="sell the GIA entirely", kind="action"),
            ]
        }
    )
    model = ScriptedJudge(
        [
            _verdict(
                action_coverage=[
                    JudgeActionCoverage(action_id="a1", report_quote=RECOMMENDATIONS_TEXT),
                    JudgeActionCoverage(action_id="a2", report_quote=RECOMMENDATIONS_TEXT),
                ]
            )
        ]
    )
    results = release_judge(_bundle(), ledger, _sources(), model)
    g8 = next(r for r in results if r.gate == "G8")
    assert g8.passed is False
    assert "same quote covers both" in g8.detail


def test_g16_cannot_be_gamed_by_a_fabricated_clause_splicing_onto_a_covered_one():
    # Second verifier report, T15 checkpoint re-check, finding #1: a fabricated fact glued
    # onto a genuinely-covered one via a comma, reusing the real fact's own figure, used to
    # ride along as "covered" because coverage was checked per whole sentence.
    spliced = (
        "You hold £45,000 in your Stocks & Shares ISA, which also happens to match the "
        "£45,000 CGT liability now due on your GIA disposal."
    )
    sections = {"introduction": "This report covers your account.", "background": spliced}
    bundle = ReportBundle(report_text="\n\n".join(sections.values()), sections=sections)
    genuine_claim = JudgeMaterialClaim(
        claim="the ISA is currently worth £45,000",
        report_quote="You hold £45,000 in your Stocks & Shares ISA",
        source_id="meeting_notes.docx",
        paragraph_id="p1",
        quote=(
            "We agreed she would move £20,000 from the cash account into the Stocks & Shares ISA."
        ),
    )
    model = ScriptedJudge(
        [_verdict(material_claims=[GOOD_CLAIM, genuine_claim]), _verdict(material_claims=[])]
    )

    results = release_judge(bundle, _ledger(), _sources(), model)
    g16 = next(r for r in results if r.gate == "G16")
    assert g16.passed is False
    assert "CGT liability" in g16.detail
