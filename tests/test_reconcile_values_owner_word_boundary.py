"""T18 verifier checkpoint: `match_image_row`'s owner-name disambiguation must match a whole
word, not a raw substring -- a short owner name (e.g. "Ann") must not spuriously match inside
an unrelated longer word in the image's account-label text (e.g. "Channel"). Split from
`tests/test_reconcile_values_p10.py` (already committed) rather than editing it."""

from __future__ import annotations

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.ledger import Account
from agent_pipeline.reconcile.values import match_image_row


def _account(account_id: str, owners: list[str], account_type: str) -> Account:
    return Account(id=account_id, owners=owners, type=account_type, in_scope=True)


def _row(account_label: str, account_type: str = "Stocks & Shares ISA") -> ImageValueRow:
    return ImageValueRow(
        account_label=account_label,
        account_type=account_type,
        amount_text="£45,000",
        currency_symbol="£",
    )


def test_a_short_owner_name_does_not_match_as_a_substring_of_an_unrelated_word() -> None:
    ann = _account("A-1", ["Ann Baker"], "Stocks & Shares ISA")
    other = _account("A-2", ["Rowan Fitch"], "Stocks & Shares ISA")
    # "Ann" is a substring of "Channel", but the two share no actual word.
    row = _row("Holloway ISA (Channel provider statement)")

    assert match_image_row(row, [ann, other]) is None


def test_a_short_owner_name_still_matches_as_its_own_word() -> None:
    ann = _account("A-1", ["Ann Baker"], "Stocks & Shares ISA")
    other = _account("A-2", ["Rowan Fitch"], "Stocks & Shares ISA")
    row = _row("Holloway ISA (Ann)")

    assert match_image_row(row, [ann, other]) is ann
