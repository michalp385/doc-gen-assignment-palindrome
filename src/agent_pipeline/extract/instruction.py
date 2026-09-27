"""Report instruction extraction (DESIGN.md section 4.3).

The table is parsed in code (T7's `read_docx` already gives structured rows); a model is
needed only for two narrow cases: an unrecognised label (unseen instructions may rename
fields), and proposing a scope mapping for R8. The scope proposal is exactly that -- a
proposal: `reconcile/scope.py::resolve_scope` (T8) remains the sole, unchanged, code-only
check for what's actually in scope. Nothing here decides scope.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from agent_pipeline.config import PromptSpec
from agent_pipeline.extract.schemas import (
    CanonicalField,
    InstructionExtraction,
    RequestField,
    ScopeMappingProposal,
)
from agent_pipeline.ledger import Account
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.document import SourceDoc

# Client 01's own table labels, normalised (lowercase, trailing "?" stripped). Unseen clients
# may use different wording entirely -- that's exactly what InstructionModel.map_label is for.
_KNOWN_LABELS: dict[str, CanonicalField] = {
    "adviser": "adviser",
    "accounts covered": "scope",
    "investment amount": "investment_amount",
    "source of funds": "source_of_funds",
    "selling existing investments": "selling_existing_investments",
    "product recommended": "product_recommended",
    "held in single or joint name": "holding_basis",
    "agreed risk profile": "risk_profile",
    "risk profile": "risk_profile",
    "initial charge": "initial_charge",
}


class InstructionModel(Protocol):
    def map_label(self, label: str, value: str) -> CanonicalField | None: ...
    def propose_scope(self, phrase: str, accounts: list[Account]) -> ScopeMappingProposal: ...


def _normalize_label(label: str) -> str:
    return label.strip().rstrip("?").strip().lower()


def _is_tbc(value: str) -> bool:
    stripped = value.strip()
    return not stripped or stripped.upper() == "TBC"


def extract_instruction(
    doc: SourceDoc, accounts: list[Account], model: InstructionModel
) -> InstructionExtraction:
    if not doc.tables:
        return InstructionExtraction(fields=[], scope_mapping=None)

    fields: list[RequestField] = []
    scope_mapping: ScopeMappingProposal | None = None

    for row in doc.tables[0]:
        if len(row) < 2:
            continue
        label_as_written, value = row[0], row[1]
        canonical = _KNOWN_LABELS.get(_normalize_label(label_as_written))
        if canonical is None:
            canonical = model.map_label(label_as_written, value)

        fields.append(
            RequestField(
                canonical=canonical,
                label_as_written=label_as_written,
                value=value,
                is_tbc=_is_tbc(value),
            )
        )

        if canonical == "scope" and not _is_tbc(value):
            scope_mapping = model.propose_scope(value, accounts)

    return InstructionExtraction(fields=fields, scope_mapping=scope_mapping)


class _LabelMapOutput(BaseModel):
    canonical_field: CanonicalField | None


class _ScopeProposalOutput(BaseModel):
    candidate_account_ids: list[str]
    reason: str


class LLMInstructionModel:
    """The real `InstructionModel`, wrapping T11's `LLMClient` with
    `config/prompts/extract_instruction.md` (label mapping) and
    `config/prompts/scope_mapping.md` (scope proposal, DESIGN.md section 4.3)."""

    def __init__(
        self, llm_client: LLMClient, label_prompt: PromptSpec, scope_prompt: PromptSpec
    ) -> None:
        self._llm = llm_client
        self._label_prompt = label_prompt
        self._scope_prompt = scope_prompt

    def map_label(self, label: str, value: str) -> CanonicalField | None:
        result = self._llm.structured(
            stage="extract",
            prompt=self._label_prompt,
            inputs={"label": label, "value": value},
            schema=_LabelMapOutput,
        )
        return result.output.canonical_field

    def propose_scope(self, phrase: str, accounts: list[Account]) -> ScopeMappingProposal:
        accounts_context = [{"id": a.id, "type": a.type, "platform": a.platform} for a in accounts]
        result = self._llm.structured(
            stage="extract",
            prompt=self._scope_prompt,
            inputs={"phrase": phrase, "accounts": accounts_context},
            schema=_ScopeProposalOutput,
        )
        return ScopeMappingProposal(
            phrase=phrase,
            candidate_account_ids=result.output.candidate_account_ids,
            reason=result.output.reason,
        )
