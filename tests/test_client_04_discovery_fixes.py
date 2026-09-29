"""Two bugs the first live run of client 04 exposed (tests first).

1. G16 split a marker's bracket text at its comma, so the second half ("pending confirmation
   of the account's tax treatment]") lost its opening bracket, mentioned tax, and demanded a
   claim. A marker's own bracket text is inserted by code and never needs one, however it is
   punctuated: marker spans are removed before a sentence is split into clauses.
2. "the Holloway joint GIA" matched every General Investment Account, because a reference
   was narrowed by owner but not by platform, so a disposal of one of two same-type accounts
   became an "unknown" wrapper. A reference naming a platform now narrows to that platform's
   accounts when it leaves exactly one.
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from agent_pipeline.gates.judge import RawJudgeVerdict, _check_g16
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.reconcile.refs import accounts_matching_reference
from agent_pipeline.sources.document import SourceDoc

# --- G16 and a marker's bracket text ---------------------------------------------------------


class _Judge:
    def judge(
        self,
        bundle: ReportBundle,
        ledger: Ledger,
        sources: Mapping[str, SourceDoc],
        corrections: list[str],
    ) -> RawJudgeVerdict:
        return RawJudgeVerdict(
            material_claims=[], action_coverage=[], recommendation_mappings=[], findings=[]
        )


def _g16(text: str, section: str = "tax_implications") -> GateResult:
    bundle = ReportBundle(report_text=text, sections={section: text}, ledger=Ledger(client="c"))
    judge = _Judge()
    result, _ = _check_g16(
        judge.judge(bundle, bundle.ledger, {}, []), judge, bundle, bundle.ledger, {}
    )
    return result


MARKER_WITH_COMMA = (
    "[ADVISER TO CONFIRM #3: capital gains tax on the possible disposal, pending confirmation "
    "of the account's tax treatment]"
)


def test_a_marker_with_a_comma_in_its_text_needs_no_claim() -> None:
    assert _g16(f"The capital gains tax on the disposal is {MARKER_WITH_COMMA}.").passed


def test_two_markers_in_one_sentence_need_no_claim() -> None:
    text = f"We note {MARKER_WITH_COMMA} and {MARKER_WITH_COMMA}."
    assert _g16(text).passed


def test_a_tax_claim_beside_a_marker_still_needs_a_claim() -> None:
    text = f"You will owe capital gains tax, {MARKER_WITH_COMMA}."
    result = _g16(text)
    assert not result.passed
    assert "owe capital gains tax" in result.detail


def test_a_figure_beside_a_marker_still_needs_a_claim() -> None:
    # a comma right after a digit does not split a clause, so the figure needs its own clause
    result = _g16(f"The charge is £500 today, and {MARKER_WITH_COMMA}.", section="fees_charges")
    assert not result.passed


# --- reference matching by platform ----------------------------------------------------------


def _account(account_id: str, type_: str, platform: str, owners: list[str]) -> Account:
    return Account(id=account_id, owners=owners, type=type_, platform=platform, in_scope=True)


def _accounts() -> list[Account]:
    both = ["James Whitmore", "Caroline Whitmore"]
    return [
        _account("H-GIA", "General Investment Account", "Holloway", both),
        _account("B-GIA", "General Investment Account", "Brightwell", both),
        _account("H-ISA-J", "Stocks & Shares ISA", "Holloway", ["James Whitmore"]),
        _account("H-ISA-C", "Stocks & Shares ISA", "Holloway", ["Caroline Whitmore"]),
    ]


def test_a_platform_narrows_two_same_type_accounts_to_one() -> None:
    matches = accounts_matching_reference(
        "the Holloway joint General Investment Account", _accounts()
    )
    assert [a.id for a in matches] == ["H-GIA"]


def test_the_platform_works_with_an_abbreviated_type() -> None:
    matches = accounts_matching_reference("the Brightwell joint GIA", _accounts())
    assert [a.id for a in matches] == ["B-GIA"]


def test_without_a_platform_two_same_type_accounts_stay_ambiguous() -> None:
    matches = accounts_matching_reference("the joint General Investment Account", _accounts())
    assert {a.id for a in matches} == {"H-GIA", "B-GIA"}


def test_a_platform_that_does_not_narrow_to_one_changes_nothing() -> None:
    matches = accounts_matching_reference("the Holloway Stocks & Shares ISA", _accounts())
    assert {a.id for a in matches} == {"H-ISA-J", "H-ISA-C"}


def test_a_platform_and_an_owner_together_narrow_to_one() -> None:
    matches = accounts_matching_reference("James's Holloway Stocks & Shares ISA", _accounts())
    assert [a.id for a in matches] == ["H-ISA-J"]


def test_a_platform_name_inside_another_word_is_not_a_mention() -> None:
    accounts = _accounts()
    accounts[1] = accounts[1].model_copy(update={"platform": "Hollo"})
    matches = accounts_matching_reference("the Holloway joint General Investment Account", accounts)
    assert [a.id for a in matches] == ["H-GIA"]
