"""Open questions for the investigation agent (D14, DESIGN section 5.2), tests first.

Reconciliation opens a question only where more evidence could change the outcome under the
rules: a singular meeting mention that identifies two or more in-scope accounts. Anything the
rules already settle, or that could not change the report, opens nothing -- which also keeps a
client whose mentions all resolve from ever reaching the model.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.questions import mention_candidates, open_questions


def _account(
    account_id: str,
    type_: str,
    owner: str = "Yvonne Pascoe",
    platform: str = "Holloway",
    *,
    in_scope: bool = True,
    status: str = "open",
    is_new: bool = False,
) -> Account:
    return Account(
        id=account_id,
        type=type_,
        owners=[owner],
        platform=platform,
        in_scope=in_scope,
        status=status,  # type: ignore[arg-type]  # the test passes the literal by name
        is_new=is_new,
    )


ISA = _account("Y-ISA", "Stocks & Shares ISA")
GIA = _account("Y-GIA", "General Investment Account")
GIA_2 = _account("Y-GIA-2", "General Investment Account")


def test_a_singular_mention_naming_only_a_platform_is_ambiguous() -> None:
    [question] = open_questions(["her other account on the Holloway platform"], [ISA, GIA])
    assert question.id == "q1" and question.kind == "account_link"
    assert set(question.candidate_ids) == {"Y-ISA", "Y-GIA"}


def test_a_type_that_matches_two_accounts_is_ambiguous() -> None:
    [question] = open_questions(["one of his General Investment Accounts"], [ISA, GIA, GIA_2])
    assert set(question.candidate_ids) == {"Y-GIA", "Y-GIA-2"}


def test_a_bare_type_acronym_narrows_the_candidates() -> None:
    """ "Ann's ISA" names her ISA, so the GIA is never a candidate (and there is no question)."""
    assert [a.id for a in mention_candidates("Yvonne's ISA", [ISA, GIA])] == ["Y-ISA"]
    assert open_questions(["Yvonne's ISA"], [ISA, GIA]) == []
    assert [a.id for a in mention_candidates("the ISA on Holloway", [ISA, GIA])] == ["Y-ISA"]


def test_a_specific_type_phrase_beats_a_bare_acronym() -> None:
    """ "her Cash ISA" names the Cash ISA; the shared acronym must not widen it to every ISA."""
    cash_isa = _account("Y-CASH-ISA", "Cash ISA", platform="Aviva")
    accounts = [cash_isa, ISA]
    assert [a.id for a in mention_candidates("her Cash ISA", accounts)] == ["Y-CASH-ISA"]
    assert open_questions(["the Aviva ISA", "her Cash ISA"], accounts) == []


def test_a_repeated_mention_opens_one_question() -> None:
    questions = open_questions(
        ["her account on Holloway", "Her account on Holloway ", "her account on Holloway"],
        [ISA, GIA],
    )
    assert [q.id for q in questions] == ["q1"]


def test_the_question_records_which_candidates_are_in_scope() -> None:
    out = _account("Y-OLD", "Cash Account", in_scope=False)
    [question] = open_questions(["her account on the Holloway platform"], [ISA, GIA, out])
    assert set(question.candidate_ids) == {"Y-ISA", "Y-GIA", "Y-OLD"}
    assert set(question.in_scope_ids) == {"Y-ISA", "Y-GIA"}


def test_a_mention_that_identifies_one_account_opens_nothing() -> None:
    assert open_questions(["her Stocks & Shares ISA"], [ISA, GIA]) == []


def test_a_plural_or_all_reference_opens_nothing() -> None:
    accounts = [ISA, _account("B-ISA", "Stocks & Shares ISA", owner="Bob Pascoe")]
    for mention in ("both ISAs", "their ISAs", "Yvonne's and Bob's Stocks & Shares ISAs"):
        assert open_questions([mention], accounts) == [], mention


def test_a_counted_reference_to_the_accounts_opens_nothing() -> None:
    accounts = [GIA, GIA_2, ISA]
    for mention in ("his two General Investment Accounts on Holloway", "several accounts there"):
        assert open_questions([mention], accounts) == [], mention


def test_a_mention_naming_nothing_opens_nothing() -> None:
    assert open_questions(["existing portfolio", "bridging loan"], [ISA, GIA]) == []


def test_only_one_in_scope_candidate_opens_nothing() -> None:
    out = _account("Y-OLD", "Cash Account", in_scope=False)
    out_2 = _account("Y-OLD-2", "Cash Account", in_scope=False)
    assert open_questions(["her cash account on Holloway"], [ISA, out, out_2]) == []
    assert open_questions(["an old account on Holloway"], [ISA, out]) == []


def test_closed_and_new_accounts_are_never_candidates() -> None:
    closed = _account("Y-CLOSED", "General Investment Account", status="closed")
    new = _account("new:x", "New joint account", is_new=True)
    assert [
        a.id for a in mention_candidates("her account on Holloway", [ISA, GIA, closed, new])
    ] == [
        "Y-ISA",
        "Y-GIA",
    ]


def test_an_account_pinned_down_by_another_mention_is_recorded_as_claimed() -> None:
    mentions = ["her Stocks & Shares ISA", "her other account on the Holloway platform"]
    [question] = open_questions(mentions, [ISA, GIA])
    assert question.claimed_ids == ("Y-ISA",)


def test_joint_accounts_seen_twice_count_once() -> None:
    joint = _account("J-GIA", "General Investment Account")
    assert open_questions(["the joint GIA on Holloway"], [joint, joint]) == []


def test_question_ids_follow_the_order_of_mention() -> None:
    questions = open_questions(
        ["one of his accounts on Holloway", "another account on the Holloway platform"],
        [ISA, GIA],
    )
    assert [q.id for q in questions] == ["q1", "q2"]
