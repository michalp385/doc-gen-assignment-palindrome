"""Quote-anchored extraction schemas (DESIGN.md section 4.3).

Every fact stores the quote and paragraph id it came from, never a model-parsed value --
T4's `parse_amount`/`parse_date` and T5's `verify_quote`/`verify_label` do that work from
the verified quote itself, in code. A decisive label (an observation's `basis`, a money
item's `class`, `blocking`, a disposal's `extent`, tangent-vs-aspiration) carries its own
evidence quote, checked against the fact's own paragraph, never trusted on the model's word
alone (section 4.2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Quote(_Strict):
    paragraph_id: str
    text: str


class LabelEvidence(_Strict):
    paragraph_id: str
    text: str


Basis = Literal["viewed_in_meeting", "recalled", "from_paperwork", "confirmed_unchanged"]
MoneyClass = Literal["received", "committed", "proceeds", "external"]
DisposalExtent = Literal["full", "portion", "unspecified"]
ExcludedClass = Literal["tangent", "aspiration", "circumstance"]


class ValueObservation(_Strict):
    account_reference: str  # as written in the source, before scope resolution
    amount: Quote
    basis: Basis
    basis_evidence: LabelEvidence


class MoneyItem(_Strict):
    # None when the class label's evidence is missing/unverified: DESIGN.md section 4.2's
    # default is "not available; review item" -- not one of the four real classes, so money
    # is never allocated on a guess (G7).
    money_class: MoneyClass | None
    purpose: str
    amount: Quote | None = None
    class_evidence: LabelEvidence


class AgreedAction(_Strict):
    description: Quote
    accounts_referenced: list[str] = Field(default_factory=list)
    amount: Quote | None = None
    is_non_action: bool = False  # an agreed non-action ("leave it as it is") counts too (G8)


class Disposal(_Strict):
    account_reference: str
    quote: Quote  # the disposal mention itself -- extent_evidence is checked against this
    extent: DisposalExtent
    extent_evidence: LabelEvidence


class LimitSignal(_Strict):
    text: Quote  # e.g. "already part-funded", "worried about over-contributing" (P4)


class OpenAction(_Strict):
    text: Quote
    blocking: bool
    blocking_evidence: LabelEvidence


class ExcludedItem(_Strict):
    item_class: ExcludedClass
    text: Quote
    class_evidence: LabelEvidence


class NewAccount(_Strict):
    """An account the plan opens (R1, P9): the meeting's own words agreeing to open one, and
    whether it is joint. Code builds the account (`reconcile/new_accounts.py`); the model only
    says one was agreed. `owner_references` are holder names as written, for a non-joint one."""

    description: Quote
    joint: bool
    owner_references: list[str] = Field(default_factory=list)


class ObjectiveStatement(_Strict):
    text: Quote


class DroppedFact(_Strict):
    """A fact still unverified after the 3-round loop: never a report fact, a review item
    instead ("could not verify: ...", DESIGN.md section 4.1)."""

    description: str
    last_quote: str
    reason: str


class RawMeetingProposal(_Strict):
    """Exactly what the model's structured output produces, one call. `dropped` isn't here:
    deciding what's dropped is the verification loop's job, computed from verify_quote/
    verify_label failures, never something the model states about its own output."""

    meeting_date: Quote | None = None  # unparseable or absent -> undated for R3/R10
    attendees: list[str] = Field(default_factory=list)
    value_observations: list[ValueObservation] = Field(default_factory=list)
    money_items: list[MoneyItem] = Field(default_factory=list)
    agreed_actions: list[AgreedAction] = Field(default_factory=list)
    disposals: list[Disposal] = Field(default_factory=list)
    limit_signals: list[LimitSignal] = Field(default_factory=list)
    open_actions: list[OpenAction] = Field(default_factory=list)
    excluded_items: list[ExcludedItem] = Field(default_factory=list)
    objectives_and_circumstances: list[ObjectiveStatement] = Field(default_factory=list)
    accounts_mentioned: list[str] = Field(default_factory=list)  # for R1's new-account check
    new_accounts: list[NewAccount] = Field(default_factory=list)


class MeetingExtraction(RawMeetingProposal):
    dropped: list[DroppedFact] = Field(default_factory=list)


CanonicalField = Literal[
    "adviser",
    "scope",
    "investment_amount",
    "source_of_funds",
    "selling_existing_investments",
    "product_recommended",
    "holding_basis",
    "risk_profile",
    "initial_charge",
]


class RequestField(_Strict):
    canonical: CanonicalField | None  # None only if unresolved even after the model fallback
    label_as_written: str
    value: str
    is_tbc: bool = False  # missing or reads "TBC" (P11): a marker, never a default


class ScopeMappingProposal(_Strict):
    phrase: str
    candidate_account_ids: list[str] = Field(default_factory=list)
    reason: str


class InstructionExtraction(_Strict):
    fields: list[RequestField] = Field(default_factory=list)
    scope_mapping: ScopeMappingProposal | None = None
