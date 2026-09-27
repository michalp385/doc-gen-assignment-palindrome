"""The deterministic stub writer (DESIGN.md section 10.5): builds a "reference bundle"
(report text, ledger) straight from a client's `eval/expected/<client>.json`, with no LLM
involved, so `tests/test_gate_mutations.py` has something concrete to run gates and
mutations against before a real writer exists (M1). Unlike `src/`, this is allowed to be
client-specific, hand-fitted code (like `expected.py`'s own JSON fixtures) -- it renders
one client's known-correct report, it doesn't generalise to an unseen one.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agent_pipeline.gates.deterministic import FCA_LINE, TABLE_HEADER, ReportBundle, TableRow
from agent_pipeline.ledger import Account, ExcludedItem, Ledger, Marker, Value, number_markers
from agent_pipeline.reconcile.markers import required_markers
from agent_pipeline.reconcile.review import ReviewItemInput, build_review_items, marker_review_items
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.markdown import read_markdown
from report_eval.expected import ExpectedFacts, load_expected
from report_eval.truth import ExpectedTruth

DATA_ROOT = Path("data")


def _doc_text(path: Path) -> str:
    doc = read_docx(path) if path.suffix == ".docx" else read_markdown(path)
    return " ".join(doc.paragraphs.values())


def _marker_bracket(marker: Marker) -> str:
    """P1's marker format, applied to an already-numbered marker."""
    return f"[ADVISER TO CONFIRM {marker.id}: {marker.text}]"


def _build_client_01_clean(facts: ExpectedFacts) -> ReportBundle:
    client_dir = DATA_ROOT / "client_01_clean"

    isa_value = Value(
        amount=Decimal("52000"),
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=facts.meeting_date,
        source_id="client_data_db.json",
        quote="",
        selected_by="R3",
    )
    accounts = [
        Account(
            id="H-ISA-01",
            owners=["Margaret Hughes"],
            type="Stocks & Shares ISA",
            platform="Holloway",
            status="open",
            in_scope=True,
            value=isa_value,
        ),
        Account(
            id="H-CASH-01",
            owners=["Margaret Hughes"],
            type="Cash Account",
            platform="Holloway",
            status="open",
            in_scope=False,
            scope_reason="not named in the report instruction's scope phrase",
        ),
    ]

    # required_markers sorts platforms then appends advice_charge, so this order is stable:
    # platform_charge_holloway is always cited (and numbered #1) before advice_charge (#2).
    markers = required_markers(in_scope_platforms={"Holloway"})
    review = build_review_items(
        [
            ReviewItemInput(
                kind="p4_note",
                blocking=False,
                detail=(
                    "The £20,000 top-up uses this tax year's full ISA allowance; prior use "
                    "this tax year is unstated."
                ),
                refs=["H-ISA-01"],
            ),
            *marker_review_items(markers),
        ]
    )

    ledger = number_markers(
        Ledger(
            client=facts.client,
            meeting_date=facts.meeting_date,
            risk_profile=facts.risk_profile,
            initial_charge=facts.initial_charge,
            tax_section=facts.sections.get("tax_implications", False),
            accounts=accounts,
            excluded=[
                ExcludedItem.model_validate(
                    {
                        "id": "e1",
                        "class": "aspiration",
                        "description": "gifting to her grandchildren",
                        "allowed_in": ["background_objectives"],
                        "quote": "she may want to discuss gifting to her grandchildren",
                    }
                )
            ],
            markers=markers,
            review=review,
        ),
        report_order=[m.key for m in markers],
    )
    platform_marker, advice_marker = ledger.markers

    sections = {
        "introduction": (
            "This report covers your Stocks & Shares ISA held with Holloway.\n\n" + FCA_LINE
        ),
        "background_objectives": (
            "Margaret Hughes is retired and her circumstances are unchanged since last year's "
            "review. She remains comfortable with her agreed risk profile, 4 (moderate). She "
            "mentioned a possible future interest in gifting to her grandchildren, which is not "
            "covered by this advice.\n\n"
            f"{TABLE_HEADER}\n"
            "|---|---|---|---|\n"
            "| H-ISA-01 | Margaret Hughes | Stocks & Shares ISA | £52,000 |\n"
        ),
        "recommendations": (
            "We recommend moving £20,000 from the Holloway cash account into the Stocks & "
            "Shares ISA, using this tax year's ISA allowance. There is no initial charge for "
            "this transaction (0%)."
        ),
        "fees_charges": (
            "The ongoing platform charge and advice charge rates apply to this account: "
            f"{_marker_bracket(platform_marker)} and {_marker_bracket(advice_marker)}."
        ),
        "conclusion": (
            "The value of investments can fall as well as rise and you may get back less than "
            "you invest. Past performance is not a guide to future returns.\n\n"
            "Please let us know if you would like to proceed with this recommendation."
        ),
    }
    report_text = "\n\n".join(sections.values())

    table_rows = [TableRow(account_id="H-ISA-01", owners=["Margaret Hughes"], value_text="£52,000")]

    return ReportBundle(
        report_text=report_text,
        sections=sections,
        table_rows=table_rows,
        ledger=ledger,
        internal_guidance_text=_doc_text(client_dir / "fde_notes.md"),
        meeting_text=_doc_text(client_dir / "meeting_notes.docx"),
        spec_text=_doc_text(client_dir / "template_spec.md"),
    )


_BUILDERS = {"client_01_clean": _build_client_01_clean}


def build_reference_bundle(client: str) -> tuple[ReportBundle, ExpectedTruth]:
    facts = load_expected(client)
    builder = _BUILDERS.get(client)
    if builder is None:
        raise NotImplementedError(
            f"no reference-bundle builder for {client!r} yet -- add one alongside its "
            f"eval/expected/{client}.json when that client's hand-written case is built"
        )
    return builder(facts), ExpectedTruth(facts)
