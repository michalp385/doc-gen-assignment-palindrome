"""T18, P10: statement-image observations never select a value, only confirm or conflict.
`match_image_row` (owner-name disambiguation for same-type accounts) and `check_image_row`
(currency mismatch always flagged; a value/date disagreement flagged; a confirming row
silent) -- and `extract_image` degrading to `readable=False` on a refusal, never crashing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from agent_pipeline.extract.image import (
    ImageExtraction,
    ImageValueRow,
    RawImageProposal,
    extract_image,
)
from agent_pipeline.ledger import Account, Value
from agent_pipeline.llm import EmptyOutputError
from agent_pipeline.reconcile.values import check_image_row, match_image_row
from agent_pipeline.sources.adapters.image import ImageSource

_IMAGE = ImageSource(path=Path("data/x/statement_summary.png"), content=b"fake-bytes")


def _account(account_id: str, owners: list[str], account_type: str) -> Account:
    return Account(id=account_id, owners=owners, type=account_type, in_scope=True)


def _row(
    account_label: str = "an account",
    account_type: str = "Stocks & Shares ISA",
    amount_text: str = "£45,000",
    currency_symbol: str = "£",
) -> ImageValueRow:
    return ImageValueRow(
        account_label=account_label,
        account_type=account_type,
        amount_text=amount_text,
        currency_symbol=currency_symbol,
        valued_on_text="30 Apr 2026",
    )


def _value(amount: str, currency: str = "GBP") -> Value:
    return Value(
        amount=Decimal(amount),
        currency=currency,
        precision="exact",
        qualifier="exact",
        date=date(2026, 4, 30),
        source_id="client_data_db.json",
        quote="",
        selected_by="R3",
    )


# --- match_image_row: owner-name disambiguation ------------------------------------------


def test_a_single_matching_type_resolves_without_needing_an_owner_hint() -> None:
    account = _account("A-1", ["Jordan Reed"], "General Investment Account")
    row = _row(account_label="an account", account_type="General Investment Account")

    assert match_image_row(row, [account]) is account


def test_two_same_type_accounts_are_disambiguated_by_owner_name_in_the_label() -> None:
    first = _account("A-1", ["Jordan Reed"], "Stocks & Shares ISA")
    second = _account("A-2", ["Casey Lane"], "Stocks & Shares ISA")
    row = _row(account_label="Platform ISA (Jordan)", account_type="Stocks & Shares ISA")

    assert match_image_row(row, [first, second]) is first


def test_two_same_type_accounts_with_no_owner_hint_stay_unresolved() -> None:
    first = _account("A-1", ["Jordan Reed"], "Stocks & Shares ISA")
    second = _account("A-2", ["Casey Lane"], "Stocks & Shares ISA")
    row = _row(account_label="an account", account_type="Stocks & Shares ISA")

    assert match_image_row(row, [first, second]) is None


def test_a_type_with_no_matching_account_stays_unresolved() -> None:
    account = _account("A-1", ["Jordan Reed"], "Cash Account")
    row = _row(account_type="Offshore Investment Bond")

    assert match_image_row(row, [account]) is None


def test_type_matching_is_exact_not_substring() -> None:
    # "ISA" alone must not match "Stocks & Shares ISA" -- the image's Type column is a
    # structured field, not free prose, so exact equality is the safer rule here.
    account = _account("A-1", ["Jordan Reed"], "Stocks & Shares ISA")
    row = _row(account_type="ISA")

    assert match_image_row(row, [account]) is None


# --- check_image_row: currency mismatch always flagged, takes priority -------------------


def test_currency_mismatch_is_flagged_as_a_possible_read_error_when_the_account_is_gbp() -> None:
    result = check_image_row(_value("45000"), _row(currency_symbol="$"), account_currency="GBP")

    assert result is not None
    assert result.kind == "currency"
    assert "possible read error" in result.detail


def test_currency_mismatch_against_a_non_gbp_account_has_no_read_error_wording() -> None:
    result = check_image_row(_value("45000", "EUR"), _row(currency_symbol="$"), "EUR")

    assert result is not None
    assert result.kind == "currency"
    assert "possible read error" not in result.detail


def test_currency_match_does_not_flag_currency() -> None:
    result = check_image_row(_value("45000"), _row(currency_symbol="£"), "GBP")

    assert result is None or result.kind != "currency"


def test_currency_check_is_skipped_when_the_account_currency_is_unknown() -> None:
    # A missing account currency already carries its own P12 marker elsewhere; the image
    # side doesn't pile on a second, redundant currency note.
    result = check_image_row(_value("45000"), _row(currency_symbol="$"), account_currency=None)

    assert result is None


def test_currency_mismatch_takes_priority_over_an_amount_disagreement() -> None:
    # Comparing raw figures across two different, unreconciled currencies isn't meaningful.
    result = check_image_row(
        _value("45000"), _row(amount_text="£99,000", currency_symbol="$"), "GBP"
    )

    assert result is not None
    assert result.kind == "currency"


# --- check_image_row: value/date confirmation vs disagreement ----------------------------


def test_a_confirming_row_produces_no_review_item() -> None:
    result = check_image_row(_value("45000"), _row(amount_text="£45,000"), "GBP")

    assert result is None


def test_a_disagreeing_amount_is_flagged_as_an_image_discrepancy() -> None:
    result = check_image_row(_value("45000"), _row(amount_text="£99,000"), "GBP")

    assert result is not None
    assert result.kind == "image_discrepancy"


def test_no_selected_value_means_nothing_to_confirm_or_conflict_with() -> None:
    result = check_image_row(None, _row(), "GBP")

    assert result is None


def test_an_unparseable_amount_never_selects_and_never_crashes() -> None:
    result = check_image_row(_value("45000"), _row(amount_text="illegible"), "GBP")

    assert result is None


# --- extract_image: degrades on a refusal, never crashes ---------------------------------


class _RefusingModel:
    def propose(self, image: ImageSource) -> RawImageProposal:
        raise EmptyOutputError("refused")


class _ScriptedModel:
    def __init__(self, rows: list[ImageValueRow]) -> None:
        self._rows = rows

    def propose(self, image: ImageSource) -> RawImageProposal:
        return RawImageProposal(rows=self._rows)


def test_extract_image_degrades_to_unreadable_on_a_refusal_not_a_crash() -> None:
    result = extract_image(_IMAGE, model=_RefusingModel())

    assert isinstance(result, ImageExtraction)
    assert result.readable is False
    assert result.rows == []


def test_extract_image_returns_the_models_rows_on_success() -> None:
    rows = [_row()]
    result = extract_image(_IMAGE, model=_ScriptedModel(rows))

    assert result.readable is True
    assert result.rows == rows
