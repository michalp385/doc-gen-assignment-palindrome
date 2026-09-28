"""G16 and required standard wording (tests first).

G16 asks for source support for client-specific factual claims. The Tax Implications slot
must state, as spec wording (P7), that a disposal may create a capital gains tax liability
assessed against the annual exempt amount, and a proceeds sentence says they are gross before
CGT (P5). Neither has a client source by design -- the same category as the FCA line and risk
warning -- so a judge asked for a source quote for them can only invent one, which fails
verification and makes G16 fail a correct report (client 02).

The exemption is a concrete whitelist (`config/standard_wording.json`) applied in code, not an
instruction to the judge: a whitelisted sentence needs no claim, any claim the judge gives for
one is ignored, and the judge is not shown it. It never applies to a sentence carrying a
figure or an account name, so an invented client claim still fails.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from agent_pipeline.config import PromptSpec
from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from agent_pipeline.gates.judge import (
    JudgeMaterialClaim,
    LLMJudgeModel,
    RawJudgeVerdict,
    _check_g16,
    is_standard_wording,
    redact_standard_wording,
)
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.document import SourceDoc

CGT_SENTENCE = (
    "We note that the disposal may create a capital gains tax liability assessed against "
    "the annual exempt amount for the relevant tax year."
)
GROSS_SENTENCE = "The stated proceeds are gross before capital gains tax."


def _ledger() -> Ledger:
    return Ledger(
        client="c",
        accounts=[
            Account(
                id="X-GIA",
                owners=["A Client"],
                type="General Investment Account",
                platform="Holloway",
                in_scope=True,
            )
        ],
    )


# --- the whitelist ---------------------------------------------------------------------------


def test_the_spec_cgt_sentence_is_standard_wording() -> None:
    assert is_standard_wording(CGT_SENTENCE, _ledger())


def test_the_gross_proceeds_sentence_is_standard_wording() -> None:
    assert is_standard_wording(GROSS_SENTENCE, _ledger())


def test_light_rewording_inside_the_whitelist_is_still_standard() -> None:
    for sentence in (
        "The disposal may create a capital gains tax liability assessed against the annual "
        "exempt amount.",
        "The sale may create a capital gains tax liability assessed against the annual "
        "exempt amount for the relevant tax year.",
        "The proceeds are gross, before capital gains tax.",
        "The stated proceeds are gross before CGT and not yet realised.",
    ):
        assert is_standard_wording(sentence, _ledger()), sentence


def test_a_figure_or_percentage_removes_the_exemption() -> None:
    for sentence in (
        "The disposal may create a capital gains tax liability of £3,540 assessed against "
        "the annual exempt amount.",
        "The disposal may create a capital gains tax liability assessed against the annual "
        "exempt amount of £3,000.",
        "The stated proceeds are gross before capital gains tax at 20%.",
    ):
        assert not is_standard_wording(sentence, _ledger()), sentence


def test_an_account_name_or_type_removes_the_exemption() -> None:
    sentence = (
        "The disposal of your General Investment Account may create a capital gains tax "
        "liability assessed against the annual exempt amount."
    )
    assert not is_standard_wording(sentence, _ledger())


def test_a_client_specific_tax_claim_is_not_standard_wording() -> None:
    for sentence in (
        "You will owe capital gains tax on this disposal.",
        "The disposal will create a large capital gains tax liability.",
        "Your annual exempt amount has already been used this year.",
        "The disposal may create a capital gains tax liability.",
    ):
        assert not is_standard_wording(sentence, _ledger()), sentence


def test_the_fca_line_and_risk_warning_are_not_this_whitelists_business() -> None:
    # they are exempt elsewhere (static template text, G4); nothing here should claim them
    assert not is_standard_wording(
        "This firm is authorised and regulated by the Financial Conduct Authority.", _ledger()
    )


# --- redaction: the judge is not shown standard wording --------------------------------------


def test_standard_sentences_are_replaced_by_a_placeholder() -> None:
    text = f"We recommend a top-up. {GROSS_SENTENCE}\n\n{CGT_SENTENCE}\n\nThe end."
    redacted = redact_standard_wording(text, _ledger())
    assert "gross before capital gains tax" not in redacted
    assert "annual exempt amount" not in redacted
    assert redacted.count("[standard wording]") == 2
    assert "We recommend a top-up." in redacted and "The end." in redacted


def test_text_with_no_standard_wording_is_untouched() -> None:
    text = "We recommend a top-up.\n\nThe value of investments can fall as well as rise."
    assert redact_standard_wording(text, _ledger()) == text


class _RecordingLLM:
    def __init__(self) -> None:
        self.inputs: dict = {}

    def structured(self, *, stage: str, prompt: PromptSpec, inputs: dict, schema: type):
        self.inputs = inputs

        class _Result:
            output = RawJudgeVerdict(
                material_claims=[], action_coverage=[], recommendation_mappings=[], findings=[]
            )

        return _Result()


def test_the_real_judge_model_sends_the_redacted_report() -> None:
    llm = _RecordingLLM()
    model = LLMJudgeModel(cast(LLMClient, llm), PromptSpec(text="t", version="v"))
    bundle = ReportBundle(report_text=f"Intro. {CGT_SENTENCE}", ledger=_ledger())
    model.judge(bundle, _ledger(), {}, [])
    assert "annual exempt amount" not in llm.inputs["report_text"]
    assert "[standard wording]" in llm.inputs["report_text"]


# --- G16 end to end --------------------------------------------------------------------------


class _ScriptedJudge:
    def __init__(self, claims: list[JudgeMaterialClaim]) -> None:
        self._claims = claims

    def judge(
        self,
        bundle: ReportBundle,
        ledger: Ledger,
        sources: Mapping[str, SourceDoc],
        corrections: list[str],
    ) -> RawJudgeVerdict:
        return RawJudgeVerdict(
            material_claims=self._claims,
            action_coverage=[],
            recommendation_mappings=[],
            findings=[],
        )


def _bundle(*sentences: str) -> ReportBundle:
    text = "\n\n".join(sentences)
    return ReportBundle(report_text=text, sections={"tax_implications": text}, ledger=_ledger())


def _g16(bundle: ReportBundle, claims: list[JudgeMaterialClaim]) -> GateResult:
    judge = _ScriptedJudge(claims)
    raw = judge.judge(bundle, _ledger(), {}, [])
    result, _ = _check_g16(raw, judge, bundle, _ledger(), {})
    return result


def test_standard_wording_passes_g16_with_no_claim_at_all() -> None:
    assert _g16(_bundle(CGT_SENTENCE, GROSS_SENTENCE), []).passed


def test_claims_the_judge_invents_for_standard_wording_are_ignored() -> None:
    invented = [
        JudgeMaterialClaim(
            claim="proceeds are gross",
            report_quote=GROSS_SENTENCE,
            source_id="meeting_notes.docx",
            paragraph_id="p1",
            quote="not a real quote",
        ),
        JudgeMaterialClaim(
            claim="cgt liability",
            report_quote=CGT_SENTENCE,
            source_id="meeting_notes.docx",
            paragraph_id="p2",
            quote="also not real",
        ),
    ]
    assert _g16(_bundle(CGT_SENTENCE, GROSS_SENTENCE), invented).passed


def test_an_invented_client_tax_claim_still_fails_g16() -> None:
    result = _g16(_bundle(CGT_SENTENCE, "You will owe capital gains tax on this sale."), [])
    assert not result.passed
    assert "owe capital gains tax" in result.detail


def test_a_fabricated_figure_in_a_standard_looking_sentence_still_fails_g16() -> None:
    sentence = (
        "The disposal may create a capital gains tax liability of £3,540 assessed against "
        "the annual exempt amount."
    )
    assert not _g16(_bundle(sentence), []).passed


def test_an_unverifiable_claim_about_a_client_sentence_still_fails_g16() -> None:
    fabricated = JudgeMaterialClaim(
        claim="owes tax",
        report_quote="You will owe capital gains tax on this sale.",
        source_id="meeting_notes.docx",
        paragraph_id="p1",
        quote="not a real quote",
    )
    bundle = _bundle("You will owe capital gains tax on this sale.")
    assert not _g16(bundle, [fabricated]).passed
