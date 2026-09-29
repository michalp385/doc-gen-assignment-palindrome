"""The G7 proceeds carve-out is narrow (tests first; verifier findings on ea7d295).

A finding is dropped only for the writer prompt's fixed form: "... using the [gross] proceeds
of <the ledger's proceeds figure> to <what to do>", directly followed by the P5 timing caveat.
It is kept when the same sentence also names another figure or contingent money, when the
figure only prefixes a longer number, and when any copy of the quoted text lacks the caveat.
"""

from __future__ import annotations

from decimal import Decimal

from agent_pipeline.gates.judge import is_permitted_proceeds_sentence
from agent_pipeline.ledger import Fact, Ledger, Value

CAVEAT = "This figure is gross before any CGT and becomes available once the disposal completes."
GOOD = "We recommend using the gross proceeds of £5,000 to fund the ISA."


def _ledger() -> Ledger:
    value = Value(
        amount=Decimal("5000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=None,
        source_id="m",
        quote="£5,000",
        selected_by="R3",
    )
    return Ledger(
        client="c",
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


def _permitted(sentence: str, report: str | None = None) -> bool:
    return is_permitted_proceeds_sentence(sentence, report or f"{sentence} {CAVEAT}", _ledger())


def test_the_fixed_form_is_permitted() -> None:
    assert _permitted(GOOD)


def test_another_figure_in_the_same_sentence_is_not_permitted() -> None:
    sentence = "We recommend using the proceeds of £5,000 together with a bonus of £40,000."
    assert not _permitted(sentence)


def test_contingent_money_named_without_a_figure_is_not_permitted() -> None:
    sentence = "We recommend using the proceeds of £5,000 and the expected inheritance to fund it."
    assert not _permitted(sentence)


def test_a_sentence_that_is_not_the_fixed_form_is_not_permitted() -> None:
    assert not _permitted("Your proceeds of £5,000 are already available to invest today.")


def test_a_figure_that_only_prefixes_a_longer_number_is_not_permitted() -> None:
    assert not _permitted("We recommend using the gross proceeds of £5,000,000 to fund the ISA.")
    assert not _permitted("We recommend using the gross proceeds of £5,000.50 to fund the ISA.")


def test_every_copy_of_the_quoted_text_must_be_followed_by_the_caveat() -> None:
    report = f"{GOOD} {CAVEAT}\n\nLater we repeat: {GOOD} That is all."
    assert not _permitted(GOOD, report)


def test_a_repeated_copy_each_followed_by_the_caveat_is_permitted() -> None:
    report = f"{GOOD} {CAVEAT}\n\n{GOOD} {CAVEAT}"
    assert _permitted(GOOD, report)
