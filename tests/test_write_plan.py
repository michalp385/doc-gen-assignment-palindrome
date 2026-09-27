"""T14: `plan_sections` resolves a section's config-declared selectors against the ledger,
and rewrites extraction-derived text digit-free before it ever reaches a writer prompt."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from agent_pipeline.config import ReportConfig, Section, StageConfig
from agent_pipeline.ledger import Account, Action, ExcludedItem, Fact, Ledger, Value
from agent_pipeline.write.plan import PlanningError, has_figure, plan_sections, rewrite_digit_free

MEETING_DATE = date(2026, 1, 1)


def _value(quote: str, amount: Decimal = Decimal("20000")) -> Value:
    return Value(
        amount=amount,
        currency="GBP",
        precision="exact",
        qualifier="exact",
        date=MEETING_DATE,
        source_id="meeting_notes.docx",
        quote=quote,
        selected_by="R3",
    )


def _base_ledger() -> Ledger:
    return Ledger(
        client="client_01_clean",
        meeting_date=MEETING_DATE,
        accounts=[
            Account(
                id="H-ISA-01",
                owners=["Margaret Hughes"],
                type="Stocks & Shares ISA",
                platform="Holloway",
                in_scope=True,
            )
        ],
        actions=[
            Action(
                id="a1",
                description="move £20,000 into the Stocks & Shares ISA",
                accounts=["H-ISA-01"],
                quote="move £20,000 into the ISA",
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
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the top-up amount",
                value=_value("£20,000"),
                reportable=True,
                transaction=True,
                role="transaction",
            )
        },
    )


def _ledger(**overrides: Any) -> Ledger:
    return _base_ledger().model_copy(update=overrides)


def _config(section: Section) -> ReportConfig:
    return ReportConfig(
        document_title="Investment Advice Report",
        global_instructions="Write in British English.",
        stages={"write": StageConfig(model="gpt-6-luna", reasoning_effort="low")},
        sections=[section],
    )


def test_facts_selector_only_matches_declared_glob_patterns():
    ledger = _ledger(
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the top-up amount",
                role="transaction",
            ),
            "account.H-ISA-01.value": Fact(
                id="account.H-ISA-01.value",
                kind="money",
                description="the ISA value",
                role="account value",
            ),
        }
    )
    section = Section(
        id="recommendations",
        title="Recommendations",
        use_if="always",
        template="<<recommendation>>",
        facts=["action.*.amount"],
    )
    plans = plan_sections(ledger, _config(section))
    assert len(plans) == 1
    assert [f.id for f in plans[0].facts] == ["action.a1.amount"]


def test_markers_and_excluded_selectors_only_match_declared_patterns():
    from agent_pipeline.ledger import Marker

    ledger = _ledger(
        markers=[
            Marker(
                id="", key="platform_charge_holloway", text="marker text", reason="r", section="s"
            ),
            Marker(id="", key="advice_charge", text="marker text", reason="r", section="s"),
        ]
    )
    section = Section(
        id="fees_charges",
        title="Fees & Charges",
        use_if="always",
        template="<<fees>>",
        markers=["platform_charge_*"],
    )
    plans = plan_sections(ledger, _config(section))
    assert [m.key for m in plans[0].markers] == ["platform_charge_holloway"]


def test_section_excluded_by_predicate_produces_no_plan():
    ledger = _ledger(tax_section=False)
    section = Section(
        id="tax_implications",
        title="Tax Implications",
        use_if="Include when the advice sells or disposes of investments.",
        predicate="taxable_disposal",
        template="<<cgt_statement>>",
    )
    plans = plan_sections(ledger, _config(section))
    assert plans == []


def test_unknown_predicate_raises_planning_error():
    ledger = _ledger()
    section = Section(
        id="weird",
        title="Weird",
        use_if="always",
        predicate="not_a_real_predicate",
        template="<<x>>",
    )
    with pytest.raises(PlanningError):
        plan_sections(ledger, _config(section))


def test_action_text_matching_a_known_fact_quote_becomes_a_token():
    ledger = _ledger()
    section = Section(
        id="recommendations",
        title="Recommendations",
        use_if="always",
        template="<<recommendation>>",
        facts=["action.*.amount"],
        text_sources=["actions"],
    )
    plans = plan_sections(ledger, _config(section))
    assert plans[0].rewritten_texts["action.a1"] == (
        "move {fact:action.a1.amount} into the Stocks & Shares ISA"
    )
    assert plans[0].withheld == []


def test_action_text_with_an_unmatched_figure_is_withheld_not_passed_through():
    ledger = _ledger(
        actions=[
            Action(
                id="a1",
                description="move £20,000 into the ISA, and possibly a further £5,000 later",
                accounts=["H-ISA-01"],
            )
        ]
    )
    section = Section(
        id="recommendations",
        title="Recommendations",
        use_if="always",
        template="<<recommendation>>",
        facts=["action.*.amount"],
        text_sources=["actions"],
    )
    plans = plan_sections(ledger, _config(section))
    assert plans[0].rewritten_texts == {}
    assert len(plans[0].withheld) == 1
    assert plans[0].withheld[0].reason == (
        "contains a money or percentage figure not matched to a known fact"
    )


def test_excluded_text_with_no_figure_passes_through_unchanged():
    ledger = _ledger()
    section = Section(
        id="background_objectives",
        title="Background & Objectives",
        use_if="always",
        template="<<summary>>",
        excluded=["aspiration"],
        text_sources=["excluded"],
    )
    plans = plan_sections(ledger, _config(section))
    assert plans[0].rewritten_texts["excluded.e1"] == "gifting to her grandchildren"
    assert plans[0].withheld == []


def test_scope_description_context_built_from_in_scope_accounts():
    ledger = _ledger()
    section = Section(
        id="introduction",
        title="Introduction",
        use_if="always",
        template="<<scope>>",
        context=["scope_description"],
    )
    plans = plan_sections(ledger, _config(section))
    assert plans[0].context["scope_description"] == ("your Stocks & Shares ISA held with Holloway")


def test_objectives_context_resolves_from_ledger_objectives_field():
    ledger = _ledger(objectives="the client's circumstances are unchanged since last review")
    section = Section(
        id="background_objectives",
        title="Background & Objectives",
        use_if="always",
        template="<<summary>>",
        context=["objectives"],
    )
    plans = plan_sections(ledger, _config(section))
    assert plans[0].context["objectives"] == (
        "the client's circumstances are unchanged since last review"
    )


def test_objectives_context_is_absent_when_ledger_objectives_is_unset():
    ledger = _ledger(objectives=None)
    section = Section(
        id="background_objectives",
        title="Background & Objectives",
        use_if="always",
        template="<<summary>>",
        context=["objectives"],
    )
    plans = plan_sections(ledger, _config(section))
    assert "objectives" not in plans[0].context


def test_extra_context_still_overrides_a_ledger_resolved_context_value():
    ledger = _ledger()
    section = Section(
        id="introduction",
        title="Introduction",
        use_if="always",
        template="<<scope>>",
        context=["scope_description"],
    )
    plans = plan_sections(
        ledger,
        _config(section),
        extra_context={"introduction": {"scope_description": "your accounts"}},
    )
    assert plans[0].context["scope_description"] == "your accounts"


def test_spec_text_and_meeting_text_are_passed_through_to_every_plan():
    ledger = _ledger()
    section = Section(
        id="recommendations",
        title="Recommendations",
        use_if="always",
        template="<<recommendation>>",
    )
    plans = plan_sections(
        ledger,
        _config(section),
        spec_text="the spec document's text",
        meeting_text="the meeting record's text",
    )
    assert plans[0].spec_text == "the spec document's text"
    assert plans[0].meeting_text == "the meeting record's text"


def test_has_figure_detects_word_form_money_and_percent():
    assert has_figure("twenty thousand pounds")
    assert has_figure("fifty per cent")
    assert has_figure("£20,000")
    assert has_figure("50%")
    assert not has_figure("a sizeable amount")


def test_rewrite_digit_free_with_no_facts_and_no_figure_passes_through():
    rewritten, defect = rewrite_digit_free("gifting to her grandchildren", [], _ledger())
    assert rewritten == "gifting to her grandchildren"
    assert defect is None
