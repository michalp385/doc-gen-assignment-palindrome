"""D8/D29 plumbing: a verified directive reaches only the sections it names, and a section with no
directive sends the writer no `handling` input at all (so its cache key is what it always was)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from agent_pipeline.config import PromptSpec, ReportConfig, Section, StageConfig
from agent_pipeline.ledger import Ledger
from agent_pipeline.llm import LLMClient
from agent_pipeline.write.plan import plan_sections
from agent_pipeline.write.schemas import SectionPlan
from agent_pipeline.write.writer import LLMWriterModel, RawSlotDraft


def _section(section_id: str) -> Section:
    return Section(
        id=section_id,
        title=section_id,
        use_if="always",
        template="<<slot>>",
    )


def _config(*sections: Section) -> ReportConfig:
    return ReportConfig(
        document_title="Investment Advice Report",
        global_instructions="Write in British English.",
        stages={"write": StageConfig(model="gpt-6-luna", reasoning_effort="low")},
        sections=list(sections),
    )


def test_a_directive_reaches_only_the_sections_it_names() -> None:
    config = _config(_section("background_objectives"), _section("recommendations"))

    plans = plan_sections(
        Ledger(client="x"),
        config,
        handling={"background_objectives": ["About Jean: describe the new money gently."]},
    )

    by_id = {p.section_id: p for p in plans}
    assert by_id["background_objectives"].handling == ["About Jean: describe the new money gently."]
    assert by_id["recommendations"].handling == []


class _RecordingLLM:
    def __init__(self) -> None:
        self.inputs: dict = {}

    def structured(self, *, stage, prompt, inputs, schema):
        self.inputs = inputs
        return SimpleNamespace(output=RawSlotDraft(paragraphs=[]))


def _write(plan: SectionPlan) -> dict:
    llm = _RecordingLLM()
    # A recording stand-in for the client and prompt: only `structured` and the prompt object are
    # passed through, so the types are cast rather than built for real.
    prompt = cast(PromptSpec, SimpleNamespace(text="prompt", version="v"))
    LLMWriterModel(cast(LLMClient, llm), prompt).write(plan, [])
    return llm.inputs


def test_no_directive_means_no_handling_key_in_the_writer_input() -> None:
    assert "handling" not in _write(SectionPlan(section_id="recommendations"))


def test_a_directive_is_passed_as_the_handling_input() -> None:
    inputs = _write(SectionPlan(section_id="recommendations", handling=["Be brief."]))

    assert inputs["handling"] == ["Be brief."]
