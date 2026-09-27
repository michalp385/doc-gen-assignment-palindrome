"""T14's live check (DESIGN.md section 7.2, section 10.7): write each of client 01's six
generated slots for real, using a hand-built Ledger (not wired to T7/T8/T13's real modules --
that integration is T16's job), and confirm every slot passes its gates with no invented
figure. Run once by hand (`uv run pytest -m live tests/test_write_live.py`) with explicit
approval; every other run relies on the offline, scripted-model tests in test_write_writer.py.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent_pipeline.config import load_prompt, load_report_config
from agent_pipeline.ledger import (
    Account,
    Action,
    ExcludedItem,
    Fact,
    Ledger,
    Marker,
    Value,
    number_markers,
)
from agent_pipeline.llm import LLMClient, OpenAITransport
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.markdown import read_markdown
from agent_pipeline.write.plan import plan_sections
from agent_pipeline.write.schemas import PlanMarker, SectionPlan
from agent_pipeline.write.writer import LLMWriterModel, write_slot

load_dotenv()

CLIENT_DIR = Path("data/client_01_clean")
MEETING_DATE = date(2026, 5, 12)

# One writer call per generated slot (D6) -- the prompt file is bound per section, matching
# each section's own placeholder; write_slot never chooses a prompt itself.
_PROMPT_FILE_BY_SECTION = {
    "introduction": "write_scope.md",
    "fees_charges": "write_fees.md",
    "conclusion": "write_closing.md",
    "background_objectives": "write_summary.md",
    "recommendations": "write_recommendation.md",
    "tax_implications": "write_cgt_statement.md",
}


def _llm() -> LLMClient:
    config = load_report_config(Path("config/template_config.json"))
    models = json.loads(Path("config/models.json").read_text(encoding="utf-8"))
    return LLMClient(
        OpenAITransport(), stages=config.stages, models=models, cache_root=Path("cache/llm")
    )


def _doc_text(path: Path) -> str:
    doc = read_docx(path) if path.suffix == ".docx" else read_markdown(path)
    return " ".join(doc.paragraphs.values())


def _value(quote: str, amount: Decimal, source_id: str = "meeting_notes.docx") -> Value:
    return Value(
        amount=amount,
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=MEETING_DATE,
        source_id=source_id,
        quote=quote,
        selected_by="R3",
    )


def _client_01_ledger() -> Ledger:
    markers = [
        Marker(
            id="",
            key="platform_charge_holloway",
            text="the ongoing platform charge rate for Holloway",
            reason="not stated in any source",
            section="fees_charges",
        ),
        Marker(
            id="",
            key="advice_charge",
            text="the ongoing advice charge rate",
            reason="not stated in any source",
            section="fees_charges",
        ),
    ]
    ledger = Ledger(
        client="client_01_clean",
        meeting_date=MEETING_DATE,
        risk_profile="4 (moderate)",
        initial_charge="0%",
        objectives=(
            "Margaret is retired and her circumstances are unchanged since last year's "
            "review. She remains comfortable with her agreed risk profile."
        ),
        tax_section=False,
        accounts=[
            Account(
                id="H-ISA-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                platform="Holloway",
                in_scope=True,
                value=_value("£52,000", Decimal("52000"), source_id="client_data_db.json"),
            ),
            Account(
                id="H-CASH-01",
                owners=["Margaret Hughes"],
                type="Cash Account",
                platform="Holloway",
                in_scope=False,
            ),
        ],
        actions=[
            Action(
                id="a1",
                description=(
                    "Move £20,000 from the Holloway cash account into the Stocks & Shares ISA"
                ),
                kind="action",
                accounts=["H-CASH-01", "H-ISA-01"],
            )
        ],
        excluded=[
            ExcludedItem.model_validate(
                {
                    "id": "e1",
                    "class": "aspiration",
                    "description": "gifting to her grandchildren",
                    "allowed_in": ["background_objectives"],
                }
            )
        ],
        markers=markers,
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the top-up amount",
                value=_value("£20,000", Decimal("20000")),
                reportable=True,
                transaction=True,
                role="transaction",
            ),
            "account.h-isa-01.value": Fact(
                id="account.h-isa-01.value",
                kind="money",
                description="the ISA's current value",
                value=_value("£52,000", Decimal("52000"), source_id="client_data_db.json"),
                reportable=True,
                role="account value",
            ),
        },
    )
    return number_markers(ledger, report_order=[m.key for m in markers])


@pytest.mark.live
def test_client_01_generated_slots_all_pass_their_gates() -> None:
    config = load_report_config(Path("config/template_config.json"))
    ledger = _client_01_ledger()
    llm = _llm()
    guidance_text = _doc_text(CLIENT_DIR / "fde_notes.md")
    spec_text = _doc_text(CLIENT_DIR / "template_spec.md")
    meeting_text = _doc_text(CLIENT_DIR / "meeting_notes.docx")

    plans = plan_sections(ledger, config, spec_text=spec_text, meeting_text=meeting_text)
    plans_by_section = {p.section_id: p for p in plans}
    sections_by_id = {s.id: s for s in config.sections}

    # tax_implications is excluded for this client (no taxable disposal); it's exercised by
    # test_synthetic_cgt_statement_slot_passes_its_gates below, with its own ledger.
    assert set(plans_by_section) == {
        "introduction",
        "fees_charges",
        "conclusion",
        "background_objectives",
        "recommendations",
    }

    for section_id, plan in plans_by_section.items():
        section = sections_by_id[section_id]
        prompt = load_prompt(Path("config/prompts") / _PROMPT_FILE_BY_SECTION[section_id])
        model = LLMWriterModel(llm, prompt)
        draft = write_slot(plan, section, ledger, model, guidance_text=guidance_text)
        assert draft.repairs_used <= 2
        assert draft.filled_text.strip()


@pytest.mark.live
def test_synthetic_cgt_statement_slot_passes_its_gates() -> None:
    """No hand-written client has a taxable disposal (client 01 doesn't), so this exercises
    write_cgt_statement.md against a small synthetic ledger built just for this check."""
    from agent_pipeline.config import Placeholder, Section

    marker = Marker(
        id="#1",
        key="cgt_liability",
        text="the capital gains tax liability arising from this disposal",
        reason="CGT is never estimated by the model",
        section="tax_implications",
    )
    ledger = Ledger(client="synthetic_disposal", tax_section=True, markers=[marker])
    section = Section(
        id="tax_implications",
        title="Tax Implications",
        use_if=(
            "Include when the advice sells or disposes of investments that may create a "
            "taxable gain."
        ),
        predicate="taxable_disposal",
        template="<<cgt_statement>>",
        placeholders={
            "cgt_statement": Placeholder(
                kind="generated", prompt="State that CGT may apply; never estimate the figure."
            )
        },
        markers=["cgt_*"],
    )
    plan = SectionPlan(
        section_id="tax_implications",
        markers=[PlanMarker(key="cgt_liability", text=marker.text)],
    )
    prompt = load_prompt(Path("config/prompts/write_cgt_statement.md"))
    model = LLMWriterModel(_llm(), prompt)

    draft = write_slot(plan, section, ledger, model, guidance_text="")
    assert draft.repairs_used <= 2
    assert "[ADVISER TO CONFIRM #1:" in draft.filled_text
