"""P10, platform step, with owner names in the label so the platform logic is what decides.

The earlier platform tests use labels that name nobody, so the owner step leaves nothing and they
return None whatever the platform logic does; these cannot pass by accident."""

from __future__ import annotations

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.values import match_image_row


def _row(label: str) -> ImageValueRow:
    return ImageValueRow(
        account_label=label,
        account_type="General Investment Account",
        amount_text="1",
        currency_symbol="£",
    )


def _gia(id_: str, platform: str | None, owners: list[str] | None = None) -> Account:
    return Account(
        id=id_,
        owners=owners or ["Ann Lee", "Ben Lee"],
        type="General Investment Account",
        platform=platform,
        in_scope=True,
    )


def test_the_platform_is_matched_as_a_whole_word_when_the_label_names_the_holders() -> None:
    short = _gia("c", "North")
    south = _gia("b", "Southgate")

    # Both accounts pass the owner step; a substring match would pick `short` ("North" inside
    # "Northgate").
    assert match_image_row(_row("Joint GIA (Ann & Ben) - Northgate"), [short, south]) is None


def test_two_accounts_on_the_named_platform_stay_unmatched_when_the_label_names_the_holders() -> (
    None
):
    first = _gia("a", "Northgate")
    twin = _gia("c", "Northgate")

    assert match_image_row(_row("Joint GIA (Ann & Ben) - Northgate"), [first, twin]) is None


def test_a_sole_account_is_never_picked_for_a_label_that_names_another_holder() -> None:
    ann_sole_north = _gia("d", "Northgate", ["Ann Lee"])
    joint_south = _gia("e", "Southgate")

    # Ben is named in the label and does not hold Ann's account: the platform alone used to pick
    # Ann's sole account for a joint row.
    assert (
        match_image_row(_row("Joint GIA (Ann & Ben) - Northgate"), [ann_sole_north, joint_south])
        is None
    )


def test_a_platform_still_picks_the_joint_account_that_every_named_holder_holds() -> None:
    joint_north = _gia("a", "Northgate")
    joint_south = _gia("b", "Southgate")

    assert (
        match_image_row(_row("Joint GIA (Ann & Ben) - Northgate"), [joint_north, joint_south])
        is joint_north
    )
