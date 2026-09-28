"""R3: which dated value wins for an account.

The most recent dated candidate wins, among the account data and any meeting figure the
meeting record says was actually viewed during the meeting -- a recalled or paperwork
figure, or a statement-image value, never selects (verify_label's conservative default,
T5, already keeps those out of `viewed_observations`). The superseded value and both
dates go to the review sheet; that assembly step lives with reconciliation's caller in M2,
once there is more than one candidate to choose between (client 01 never has one).

P10 (T18): a statement image never reaches `select_values` at all -- `match_image_row` and
`check_image_row` below run afterward, against the value `select_values` already chose, and
can only confirm it (no review item) or raise a review item. Never a candidate, never a
selection.
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.ledger import Account, Value
from agent_pipeline.reconcile.review import ReviewItemInput


def select_values(
    db_value: Decimal | None,
    db_date: _date | None,
    currency: str | None,
    viewed_observations: list[Value],
) -> Value | None:
    candidates: list[Value] = []
    if db_value is not None:
        candidates.append(
            Value(
                amount=db_value,
                currency=currency or "GBP",
                precision="exact",
                qualifier="exact",
                date=db_date,
                source_id="client_data_db.json",
                quote="",
                selected_by="R3",
            )
        )
    candidates.extend(viewed_observations)
    if not candidates:
        return None
    return max(candidates, key=lambda v: v.date or _date.min)


# The symbol -> currency-code direction of parsing.py's own map, kept local rather than
# imported from that module's private `_CURRENCY_SYMBOLS`: this check only ever needs the
# reverse lookup, and duplicating three entries is cheaper than exposing a private constant
# across a module boundary for one caller.
_SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def match_image_row(row: ImageValueRow, accounts: list[Account]) -> Account | None:
    """P10: matches a statement row to exactly one account, by exact wrapper-type equality
    (the image's "Type" column is the same canonical wording `config/account_types.json`
    uses, not free prose, so exact equality is safe here -- unlike `resolve_scope`'s
    substring matching over natural-language phrases). Two accounts sharing a type (e.g. two
    individual ISAs) are disambiguated by whether an owner's name appears in the row's own
    "Account" label (which always names the owner in parens on the current clients) -- the
    gap `reconcile/scope.py` documents
    as deliberately deferred until a client needed it (verifier report, T8 checkpoint,
    finding #8); client 02's two same-type ISAs are that client (T18). Anything that still
    isn't exactly one match stays unresolved, never guessed."""
    same_type = [a for a in accounts if a.type.lower() == row.account_type.lower()]
    if len(same_type) == 1:
        return same_type[0]
    if len(same_type) > 1:
        by_owner = [
            a
            for a in same_type
            if any(owner.split()[0].lower() in row.account_label.lower() for owner in a.owners)
        ]
        if len(by_owner) == 1:
            return by_owner[0]
    return None


def check_image_row(
    selected: Value | None,
    row: ImageValueRow,
    account_currency: str | None,
) -> ReviewItemInput | None:
    """P10: an already-matched row against the value `select_values` already chose for that
    account. A currency-symbol mismatch is never dismissed and takes priority over comparing
    the amount at all -- comparing figures across two different, unreconciled currencies
    isn't meaningful (SCOPING.md P10/P12). Silent (`None`) when the image simply confirms
    the selected value, matching the current clients' own expected effect: none."""
    if account_currency is not None:
        currency_code = _SYMBOL_TO_CURRENCY.get(row.currency_symbol)
        if currency_code is not None and currency_code != account_currency:
            read_error = " (possible read error)" if account_currency == "GBP" else ""
            return ReviewItemInput(
                kind="currency",
                blocking=False,
                detail=(
                    f"statement image shows {row.currency_symbol!r} for "
                    f"{row.account_label!r}; account data is in {account_currency}{read_error}"
                ),
                refs=[],
            )

    if selected is None:
        return None
    parsed = parse_amount(row.amount_text)
    if parsed is None or parsed.amount == selected.amount:
        return None
    return ReviewItemInput(
        kind="image_discrepancy",
        blocking=False,
        detail=(
            f"statement image shows {row.amount_text!r} for {row.account_label!r}; "
            f"selected value is {selected.amount}"
        ),
        refs=[],
    )
