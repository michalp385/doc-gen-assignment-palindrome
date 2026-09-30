"""R3: which dated value wins for an account.

The most recent dated candidate wins, among the account data and any meeting figure the
meeting record says was actually viewed during the meeting -- a recalled or paperwork
figure, or a statement-image value, never selects (verify_label's conservative default,
T5, already keeps those out of `viewed_observations`). `superseded_values` (T19, client
02's joint GIA: a later live-viewed figure beats the snapshot) shares `select_values`'
own candidate-building and returns everything that wasn't picked, for the account table's
footnote and the review sheet's superseded-value item; wiring those in is
reconciliation's caller's job (`pipeline.py`).

P10 (T18): a statement image never reaches `select_values` at all -- `match_image_row` and
`check_image_row` below run afterward, against the value `select_values` already chose, and
can only confirm it (no review item) or raise a review item. Never a candidate, never a
selection.
"""

from __future__ import annotations

import re
from datetime import date as _date
from decimal import Decimal

from agent_pipeline.extract.image import ImageValueRow
from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.ledger import Account, Value, render_table
from agent_pipeline.reconcile.review import ReviewItemInput

# A record with no stated currency is not treated as sterling (P12, DESIGN.md section 3.3):
# its value is withheld and marked downstream (`account_state.py`), never rendered as GBP.
UNKNOWN_CURRENCY = "UNKNOWN"


def is_stated_gbp(currency: str | None) -> bool:
    """Whether the account data states sterling (case-insensitively). Anything else, a missing
    or blank currency included, is not-GBP (P12)."""
    return currency is not None and currency.strip().upper() == "GBP"


def _candidates(
    db_value: Decimal | None,
    db_date: _date | None,
    currency: str | None,
    viewed_observations: list[Value],
) -> list[Value]:
    candidates: list[Value] = []
    if db_value is not None:
        candidates.append(
            Value(
                amount=db_value,
                currency=currency.strip().upper()
                if currency and currency.strip()
                else UNKNOWN_CURRENCY,
                precision="exact",
                qualifier="exact",
                date=db_date,
                source_id="client_data_db.json",
                quote="",
                selected_by="R3",
            )
        )
    candidates.extend(viewed_observations)
    return candidates


def record_candidate(
    value: Decimal | None, day: _date | None, currency: str | None
) -> Value | None:
    """A joint-account copy's own figure as a candidate, for R9: the same shape as the account
    data's figure in `_candidates`, so two copies compete under R3 like any two dated figures."""
    candidates = _candidates(value, day, currency, [])
    return candidates[0] if candidates else None


def _latest(candidates: list[Value]) -> list[Value]:
    """The candidates sharing the latest date (an undated one is the earliest of all)."""
    latest = max(v.date or _date.min for v in candidates)
    return [v for v in candidates if (v.date or _date.min) == latest]


def tied_candidates(
    db_value: Decimal | None,
    db_date: _date | None,
    currency: str | None,
    viewed_observations: list[Value],
) -> list[Value]:
    """R3's same-date tie: the candidates sharing the latest date when they do not agree on the
    amount and currency ("the most recent dated figure wins" has no answer between them).
    Following R9 (same-date, different-value joint copies are unresolved), a tie selects
    nothing: the value cell is a marker and the review sheet gets a conflict, never a silent
    pick. Candidates that agree are not a tie. Empty when there is no tie."""
    candidates = _candidates(db_value, db_date, currency, viewed_observations)
    if not candidates:
        return []
    at_latest = _latest(candidates)
    if len({(v.amount, v.currency) for v in at_latest}) > 1:
        return at_latest
    return []


def select_values(
    db_value: Decimal | None,
    db_date: _date | None,
    currency: str | None,
    viewed_observations: list[Value],
) -> Value | None:
    """R3: the most recent dated candidate. `None` when there is none, and also on a same-date
    tie that disagrees (`tied_candidates`): unresolved, never a silent pick. Candidates on the
    latest date that agree on the amount are one answer; the exact one is used."""
    candidates = _candidates(db_value, db_date, currency, viewed_observations)
    if not candidates:
        return None
    if tied_candidates(db_value, db_date, currency, viewed_observations):
        return None
    at_latest = _latest(candidates)
    return next((v for v in at_latest if v.precision == "exact"), at_latest[0])


