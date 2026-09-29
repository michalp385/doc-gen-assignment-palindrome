"""Three small consequences of the hand-written run (tests first; cases 08, 12, 18).

- P12: the currency item names the currency in words ("EUR (euros)") as well as its code, so the
  adviser reads it without a lookup. General vocabulary in `config/currency_names.json`.
- An action whose amount was dropped for an R5 conflict is already covered by that conflict's
  marker; it must not also get an "amount not stated" marker.
- A missing-platform charges marker does not name the account type: the fees writer would repeat
  it, and a sentence naming the client's account needs a source claim the fees slot has none for.
"""

from __future__ import annotations

from agent_pipeline.ledger import Account, Action
from agent_pipeline.reconcile.account_state import check_account_states
from agent_pipeline.reconcile.markers import required_markers
from agent_pipeline.reconcile.unspecified_amounts import build_unspecified_amounts


def test_the_currency_item_names_the_currency_in_words() -> None:
    account = Account(
        id="U-GIA",
        type="General Investment Account",
        owners=["A B"],
        platform="Holloway",
        in_scope=True,
    )
    from decimal import Decimal

    from agent_pipeline.ledger import Value

    account = account.model_copy(
        update={
            "value": Value(
                amount=Decimal("1"),
                currency="EUR",
                precision="exact",
                qualifier="exact",
                date=None,
                source_id="db",
                quote="",
                selected_by="R3",
            )
        }
    )
    [item] = check_account_states([account], {"U-GIA": "EUR"})["U-GIA"].review_items
    assert item.kind == "currency" and "EUR (euros)" in item.detail


def test_an_unknown_currency_code_is_shown_as_the_code_alone() -> None:
    account = Account(id="X", type="Cash Account", owners=["A B"], platform="P", in_scope=True)
    from decimal import Decimal

    from agent_pipeline.ledger import Value

    account = account.model_copy(
        update={
            "value": Value(
                amount=Decimal("1"),
                currency="ZZZ",
                precision="exact",
                qualifier="exact",
                date=None,
                source_id="db",
                quote="",
                selected_by="R3",
            )
        }
    )
    [item] = check_account_states([account], {"X": "ZZZ"})["X"].review_items
    assert "ZZZ" in item.detail and "(" not in item.detail.split("ZZZ", 1)[1].split(",")[0]


def test_a_conflicted_action_gets_no_unspecified_amount_marker() -> None:
    isa = Account(id="I", type="Stocks & Shares ISA", owners=["A B"], platform="P", in_scope=True)
    action = Action(
        id="a1",
        description="move money into the ISA",
        kind="action",
        accounts=["Stocks & Shares ISA"],
        quote="move money into the ISA",
    )
    common: dict = dict(
        partial_disposals=[],
        disposal_quotes=[],
        other_unspecified=0,
        taken_keys=set(),
        available=None,
    )
    assert [m.key for m in build_unspecified_amounts([action], {}, [isa], **common).markers] == [
        "isa_amounts"
    ]
    skipped = build_unspecified_amounts(
        [action], {}, [isa], skip_action_ids={"a1"}, **{**common, "taken_keys": set()}
    )
    assert skipped.markers == []


def test_the_missing_platform_marker_does_not_name_the_account_type() -> None:
    [marker, _advice] = required_markers(set(), no_platform_types=["Stocks & Shares ISA"])
    assert marker.key == "platform_charge_unknown_platform"
    assert "not stated" in marker.text and "ISA" not in marker.text
