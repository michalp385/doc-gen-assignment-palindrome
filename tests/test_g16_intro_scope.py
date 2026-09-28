"""The introduction's scope sentence is checked in code, not sourced by the judge (tests first).

Which accounts the report covers is decided in code (R2, R8) and handed to the writer, so
"does the introduction name exactly the in-scope account types" has a right answer: compare
it with the ledger. G16 no longer asks the judge for a source quote for that sentence (a
quote from the request's scope field that rarely matched the Introduction's own wording, so
the claim failed verification); a mismatch with the ledger fails G16 instead.

A scope sentence carrying a figure or a tax term still needs a claim, and every other
section is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from agent_pipeline.gates.judge import (
    JudgeMaterialClaim,
    RawJudgeVerdict,
    _check_g16,
    intro_scope_problems,
)
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.sources.document import SourceDoc


def _account(account_id: str, type_: str, *, in_scope: bool, status: str = "open") -> Account:
    return Account(
        id=account_id,
        owners=["A Client"],
        type=type_,
        platform="Holloway",
        in_scope=in_scope,
        status=status,  # type: ignore[arg-type]  # callers pass "open" or "closed"
    )


def _ledger() -> Ledger:
    return Ledger(
        client="c",
        accounts=[
            _account("X-ISA", "Stocks & Shares ISA", in_scope=True),
            _account("X-GIA", "General Investment Account", in_scope=True),
            _account("X-CASH", "Cash Account", in_scope=False),
            _account("X-OLD", "Cash Account", in_scope=False, status="closed"),
        ],
    )


GOOD = (
    "We are writing to set out our advice on your Stocks & Shares ISA and General Investment "
    "Account held with Holloway."
)


# --- intro_scope_problems --------------------------------------------------------------------


def test_an_introduction_naming_exactly_the_in_scope_types_is_fine() -> None:
    assert intro_scope_problems(GOOD, _ledger()) == []


def test_a_plural_or_reordered_mention_is_fine() -> None:
    text = "Our advice covers your General Investment Account and your Stocks & Shares ISAs."
    assert intro_scope_problems(text, _ledger()) == []


def test_an_alias_counts_as_naming_the_type() -> None:
    text = "Our advice covers your Stocks & Shares ISA and your GIA held with Holloway."
    assert intro_scope_problems(text, _ledger()) == []


def test_a_missing_in_scope_type_is_a_problem() -> None:
    problems = intro_scope_problems("Our advice covers your Stocks & Shares ISA.", _ledger())
    assert any("General Investment Account" in p for p in problems)


def test_naming_an_out_of_scope_type_is_a_problem() -> None:
    problems = intro_scope_problems(GOOD + " It also covers your Cash Account.", _ledger())
    assert any("Cash Account" in p and "out of scope" in p for p in problems)


def test_a_type_that_is_in_scope_for_one_account_may_be_named_though_another_is_not() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _account("A", "Stocks & Shares ISA", in_scope=True),
            _account("B", "Stocks & Shares ISA", in_scope=False),
        ],
    )
    assert intro_scope_problems("This covers your Stocks & Shares ISA.", ledger) == []


def test_a_new_account_needs_no_type_wording() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _account("A", "Stocks & Shares ISA", in_scope=True),
            Account(
                id="new:x",
                owners=["A Client"],
                type="New joint account",
                in_scope=True,
                is_new=True,
            ),
        ],
    )
    assert intro_scope_problems("This covers your Stocks & Shares ISA.", ledger) == []


def test_an_empty_introduction_is_not_checked() -> None:
    assert intro_scope_problems("", _ledger()) == []


# --- G16 ---------------------------------------------------------------------------------------


class _Judge:
    def __init__(self, claims: list[JudgeMaterialClaim] | None = None) -> None:
        self._claims = claims or []

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


def _g16(intro: str, claims: list[JudgeMaterialClaim] | None = None, rest: str = "") -> GateResult:
    sections = {"introduction": intro}
    if rest:
        sections["recommendations"] = rest
    text = "\n\n".join(sections.values())
    bundle = ReportBundle(report_text=text, sections=sections, ledger=_ledger())
    judge = _Judge(claims)
    result, _ = _check_g16(judge.judge(bundle, _ledger(), {}, []), judge, bundle, _ledger(), {})
    return result


def test_a_matching_introduction_passes_g16_with_no_claim() -> None:
    assert _g16(GOOD).passed


def test_a_claim_the_judge_invents_for_the_scope_sentence_is_ignored() -> None:
    invented = JudgeMaterialClaim(
        claim="scope",
        report_quote=GOOD,
        source_id="report_request.docx",
        paragraph_id="p9",
        quote="not the request's wording",
    )
    assert _g16(GOOD, [invented]).passed


def test_a_mismatching_introduction_fails_g16() -> None:
    result = _g16("Our advice covers your Stocks & Shares ISA and your Cash Account.")
    assert not result.passed
    assert "introduction" in result.detail


def test_a_scope_sentence_with_a_figure_still_needs_a_claim() -> None:
    sentence = (
        "Our advice covers your Stocks & Shares ISA and General Investment Account, "
        "worth £45,000 in total."
    )
    result = _g16(sentence)
    assert not result.passed
    assert "uncovered" in result.detail


def test_a_scope_sentence_with_a_tax_term_still_needs_a_claim() -> None:
    sentence = (
        "Our advice covers your Stocks & Shares ISA and General Investment Account, "
        "including capital gains tax."
    )
    assert not _g16(sentence).passed


def test_account_names_in_other_sections_still_need_claims() -> None:
    result = _g16(GOOD, rest="We recommend selling your General Investment Account.")
    assert not result.passed
    assert "uncovered" in result.detail
