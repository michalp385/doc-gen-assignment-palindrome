"""P10: a statement row that matches several same-type accounts is narrowed by owner, and then by
the platform named in the row's own label, so two joint accounts of one type on different
platforms are told apart. Anything still ambiguous stays unmatched: never guessed."""

from __future__ import annotations

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.values import match_image_row


def _row(label: str, type_: str = "General Investment Account") -> ImageValueRow:
    return ImageValueRow(
        account_label=label, account_type=type_, amount_text="1", currency_symbol="£"
    )


def _gia(id_: str, platform: str | None, owners: list[str] | None = None) -> Account:
    return Account(
        id=id_,
        owners=owners or ["Ann Lee", "Ben Lee"],
        type="General Investment Account",
        platform=platform,
        in_scope=True,
    )


ON_NORTH = _gia("a", "Northgate")
ON_SOUTH = _gia("b", "Southgate")


def test_same_type_same_owners_on_two_platforms_is_told_apart_by_the_platform_in_the_label() -> (
    None
):
    assert (
        match_image_row(_row("Joint GIA (Ann & Ben) - Northgate"), [ON_NORTH, ON_SOUTH]) is ON_NORTH
    )
    assert (
        match_image_row(_row("Joint GIA (Ann & Ben) - Southgate"), [ON_NORTH, ON_SOUTH]) is ON_SOUTH
    )


def test_no_platform_in_the_label_stays_unmatched() -> None:
    assert match_image_row(_row("Joint GIA (Ann & Ben)"), [ON_NORTH, ON_SOUTH]) is None


def test_a_label_naming_someone_who_holds_neither_account_is_never_matched_by_platform() -> None:
    ann_north = _gia("d", "Northgate", ["Ann Lee"])
    ben_south = _gia("e", "Southgate", ["Ben Lee"])

    assert match_image_row(_row("GIA (Carol) Northgate"), [ann_north, ben_south]) is None


def test_the_platform_is_matched_as_a_whole_word() -> None:
    other = _gia("c", "North")

    assert match_image_row(_row("Joint GIA - Northgate"), [other, ON_SOUTH]) is None


def test_a_platform_that_names_both_accounts_stays_unmatched() -> None:
    twin = _gia("c", "Northgate")

    assert match_image_row(_row("Joint GIA - Northgate"), [ON_NORTH, twin]) is None


def test_owner_disambiguation_still_works_and_platform_narrows_within_it() -> None:
    ann_north = _gia("d", "Northgate", ["Ann Lee"])
    ben_north = _gia("e", "Northgate", ["Ben Lee"])

    assert match_image_row(_row("GIA (Ben)"), [ann_north, ben_north]) is ben_north
    assert (
        match_image_row(_row("GIA (Ann) Northgate"), [ann_north, ben_north, ON_SOUTH]) is ann_north
    )
