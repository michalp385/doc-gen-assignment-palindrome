"""Expected facts: the hand-derived truth a report is scored against (DESIGN.md section 10.1).

One JSON file per client under `eval/expected/`. The schema mirrors SCOPING.md section 7 and adds
what the eval needs to score stages on their own: extraction labels and investigation answers.
Every model forbids unknown keys, so a typo in a fixture fails loudly instead of silently
weakening a check.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXPECTED_ROOT = Path("eval/expected")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Release(_Strict):
    """The release state the pipeline should reach (DESIGN section 8.3)."""

    state: Literal["draft", "failed"]
    reason: str | None = None

    @model_validator(mode="after")
    def _failed_needs_reason(self) -> Release:
        if self.state == "failed" and not self.reason:
            raise ValueError("an expected failed generation must say why")
        return self


class TableRow(_Strict):
    """One row of the account table (G1, G6, P9). `account` is an account_id or `new:<slug>`."""

    account: str
    owners: list[str]
    type: str
    value: str  # as rendered: "£10,000", "c. £12,500", "To be opened", or "marker"
    footnote: str | None = None


class NotInTable(_Strict):
    """An account deliberately left out of the table, and why (SCOPING section 8)."""

    account: str
    reason: Literal["out_of_scope", "closed", "no_value", "out_of_scope_no_value"]


class ReportableFigure(_Strict):
    """A money amount or percentage the report may state (G2's closed list)."""

    value: str  # as rendered in prose or table: "£10,000", "c. £12,500", "1%", "up to £50,000"
    placement: Literal["any", "table", "footnote_only"] = "any"
    optional: bool = False
    section_hint: str | None = None  # guidance only; not enforced (SCOPING section 7)
    derived_from: list[str] | None = None  # the inputs, when the figure is a calculation


class Marker(_Strict):
    """An adviser-review marker the report must carry (G3, G14)."""

    key: str
    description: str
    required: bool = True


class Alternative(_Strict):
    """One acceptable outcome of a judgement call."""

    label: str
    markers: list[str] = Field(default_factory=list)
    review_items: list[str] = Field(default_factory=list)


class JudgementCall(_Strict):
    """A fact SCOPING section 7 settles as 'any of these passes' (G14)."""

    id: str
    description: str
    alternatives: list[Alternative] = Field(min_length=2)


ReviewKind = Literal[
    "conflict",
    "superseded",
    "out_of_scope_no_value",
    "open_action",
    "p4_note",
    "scope_flag",
    "currency",
    "image_discrepancy",
    "unverified",
    "degradation",
    "investigation",
    "ambiguity",  # an unresolved plan detail the sources leave open, not a conflict between them
]


class ReviewItem(_Strict):
    """A review-sheet entry the run must produce (G15)."""

    key: str
    kind: ReviewKind
    blocking: bool = False
    must_mention: list[str] = Field(default_factory=list)


class Action(_Strict):
    """An agreed action; agreed non-actions ('leave it as it is') count too (G8)."""

    description: str
    kind: Literal["action", "non_action"] = "action"
    accounts: list[str] = Field(default_factory=list)


class ExcludedItem(_Strict):
    """A tangent, aspiration or circumstance the client said not to action (P6)."""

    item_class: Literal["tangent", "aspiration", "circumstance"] = Field(alias="class")
    subject: str


class MaterialClaim(_Strict):
    """A material claim a correct report makes, for calibrating the G16 judge."""

    claim: str
    source_quote: str | None = None


Basis = Literal["viewed_in_meeting", "recalled", "from_paperwork", "confirmed_unchanged"]


class ValueObservation(_Strict):
    account: str
    amount_quote: str
    basis: Basis
    evidence_quote: str


class MoneyItem(_Strict):
    item_class: Literal["received", "committed", "proceeds", "external"] = Field(alias="class")
    amount_quote: str | None = None
    evidence_quote: str


class Disposal(_Strict):
    account: str
    extent: Literal["full", "portion", "unspecified"]
    evidence_quote: str


class OpenAction(_Strict):
    description: str
    blocking: bool
    evidence_quote: str


class Extraction(_Strict):
    """What extraction should find, labels included, so it can be scored alone (section 10.7)."""

    value_observations: list[ValueObservation] = Field(default_factory=list)
    money_items: list[MoneyItem] = Field(default_factory=list)
    disposals: list[Disposal] = Field(default_factory=list)
    open_actions: list[OpenAction] = Field(default_factory=list)


class InvestigationExpectation(_Strict):
    """The right outcome for a question the case is built to raise (section 5.2)."""

    question: str
    expected: str | None = None
    stays_unresolved: bool = False

    @model_validator(mode="after")
    def _answer_or_unresolved(self) -> InvestigationExpectation:
        if (self.expected is None) == (not self.stays_unresolved):
            raise ValueError("give exactly one of `expected` or `stays_unresolved: true`")
        return self


class ExpectedFacts(_Strict):
    """Everything a correct run produces for one client."""

    client: str
    meeting_date: dt.date | None
    risk_profile: str
    initial_charge: str
    release: Release
    table_rows: list[TableRow] = Field(default_factory=list)
    not_in_table: list[NotInTable] = Field(default_factory=list)
    reportable_figures: list[ReportableFigure] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)
    judgement_calls: list[JudgementCall] = Field(default_factory=list)
    review_items: list[ReviewItem] = Field(default_factory=list)
    sections: dict[str, bool] = Field(default_factory=dict)
    actions: list[Action] = Field(default_factory=list)
    excluded_items: list[ExcludedItem] = Field(default_factory=list)
    must_not_appear: list[str] = Field(default_factory=list)
    material_claims: list[MaterialClaim] = Field(default_factory=list)
    extraction: Extraction = Field(default_factory=Extraction)
    investigation: list[InvestigationExpectation] = Field(default_factory=list)


def load_expected(client: str, root: Path = EXPECTED_ROOT) -> ExpectedFacts:
    """Load `<root>/<client>.json`; the file must be about the client it is named for."""
    path = root / f"{client}.json"
    facts = ExpectedFacts.model_validate_json(path.read_text(encoding="utf-8"))
    if facts.client != client:
        raise ValueError(f"{path} is for client {facts.client!r}, not {client!r}")
    return facts
