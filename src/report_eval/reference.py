"""The deterministic stub writer (DESIGN.md section 10.5): builds a "reference bundle"
(report text, ledger) straight from a client's `eval/expected/<client>.json`, with no LLM
involved, so `tests/test_gate_mutations.py` has something concrete to run gates and
mutations against before a real writer exists (M1). Unlike `src/`, this is allowed to be
client-specific, hand-fitted code (like `expected.py`'s own JSON fixtures) -- it renders
one client's known-correct report, it doesn't generalise to an unseen one.

Client 01's bundle is hand-written; clients 02-04 (T24) are rendered from their expected
facts by one generic function (`_build_from_expected`), so every deterministic gate's
mutation can run on all four real clients' reference bundles.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

from agent_pipeline.extract.parsing import parse_amount
from agent_pipeline.gates.deterministic import (
    FCA_LINE,
    RISK_WARNING_FULL,
    TABLE_HEADER,
    ReportBundle,
    TableRow,
)
from agent_pipeline.ledger import Account, ExcludedItem, Ledger, Marker, Value, number_markers
from agent_pipeline.reconcile.markers import required_markers
from agent_pipeline.reconcile.review import ReviewItemInput, build_review_items, marker_review_items
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.json_accounts import read_accounts
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


_FEES_MARKER_KEYS = ("advice_charge", "new_account_charges")


def _marker_section(key: str) -> str:
    """Where the reference report places a marker, mirroring the shipped config's section
    selectors: CGT in Tax Implications, charge rates in Fees & Charges, the rest (amounts to
    settle) in Recommendations."""
    if key.startswith("cgt"):
        return "tax_implications"
    if key.startswith("platform_charge_") or key in _FEES_MARKER_KEYS:
        return "fees_charges"
    return "recommendations"


def _value_from_table_text(text: str, day: dt.date | None) -> Value | None:
    parsed = parse_amount(text)
    if parsed is None:
        return None
    return Value(
        amount=parsed.amount,
        currency=parsed.currency,
        precision=parsed.precision,
        qualifier=parsed.qualifier,
        date=day,
        source_id="reference",
        quote="",
        selected_by="R3",
    )


def _brackets(markers: list[Marker]) -> str:
    return " and ".join(_marker_bracket(m) for m in markers)


def _build_from_expected(facts: ExpectedFacts) -> ReportBundle:
    """A known-correct report for one client, rendered straight from its expected facts: the
    table (with a footnote in the pipeline's own style, the superseded figure only), the
    amounts the sources state, every required marker in the section the shipped config
    routes it to, a review sheet carrying each expected item, and every aspiration once in
    Background and every tangent nowhere. Prose is deliberately plain -- this is a stub
    writer for the gates, not a quality benchmark."""
    client_dir = DATA_ROOT / facts.client
    platforms = {
        r.account_id: r.platform
        for holder in read_accounts(client_dir / "client_data_db.json").holders.values()
        for r in holder.accounts
        if r.account_id
    }

    accounts = [
        Account(
            id=row.account,
            owners=row.owners,
            type=row.type,
            platform=platforms.get(row.account),
            status="open",
            in_scope=True,
            is_new=row.account.startswith("new:"),
            value=None
            if row.value == "To be opened"
            else _value_from_table_text(row.value, facts.meeting_date),
        )
        for row in facts.table_rows
    ]

    ledger_markers = [
        Marker(
            id="", key=m.key, text=m.description, reason="reference", section=_marker_section(m.key)
        )
        for m in facts.markers
        if m.required
    ]
    # P1: numbered by first appearance -- the order the reference report cites them in.
    ordered = [
        m
        for section in ("recommendations", "tax_implications", "fees_charges")
        for m in ledger_markers
        if m.section == section
    ]
    review = build_review_items(
        [
            *(
                ReviewItemInput(
                    kind=r.kind,
                    blocking=r.blocking,
                    detail=f"{r.key}: " + "; ".join(r.must_mention),
                    refs=[],
                )
                for r in facts.review_items
            ),
            *marker_review_items(ordered),
        ]
    )
    excluded = [
        ExcludedItem.model_validate(
            {
                "id": f"e{i}",
                "class": item.item_class,
                "description": item.subject,
                "allowed_in": ["background_objectives"] if item.item_class == "aspiration" else [],
                "quote": item.subject,
            }
        )
        for i, item in enumerate(facts.excluded_items, start=1)
    ]
    ledger = number_markers(
        Ledger(
            client=facts.client,
            meeting_date=facts.meeting_date,
            risk_profile=facts.risk_profile,
            initial_charge=facts.initial_charge,
            tax_section=facts.sections.get("tax_implications", False),
            accounts=accounts,
            excluded=excluded,
            markers=ordered,
            review=review,
        ),
        report_order=[m.key for m in ordered],
    )
    by_section: dict[str, list[Marker]] = {}
    for marker in ledger.markers:
        by_section.setdefault(marker.section, []).append(marker)

    names = " and ".join(dict.fromkeys(o for row in facts.table_rows for o in row.owners))
    table_values = {row.value for row in facts.table_rows}
    footnote_figures = [f.value for f in facts.reportable_figures if f.placement == "footnote_only"]
    stated_figures = [
        f.value
        for f in facts.reportable_figures
        if f.placement == "any"
        and not f.optional
        and f.value not in table_values
        and "%" not in f.value
    ]

    table_lines = [TABLE_HEADER, "|---|---|---|---|"]
    footnotes: list[str] = []
    for row in facts.table_rows:
        table_lines.append(
            f"| {row.account} | {' & '.join(row.owners)} | {row.type} | {row.value} |"
        )
        figure = next((f for f in footnote_figures if row.footnote and f in row.footnote), None)
        if figure is not None:
            label = (
                f"{row.owners[0].split()[0]}'s {row.type}"
                if len(row.owners) == 1
                else f"Your joint {row.type}"
            )
            footnotes.append(f"{label} was previously shown as {figure}.")

    aspirations = [i.subject for i in facts.excluded_items if i.item_class == "aspiration"]
    background = [
        f"{names} have discussed their circumstances and objectives. "
        f"Their agreed risk profile is {facts.risk_profile}."
    ]
    background += [
        f"They also raised the following, which this advice does not cover: {subject}."
        for subject in aspirations
    ]
    background_text = "\n\n".join(
        [" ".join(background), "\n".join(table_lines)]
        + (["\n".join(footnotes)] if footnotes else [])
    )

    recommendation = [f"{action.description}." for action in facts.actions]
    if stated_figures:
        recommendation.append(f"The amounts involved are {', '.join(stated_figures)}.")
    if "recommendations" in by_section:
        recommendation.append(f"Still to be confirmed: {_brackets(by_section['recommendations'])}.")

    sections = {
        "introduction": f"This report is prepared for {names}.\n\n{FCA_LINE}",
        "background_objectives": background_text,
        "recommendations": " ".join(recommendation),
    }
    if ledger.tax_section:
        sections["tax_implications"] = (
            "The sale of these investments may create a capital gains tax liability, assessed "
            "against the annual exempt amount. "
            f"{_brackets(by_section.get('tax_implications', []))}."
        )
    sections["fees_charges"] = (
        "The ongoing platform charge and advice charge rates that apply are "
        f"{_brackets(by_section.get('fees_charges', []))}. "
        f"The initial charge that applies is {facts.initial_charge}."
    )
    sections["conclusion"] = (
        f"{RISK_WARNING_FULL}\n\nPlease let us know if you would like to proceed with this "
        "recommendation."
    )

    return ReportBundle(
        report_text="\n\n".join(sections.values()),
        sections=sections,
        table_rows=[
            TableRow(account_id=row.account, owners=row.owners, value_text=row.value)
            for row in facts.table_rows
        ],
        ledger=ledger,
        internal_guidance_text=_doc_text(client_dir / "fde_notes.md"),
        meeting_text=_doc_text(client_dir / "meeting_notes.docx"),
        spec_text=_doc_text(client_dir / "template_spec.md"),
    )


_BUILDERS = {
    "client_01_clean": _build_client_01_clean,
    "client_02_medium": _build_from_expected,
    "client_03_hard": _build_from_expected,
    "client_04_stretch": _build_from_expected,
}


def build_reference_bundle(client: str) -> tuple[ReportBundle, ExpectedTruth]:
    facts = load_expected(client)
    builder = _BUILDERS.get(client)
    if builder is None:
        raise NotImplementedError(
            f"no reference-bundle builder for {client!r} yet -- add one alongside its "
            f"eval/expected/{client}.json when that client's hand-written case is built"
        )
    return builder(facts), ExpectedTruth(facts)
