"""T19: G16's `_requires_coverage` exempts the account table (and its footnote) -- its
rendered text is synthesised from the ledger (G1/G6 already check it deterministically),
not a model claim about a source document, so it can never satisfy `_verify_claims`'
`verify_quote` check against one. Client 01's single-row table happened to pass coverage
before this was made explicit (a sentence-splitting accident, not by design); client 02's
three-row table exposed the gap. It also exempts the fixed "initial charge" template
sentence (config/base.json), whose value is a *computed* placeholder G13 already checks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent_pipeline.gates.judge import _requires_coverage
from agent_pipeline.ledger import Account, Ledger, Value
from agent_pipeline.write.table import build_table


def _ledger_with_gia() -> Ledger:
    return Ledger(
        client="c",
        initial_charge="0%",
        accounts=[
            Account(
                id="H-GIA-J",
                owners=["David Clarke", "Susan Clarke"],
                type="General Investment Account",
                platform="Holloway",
                in_scope=True,
                value=Value(
                    amount=Decimal("45000"),
                    currency="GBP",
                    precision="approximate",
                    qualifier="a_little_over",
                    date=date(2026, 5, 14),
                    source_id="meeting_notes.docx",
                    quote="a little over £45,000",
                    selected_by="R3",
                ),
                superseded=[
                    Value(
                        amount=Decimal("40000"),
                        currency="GBP",
                        precision="exact",
                        qualifier="exact",
                        date=date(2026, 3, 15),
                        source_id="client_data_db.json",
                        quote="",
                        selected_by="R3",
                    )
                ],
            )
        ],
    )


def test_the_account_table_never_requires_a_material_claim() -> None:
    ledger = _ledger_with_gia()
    table = build_table(ledger)
    header_and_row = table.split("\n\n")[0]
    assert _requires_coverage(header_and_row, ledger) is False


def test_the_table_footnote_never_requires_a_material_claim() -> None:
    ledger = _ledger_with_gia()
    table = build_table(ledger)
    footnote = table.split("\n\n")[1]
    assert "£40,000" in footnote  # sanity: this is really the footnote block
    assert _requires_coverage(footnote, ledger) is False


def test_the_fixed_initial_charge_sentence_never_requires_a_material_claim() -> None:
    ledger = _ledger_with_gia()
    assert _requires_coverage("The initial charge that applies is 0%.", ledger) is False


def test_ordinary_prose_with_a_figure_still_requires_coverage() -> None:
    assert _requires_coverage("We recommend topping up the ISA by c. £45,000.", Ledger(client="c"))


def test_a_markers_own_bracket_text_never_requires_a_material_claim() -> None:
    # A marker is code-inserted from the ledger (P1), never a model claim -- G14 already
    # checks it exists and maps to a review row.
    sentence = (
        "The capital gains tax on the disposal is "
        "[ADVISER TO CONFIRM #3: capital gains tax on the disposal]."
    )
    assert _requires_coverage(sentence, Ledger(client="c")) is False