def superseded_values(
    db_value: Decimal | None,
    db_date: _date | None,
    currency: str | None,
    viewed_observations: list[Value],
    selected: Value | None,
) -> list[Value]:
    """R3, R6: every candidate `select_values` didn't pick -- the account table's footnote
    (P9, `write/table.py`) and the review sheet's superseded-value item are built from
    this, never from re-deriving "the other one" ad hoc at the call site. `selected` is
    matched by identity-equivalent fields (amount, date, source_id), not object identity,
    so a caller that reselects the same winning candidate (as `select_values` itself does)
    still excludes exactly one match, not zero."""
    if selected is None:
        return []
    candidates = _candidates(db_value, db_date, currency, viewed_observations)
    superseded: list[Value] = []
    already_excluded = False
    for candidate in candidates:
        if (
            not already_excluded
            and candidate.amount == selected.amount
            and candidate.date == selected.date
            and candidate.source_id == selected.source_id
        ):
            already_excluded = True
            continue
        superseded.append(candidate)
    return superseded


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
    finding #8); client 02's two same-type ISAs are that client (T18). A whole-word match,
    not a raw substring: an owner's first name is checked against the label's own words, so
    a short name (e.g. "Ann") can't spuriously match inside an unrelated longer word (e.g.
    "Channel") the way a plain `in` check would (verifier checkpoint, T18). Two same-type
    accounts with the same owners on different platforms are told apart by the platform the
    label names, as a whole word. Anything that still isn't exactly one match stays
    unresolved, never guessed."""
    same_type = [a for a in accounts if a.type.lower() == row.account_type.lower()]
    if len(same_type) == 1:
        return same_type[0]
    if len(same_type) > 1:
        label = row.account_label.lower()
        label_words = set(re.findall(r"[a-z']+", label))
        by_owner = [
            a
            for a in same_type
            if any(owner.split()[0].lower() in label_words for owner in a.owners)
        ]
        if len(by_owner) == 1:
            return by_owner[0]
        # Two or more accounts of one type share the owners the label names (the same holders on
        # different platforms): the platform the row's own label names decides, as a whole word
        # or phrase. A label that names nobody, or a holder we do not have, is never narrowed by
        # platform alone -- that would pick an account for a person who does not hold it.
        by_platform = [
            a
            for a in by_owner
            if a.platform and re.search(rf"\b{re.escape(a.platform.lower())}\b", label)
        ]
        if len(by_owner) >= 2 and len(by_platform) == 1:
            # Every holder the label names must hold the account the platform picked: a joint
            # row is never given to a sole account that shares one holder with it.
            named = {
                owner.split()[0].lower()
                for a in same_type
                for owner in a.owners
                if owner.split()[0].lower() in label_words
            }
            held = {owner.split()[0].lower() for owner in by_platform[0].owners}
            if named <= held:
                return by_platform[0]
    return None


def _full_date(day: _date) -> str:
    return f"{day.day} {day:%B} {day.year}"


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
    # parse_amount needs a currency symbol or code to recognise an amount at all -- the
    # model reports the symbol separately (currency_symbol), not folded into amount_text
    # (confirmed against the real vision model, T18 live check: it prints the digits alone),
    # so it's put back before parsing rather than trusting amount_text alone, or every real
    # read would silently fail to parse and never flag a genuine disagreement.
    # A currency code ("GBP") needs a separating space to parse; a symbol does not mind one.
    shown = (
        f"{row.currency_symbol} {row.amount_text}"
        if row.currency_symbol.isalpha()
        else f"{row.currency_symbol}{row.amount_text}"
    )
    parsed = parse_amount(shown)
    if parsed is None or parsed.amount == selected.amount:
        return None
    detail = (
        f"statement image shows {row.amount_text!r} for {row.account_label!r}; "
        f"selected value is {selected.amount}"
    )
    if row.currency_symbol.isalpha():
        # A row that prints a currency code was never flagged before (it did not parse), so
        # its item is new and names both figures and the statement date. A symbol row keeps
        # the wording clients already carry in their committed ledgers.
        selected_when = f", dated {_full_date(selected.date)}" if selected.date is not None else ""
        detail += (
            f". The statement gives {shown}, valued on {row.valued_on_text}; the selected value "
            f"is {render_table(selected)}{selected_when}. Images never select a value (P10)."
        )
    return ReviewItemInput(kind="image_discrepancy", blocking=False, detail=detail, refs=[])
