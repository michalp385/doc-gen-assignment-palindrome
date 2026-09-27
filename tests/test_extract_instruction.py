"""Report instruction extraction (T13, DESIGN.md section 4.3): the table is parsed in code;
a model is called only for an unrecognised label or a scope-mapping proposal. A scripted
fake model stands in for the real one -- offline, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_pipeline.extract.instruction import extract_instruction
from agent_pipeline.extract.schemas import CanonicalField, ScopeMappingProposal
from agent_pipeline.ledger import Account
from agent_pipeline.sources.adapters.docx import read_docx

CLIENT_01_INSTRUCTION = read_docx(Path("data/client_01_clean/report_request.docx"))


@dataclass
class ScriptedModel:
    label_map: dict[str, CanonicalField | None] = field(default_factory=dict)
    scope_proposal: ScopeMappingProposal | None = None
    map_label_calls: list[str] = field(default_factory=list)
    propose_scope_calls: list[str] = field(default_factory=list)

    def map_label(self, label: str, value: str) -> CanonicalField | None:
        self.map_label_calls.append(label)
        return self.label_map.get(label)

    def propose_scope(self, phrase: str, accounts: list[Account]) -> ScopeMappingProposal:
        self.propose_scope_calls.append(phrase)
        assert self.scope_proposal is not None
        return self.scope_proposal


def _scope_proposal(phrase: str = "Holloway Stocks & Shares ISA") -> ScopeMappingProposal:
    return ScopeMappingProposal(
        phrase=phrase, candidate_account_ids=["H-ISA-01"], reason="type and platform match"
    )


def test_client_01s_table_is_parsed_without_any_model_call_for_labels() -> None:
    model = ScriptedModel(scope_proposal=_scope_proposal())

    result = extract_instruction(CLIENT_01_INSTRUCTION, [], model)

    assert model.map_label_calls == []  # every label is already known
    by_canonical = {f.canonical: f.value for f in result.fields}
    assert by_canonical["risk_profile"] == "4 (moderate)"
    assert by_canonical["initial_charge"] == "0%"
    assert by_canonical["scope"] == "Holloway Stocks & Shares ISA"
    assert all(not f.is_tbc for f in result.fields)


def test_scope_mapping_is_proposed_once_for_the_scope_field() -> None:
    model = ScriptedModel(scope_proposal=_scope_proposal())

    result = extract_instruction(CLIENT_01_INSTRUCTION, [], model)

    assert model.propose_scope_calls == ["Holloway Stocks & Shares ISA"]
    assert result.scope_mapping == _scope_proposal()


def test_an_unrecognised_label_triggers_exactly_one_model_call() -> None:
    doc = read_docx(Path("data/client_01_clean/report_request.docx"))
    doc.tables[0].append(["Some new field nobody has seen", "A value"])
    model = ScriptedModel(
        label_map={"Some new field nobody has seen": "source_of_funds"},
        scope_proposal=_scope_proposal(),
    )

    result = extract_instruction(doc, [], model)

    assert model.map_label_calls == ["Some new field nobody has seen"]
    new_field = next(
        f for f in result.fields if f.label_as_written == "Some new field nobody has seen"
    )
    assert new_field.canonical == "source_of_funds"


def test_an_unmappable_label_stays_uncanonicalised() -> None:
    doc = read_docx(Path("data/client_01_clean/report_request.docx"))
    doc.tables[0].append(["Completely unrelated field", "Some value"])
    model = ScriptedModel(label_map={}, scope_proposal=_scope_proposal())  # maps nothing

    result = extract_instruction(doc, [], model)

    new_field = next(f for f in result.fields if f.label_as_written == "Completely unrelated field")
    assert new_field.canonical is None


def test_a_missing_or_tbc_value_is_flagged_not_defaulted() -> None:
    doc = read_docx(Path("data/client_01_clean/report_request.docx"))
    for row in doc.tables[0]:
        if row[0] == "Initial charge":
            row[1] = "TBC"
    model = ScriptedModel(scope_proposal=_scope_proposal())

    result = extract_instruction(doc, [], model)

    charge = next(f for f in result.fields if f.canonical == "initial_charge")
    assert charge.is_tbc is True
    assert charge.value == "TBC"


def test_an_empty_value_is_also_treated_as_tbc() -> None:
    doc = read_docx(Path("data/client_01_clean/report_request.docx"))
    for row in doc.tables[0]:
        if row[0] == "Initial charge":
            row[1] = ""
    model = ScriptedModel(scope_proposal=_scope_proposal())

    result = extract_instruction(doc, [], model)

    charge = next(f for f in result.fields if f.canonical == "initial_charge")
    assert charge.is_tbc is True


def test_no_scope_mapping_is_proposed_when_the_scope_value_is_tbc() -> None:
    doc = read_docx(Path("data/client_01_clean/report_request.docx"))
    for row in doc.tables[0]:
        if row[0] == "Accounts covered":
            row[1] = "TBC"
    model = ScriptedModel(scope_proposal=_scope_proposal())

    result = extract_instruction(doc, [], model)

    assert model.propose_scope_calls == []
    assert result.scope_mapping is None
