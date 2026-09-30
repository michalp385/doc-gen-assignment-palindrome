"""The Introduction must not name an account type in the singular when the report covers more than
one account of it. The existing scope check only asked whether every in-scope type is named, so "the
General Investment Account held by Bernard" passed for a client with two. The writer repairs it
before the release judge ever sees it."""

from __future__ import annotations

from agent_pipeline.config import Placeholder, Section
from agent_pipeline.gates.judge import intro_scope_problems
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.write.schemas import SectionPlan
from agent_pipeline.write.writer import RawSlotDraft, write_slot


def _acct(id_: str, type_: str, owner: str = "Bernard Otieno") -> Account:
    return Account(id=id_, type=type_, owners=[owner], platform="Holloway", in_scope=True)


TWO_GIAS = Ledger(
    client="c",
    accounts=[
        _acct("g1", "General Investment Account"),
        _acct("g2", "General Investment Account"),
        _acct("i1", "Stocks & Shares ISA"),
    ],
)


def test_one_singular_mention_does_not_cover_two_accounts_of_the_type() -> None:
    problems = intro_scope_problems(
        "the General Investment Account held by Bernard and your Stocks & Shares ISA", TWO_GIAS
    )

    assert len(problems) == 1
    assert "General Investment Account" in problems[0] and "2" in problems[0]


def test_a_plural_covers_every_account_of_the_type() -> None:
    assert (
        intro_scope_problems(
            "your two General Investment Accounts and your Stocks & Shares ISA", TWO_GIAS
        )
        == []
    )


def test_one_mention_per_account_covers_them() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _acct("i1", "Stocks & Shares ISA", "Robert Fletcher"),
            _acct("i2", "Stocks & Shares ISA", "Jean Fletcher"),
        ],
    )

    text = "Robert's Stocks & Shares ISA held with Holloway and Jean's Stocks & Shares ISA"
    assert intro_scope_problems(text, ledger) == []


def test_a_single_account_named_once_is_fine() -> None:
    ledger = Ledger(client="c", accounts=[_acct("i1", "Stocks & Shares ISA")])

    assert intro_scope_problems("your Stocks & Shares ISA", ledger) == []


SECTION = Section(
    id="introduction",
    title="Introduction",
    use_if="always",
    template="We are writing about <<scope>>.",
    placeholders={"scope": Placeholder(kind="generated", prompt="Say which accounts.")},
)


class Scripted:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.corrections: list[list[str]] = []

    def write(self, plan: SectionPlan, corrections: list[str]) -> RawSlotDraft:
        self.corrections.append(list(corrections))
        index = min(len(self.corrections) - 1, len(self._responses) - 1)
        return RawSlotDraft(paragraphs=[self._responses[index]])


def test_the_writer_repairs_a_singular_introduction_for_two_accounts() -> None:
    model = Scripted(
        [
            "the General Investment Account held by Bernard and your Stocks & Shares ISA",
            "your two General Investment Accounts and your Stocks & Shares ISA",
        ]
    )

    draft = write_slot(
        SectionPlan(section_id="introduction"), SECTION, TWO_GIAS, model, guidance_text=""
    )

    assert draft.repairs_used == 1
    assert "two General Investment Accounts" in draft.filled_text
    assert "General Investment Account" in model.corrections[1][0]
