"""Two in-scope accounts that would get the same label ("Bernard's General Investment Account"
twice) are described once, with their count ("Bernard's two General Investment Accounts"). Listing
the same phrase twice let the scope writer collapse it to one account, and the Introduction then
under-counted the client's accounts. Descriptions with no repeated label are unchanged, so no other
client's writer input moves."""

from __future__ import annotations

from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.write.plan import _describe_scope


def _acct(id_: str, type_: str, owners: list[str], platform: str | None = "Holloway") -> Account:
    return Account(id=id_, type=type_, owners=owners, platform=platform, in_scope=True)


def test_two_accounts_with_the_same_owner_and_type_are_counted() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _acct("g1", "General Investment Account", ["Bernard Otieno"]),
            _acct("g2", "General Investment Account", ["Bernard Otieno"]),
            _acct("i1", "Stocks & Shares ISA", ["Bernard Otieno"]),
        ],
    )

    text = _describe_scope(ledger)

    assert "Bernard's two General Investment Accounts" in text
    assert text.count("General Investment Account") == 1  # once, as a counted plural
    assert "your Stocks & Shares ISA" in text
    assert text.endswith("held with Holloway")


def test_two_joint_accounts_of_one_type_are_counted_too() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _acct("g1", "General Investment Account", ["Ann Lee", "Ben Lee"]),
            _acct("g2", "General Investment Account", ["Ann Lee", "Ben Lee"]),
        ],
    )

    assert _describe_scope(ledger) == "your two General Investment Accounts held with Holloway"


def test_distinct_labels_are_described_exactly_as_before() -> None:
    ledger = Ledger(
        client="c",
        accounts=[
            _acct("i1", "Stocks & Shares ISA", ["Robert Fletcher"]),
            _acct("i2", "Stocks & Shares ISA", ["Jean Fletcher"]),
        ],
    )

    assert _describe_scope(ledger) == (
        "Robert's Stocks & Shares ISA and Jean's Stocks & Shares ISA, held with Holloway"
    )


def test_a_single_account_is_described_exactly_as_before() -> None:
    ledger = Ledger(client="c", accounts=[_acct("i1", "Stocks & Shares ISA", ["Margaret Hughes"])])

    assert _describe_scope(ledger) == "your Stocks & Shares ISA held with Holloway"
