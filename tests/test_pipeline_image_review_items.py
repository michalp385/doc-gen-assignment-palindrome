"""T18 verifier checkpoint: `pipeline._image_review_items` itself (the wiring around
`match_image_row`/`check_image_row`) had zero direct coverage -- exactly where the P4
feature's in-scope bug happened (ad234e1) before it was caught. Covers: matching is scoped
to in-scope accounts only, and the currency check uses the account data's own raw, possibly-
missing currency, not `select_values`'s GBP-defaulted one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from agent_pipeline.extract.image import ImageValueRow, RawImageProposal
from agent_pipeline.ledger import Account, Value
from agent_pipeline.pipeline import _image_review_items
from agent_pipeline.sources.classify import ClassifiedSource


@dataclass
class _FakeResult:
    output: RawImageProposal


class _FakeLLM:
    """Stands in for `LLMClient`: `LLMImageModel.propose` only ever calls `.structured(...)`
    and reads `.output` off the result, so that's all this needs to fake -- no cache, no
    transport, no network."""

    def __init__(self, rows: list[ImageValueRow]) -> None:
        self._rows = rows

    def structured(self, **kwargs):
        return _FakeResult(output=RawImageProposal(rows=self._rows))


_IMAGE_SOURCE = ClassifiedSource(
    # A real file: _image_review_items reads its bytes (read_image), even though the fake
    # LLM below never looks at the image content, only returns scripted rows.
    path=Path("data/client_02_medium/statement_summary.png"),
    role="statement_image",
    method="structural",
)


def _value(amount: str) -> Value:
    return Value(
        amount=Decimal(amount),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=date(2026, 4, 30),
        source_id="client_data_db.json",
        quote="",
        selected_by="R3",
    )


def test_an_out_of_scope_account_is_never_matched_or_flagged() -> None:
    in_scope = Account(
        id="A-1",
        owners=["Jordan Reed"],
        type="Stocks & Shares ISA",
        in_scope=True,
        value=_value("45000"),
    )
    out_of_scope = Account(
        id="A-2",
        owners=["Jordan Reed"],
        type="Stocks & Shares ISA",
        in_scope=False,
        value=_value("99000"),
    )
    row = ImageValueRow(
        account_label="an account",
        account_type="Stocks & Shares ISA",
        amount_text="£99,000",
        currency_symbol="£",
    )
    llm = _FakeLLM(rows=[row])

    items = _image_review_items(
        _IMAGE_SOURCE,
        [in_scope, out_of_scope],
        {"A-1": "GBP", "A-2": "GBP"},
        llm,  # type: ignore[arg-type]
    )

    # The row's amount (£99,000) only matches the OUT-OF-SCOPE account's own value -- if
    # out-of-scope accounts were still candidates, this would silently confirm against the
    # wrong account. Matched against the in-scope account instead, it's a real disagreement.
    assert len(items) == 1
    assert items[0].kind == "image_discrepancy"


def test_currency_check_uses_the_raw_account_currency_not_the_defaulted_one() -> None:
    # select_values would have defaulted a missing record currency to "GBP" on the Value
    # itself -- account_currency_by_id carries the raw, still-missing value instead, so the
    # currency check is skipped rather than comparing against a currency nobody confirmed.
    account = Account(
        id="A-1",
        owners=["Jordan Reed"],
        type="Stocks & Shares ISA",
        in_scope=True,
        value=_value("45000"),
    )
    row = ImageValueRow(
        account_label="an account",
        account_type="Stocks & Shares ISA",
        amount_text="£45,000",
        currency_symbol="$",
    )
    llm = _FakeLLM(rows=[row])

    items = _image_review_items(_IMAGE_SOURCE, [account], {"A-1": None}, llm)  # type: ignore[arg-type]

    assert items == []


def test_currency_check_fires_when_the_raw_account_currency_is_known() -> None:
    account = Account(
        id="A-1",
        owners=["Jordan Reed"],
        type="Stocks & Shares ISA",
        in_scope=True,
        value=_value("45000"),
    )
    row = ImageValueRow(
        account_label="an account",
        account_type="Stocks & Shares ISA",
        amount_text="£45,000",
        currency_symbol="$",
    )
    llm = _FakeLLM(rows=[row])

    items = _image_review_items(_IMAGE_SOURCE, [account], {"A-1": "GBP"}, llm)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].kind == "currency"


def test_no_image_source_is_a_no_op() -> None:
    account = Account(id="A-1", owners=["Jordan Reed"], type="Cash Account", in_scope=True)
    llm = _FakeLLM(rows=[])

    assert _image_review_items(None, [account], {}, llm) == []  # type: ignore[arg-type]
