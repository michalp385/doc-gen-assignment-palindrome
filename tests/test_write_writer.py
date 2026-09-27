"""T14: `write_slot`'s per-slot writer loop -- invented-token, digit-free, required-marker
and the slot-level deterministic gates, in order, with up to 2 repair rounds before
`WriterStopError` (DESIGN.md section 8.4: writing is a required stage, never a silent drop)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agent_pipeline.config import Placeholder, Section
from agent_pipeline.ledger import Fact, Ledger, Marker, Value
from agent_pipeline.write.schemas import PlanFact, PlanMarker, SectionPlan
from agent_pipeline.write.writer import (
    RawSlotDraft,
    WriterConfigError,
    WriterStopError,
    write_slot,
)

MEETING_DATE = date(2026, 1, 1)


class ScriptedModel:
    """Returns each of `responses` in order, repeating the last one if the loop asks for
    more attempts than were scripted."""

    def __init__(self, responses: list[list[str]]):
        self._responses = responses
        self.calls = 0

    def write(self, plan: SectionPlan, corrections: list[str]) -> RawSlotDraft:
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return RawSlotDraft(paragraphs=self._responses[index])


class NeverCalledModel:
    def write(self, plan: SectionPlan, corrections: list[str]) -> RawSlotDraft:
        raise AssertionError("model should not be called when the section config is invalid")


def _ledger(**overrides) -> Ledger:
    base = Ledger(
        client="client_01_clean",
        facts={
            "action.a1.amount": Fact(
                id="action.a1.amount",
                kind="money",
                description="the top-up amount",
                value=Value(
                    amount=Decimal("20000"),
                    currency="GBP",
                    precision="exact",
                    qualifier="exact",
                    date=MEETING_DATE,
                    source_id="meeting_notes.docx",
                    quote="£20,000",
                    selected_by="R3",
                ),
                reportable=True,
                transaction=True,
                role="transaction",
            )
        },
        markers=[
            Marker(
                id="#1",
                key="platform_charge_holloway",
                text="the platform charge rate for Holloway",
                reason="not stated in any source",
                section="fees_charges",
            )
        ],
    )
    return base.model_copy(update=overrides)


def _recommendations_section() -> Section:
    return Section(
        id="recommendations",
        title="Recommendations",
        use_if="always",
        template="We recommend the following:\n\n<<recommendation>>",
        placeholders={
            "recommendation": Placeholder(kind="generated", prompt="Describe the recommendation.")
        },
        facts=["action.*.amount"],
    )


def _plan(**overrides) -> SectionPlan:
    base = SectionPlan(
        section_id="recommendations",
        facts=[
            PlanFact(
                id="action.a1.amount",
                description="the top-up amount",
                role="transaction",
                transaction=True,
            )
        ],
    )
    for key, value in overrides.items():
        base = SectionPlan(**{**base.__dict__, key: value})
    return base


def test_write_slot_succeeds_on_the_first_attempt():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel(
        [["We recommend moving {fact:action.a1.amount} into the Stocks & Shares ISA."]]
    )
    draft = write_slot(plan, section, _ledger(), model, guidance_text="")
    assert draft.repairs_used == 0
    assert draft.filled_text == "We recommend moving £20,000 into the Stocks & Shares ISA."


def test_invented_fact_token_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["We recommend moving {fact:not.in.plan} into the ISA."]])
    with pytest.raises(WriterStopError, match="invented fact token"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_invented_marker_token_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["The rate is {marker:not_in_plan}."]])
    with pytest.raises(WriterStopError, match="invented marker token"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_digit_outside_a_token_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["We recommend investing 500 pounds today."]])
    with pytest.raises(WriterStopError, match="a digit appears outside a token"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_word_form_money_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["We recommend investing twenty thousand pounds."]])
    with pytest.raises(WriterStopError, match="money figure written in words"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_word_form_percent_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["Growth of fifty per cent is expected next year."]])
    with pytest.raises(WriterStopError, match="percentage written in words"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_missing_required_marker_is_rejected():
    plan = _plan(
        section_id="fees_charges",
        markers=[PlanMarker(key="platform_charge_holloway", text="platform charge rate")],
        facts=[],
    )
    section = Section(
        id="fees_charges",
        title="Fees & Charges",
        use_if="always",
        template="<<fees>>",
        placeholders={"fees": Placeholder(kind="generated", prompt="State the fees.")},
        markers=["platform_charge_*"],
    )
    model = ScriptedModel([["The ongoing platform charge applies to your account."]])
    with pytest.raises(WriterStopError, match=r"appears 0 times, expected exactly 1"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_marker_appearing_twice_is_rejected():
    plan = _plan(
        section_id="fees_charges",
        markers=[PlanMarker(key="platform_charge_holloway", text="platform charge rate")],
        facts=[],
    )
    section = Section(
        id="fees_charges",
        title="Fees & Charges",
        use_if="always",
        template="<<fees>>",
        placeholders={"fees": Placeholder(kind="generated", prompt="State the fees.")},
        markers=["platform_charge_*"],
    )
    text = (
        "The rate is {marker:platform_charge_holloway}, cited again as "
        "{marker:platform_charge_holloway}."
    )
    model = ScriptedModel([[text]])
    with pytest.raises(WriterStopError, match=r"appears 2 times, expected exactly 1"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_table_markup_in_a_generated_slot_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["| Account | Owner | Type | Value |\n|---|---|---|---|"]])
    with pytest.raises(WriterStopError, match="table"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_heading_markup_in_a_generated_slot_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["# Recommendation\nWe recommend proceeding."]])
    with pytest.raises(WriterStopError, match="heading"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_paraphrase_of_the_risk_warning_is_rejected():
    plan = _plan()
    section = _recommendations_section()
    text = (
        "The value of your investments could fall as well as rise, so you might get back "
        "less than you invested."
    )
    model = ScriptedModel([[text]])
    with pytest.raises(WriterStopError, match="paraphrase"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_transaction_fact_used_in_background_is_rejected():
    plan = _plan(section_id="background_objectives")
    section = Section(
        id="background_objectives",
        title="Background & Objectives",
        use_if="always",
        template="<<summary>>",
        placeholders={"summary": Placeholder(kind="generated", prompt="Summarise.")},
        facts=["action.*.amount"],
    )
    model = ScriptedModel([["We discussed moving {fact:action.a1.amount} into the ISA."]])
    with pytest.raises(WriterStopError, match="used in Background"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_a_non_transaction_fact_is_allowed_in_background():
    plan = _plan(
        section_id="background_objectives",
        facts=[
            PlanFact(
                id="account.h1.value",
                description="the ISA value",
                role="account value",
                transaction=False,
            )
        ],
    )
    section = Section(
        id="background_objectives",
        title="Background & Objectives",
        use_if="always",
        template="<<summary>>",
        placeholders={"summary": Placeholder(kind="generated", prompt="Summarise.")},
        facts=["account.*.value"],
    )
    ledger = _ledger(
        facts={
            "account.h1.value": Fact(
                id="account.h1.value",
                kind="money",
                description="the ISA value",
                value=Value(
                    amount=Decimal("52000"),
                    currency="GBP",
                    precision="exact",
                    qualifier="exact",
                    date=MEETING_DATE,
                    source_id="client_data_db.json",
                    quote="£52,000",
                    selected_by="R3",
                ),
                reportable=True,
                role="account value",
            )
        }
    )
    model = ScriptedModel([["Your account is currently valued at {fact:account.h1.value}."]])
    draft = write_slot(plan, section, ledger, model, guidance_text="")
    assert draft.filled_text == "Your account is currently valued at £52,000."


def test_internal_guidance_leak_is_rejected():
    plan = _plan(spec_text="")
    section = _recommendations_section()
    guidance_text = (
        "FDE guidance: always mention the client's long standing relationship with the "
        "firm before any recommendation is given."
    )
    text = "We note the client's long standing relationship with the firm before proceeding."
    model = ScriptedModel([[text]])
    with pytest.raises(WriterStopError, match="internal guidance text found"):
        write_slot(plan, section, _ledger(), model, guidance_text=guidance_text)


def test_internal_guidance_overlap_already_in_the_spec_is_not_flagged():
    guidance_text = "the client's long standing relationship with the firm matters greatly"
    plan = _plan(spec_text=guidance_text)
    section = _recommendations_section()
    text = "We recommend moving {fact:action.a1.amount} into the ISA."
    model = ScriptedModel([[text]])
    draft = write_slot(plan, section, _ledger(), model, guidance_text=guidance_text)
    assert draft.filled_text == "We recommend moving £20,000 into the ISA."


def test_internal_guidance_overlap_already_in_the_meeting_record_is_not_flagged():
    guidance_text = "the client's long standing relationship with the firm matters greatly"
    plan = _plan(meeting_text=guidance_text)
    section = _recommendations_section()
    text = "We recommend moving {fact:action.a1.amount} into the ISA."
    model = ScriptedModel([[text]])
    draft = write_slot(plan, section, _ledger(), model, guidance_text=guidance_text)
    assert draft.filled_text == "We recommend moving £20,000 into the ISA."


def test_g12_pre_rejects_a_capitalised_start_after_a_lowercase_continuation():
    plan = _plan(section_id="introduction", facts=[])
    section = Section(
        id="introduction",
        title="Introduction",
        use_if="always",
        template=(
            "Further to our recent discussions, we are writing to set out our advice in "
            "relation to <<scope>>. This advice is based on the information currently "
            "available to us."
        ),
        placeholders={"scope": Placeholder(kind="generated", prompt="Say which accounts.")},
        context=["scope_description"],
    )
    model = ScriptedModel([["Your Stocks & Shares ISA held with Holloway"]])
    with pytest.raises(WriterStopError, match="starts capitalised"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_g12_pre_allows_a_lowercase_start_after_a_lowercase_continuation():
    plan = _plan(section_id="introduction", facts=[])
    section = Section(
        id="introduction",
        title="Introduction",
        use_if="always",
        template=(
            "Further to our recent discussions, we are writing to set out our advice in "
            "relation to <<scope>>. This advice is based on the information currently "
            "available to us."
        ),
        placeholders={"scope": Placeholder(kind="generated", prompt="Say which accounts.")},
        context=["scope_description"],
    )
    model = ScriptedModel([["your Stocks & Shares ISA held with Holloway"]])
    draft = write_slot(plan, section, _ledger(), model, guidance_text="")
    assert draft.filled_text == "your Stocks & Shares ISA held with Holloway"


def test_g12_pre_does_not_force_lowercase_after_a_paragraph_break():
    plan = _plan(section_id="conclusion", facts=[])
    section = Section(
        id="conclusion",
        title="Conclusion",
        use_if="always",
        template=(
            "The value of investments can fall as well as rise and you may get back less "
            "than you invest. Past performance is not a guide to future returns.\n\n<<closing>>"
        ),
        placeholders={"closing": Placeholder(kind="generated", prompt="Write a closing line.")},
    )
    model = ScriptedModel([["Please let us know if you would like to proceed."]])
    draft = write_slot(plan, section, _ledger(), model, guidance_text="")
    assert draft.filled_text == "Please let us know if you would like to proceed."


def test_g12_pre_rejects_a_trailing_full_stop_where_the_template_already_adds_one():
    plan = _plan(section_id="introduction", facts=[])
    section = Section(
        id="introduction",
        title="Introduction",
        use_if="always",
        template=(
            "Further to our recent discussions, we are writing to set out our advice in "
            "relation to <<scope>>. This advice is based on the information currently "
            "available to us."
        ),
        placeholders={"scope": Placeholder(kind="generated", prompt="Say which accounts.")},
        context=["scope_description"],
    )
    model = ScriptedModel([["your Stocks & Shares ISA held with Holloway."]])
    with pytest.raises(WriterStopError, match="ends with a full stop"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_g12_post_catches_an_internal_double_stop_the_boundary_scoped_pre_check_misses():
    plan = _plan(section_id="conclusion", facts=[])
    section = Section(
        id="conclusion",
        title="Conclusion",
        use_if="always",
        template=(
            "The value of investments can fall as well as rise and you may get back less "
            "than you invest. Past performance is not a guide to future returns.\n\n<<closing>>"
        ),
        placeholders={"closing": Placeholder(kind="generated", prompt="Write a closing line.")},
    )
    text = "We recommend proceeding with the transfer.. Please confirm your instructions."
    model = ScriptedModel([[text]])
    with pytest.raises(WriterStopError, match="double full stop"):
        write_slot(plan, section, _ledger(), model, guidance_text="")


def test_repair_round_succeeds_after_one_correction():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel(
        [
            ["We recommend investing 500 pounds."],
            ["We recommend moving {fact:action.a1.amount} into the Stocks & Shares ISA."],
        ]
    )
    draft = write_slot(plan, section, _ledger(), model, guidance_text="")
    assert draft.repairs_used == 1
    assert model.calls == 2


def test_exhausted_repairs_raises_writer_stop_error():
    plan = _plan()
    section = _recommendations_section()
    model = ScriptedModel([["We recommend investing 500 pounds."]])
    with pytest.raises(WriterStopError):
        write_slot(plan, section, _ledger(), model, guidance_text="")
    assert model.calls == 3


def test_no_generated_placeholder_raises_writer_config_error_without_calling_the_model():
    plan = _plan(section_id="background_objectives", facts=[])
    section = Section(
        id="background_objectives",
        title="Background & Objectives",
        use_if="always",
        template="<<holdings_table>>",
        placeholders={"holdings_table": Placeholder(kind="computed")},
    )
    with pytest.raises(WriterConfigError):
        write_slot(plan, section, _ledger(), NeverCalledModel(), guidance_text="")


def test_two_generated_placeholders_raises_writer_config_error():
    plan = _plan()
    section = Section(
        id="weird",
        title="Weird",
        use_if="always",
        template="<<a>> <<b>>",
        placeholders={
            "a": Placeholder(kind="generated", prompt="A"),
            "b": Placeholder(kind="generated", prompt="B"),
        },
    )
    with pytest.raises(WriterConfigError):
        write_slot(plan, section, _ledger(), NeverCalledModel(), guidance_text="")
