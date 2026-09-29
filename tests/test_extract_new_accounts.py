"""The meeting extraction's `new_accounts` fact (tests first): an account the plan opens. Its
quote is verified against the meeting like every other fact, and one that does not verify is
dropped and recorded, never built into a report. A scripted fake model stands in for the real
one, offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_pipeline.extract.meeting import extract_meeting
from agent_pipeline.extract.schemas import NewAccount, Quote, RawMeetingProposal
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.document import SourceDoc

MEETING = read_docx(Path("data/client_03_hard/meeting_notes.docx"))
PLAN_ID, PLAN_TEXT = next(
    (pid, text) for pid, text in MEETING.paragraphs.items() if "new jointly-held" in text
)


@dataclass
class Scripted:
    proposals: list[RawMeetingProposal]
    calls: list[list[str]] = field(default_factory=list)
    _index: int = 0

    def propose(self, doc_text: str, corrections: list[str]) -> RawMeetingProposal:
        self.calls.append(corrections)
        proposal = self.proposals[min(self._index, len(self.proposals) - 1)]
        self._index += 1
        return proposal


def _proposal(text: str, *, joint: bool = True, owners: list[str] | None = None):
    return RawMeetingProposal(
        new_accounts=[
            NewAccount(
                description=Quote(paragraph_id=PLAN_ID, text=text),
                joint=joint,
                owner_references=owners or [],
            )
        ]
    )


def test_a_verified_new_account_is_kept() -> None:
    model = Scripted([_proposal("open a new jointly-held investment account for the balance")])
    result = extract_meeting(MEETING, model)
    assert len(model.calls) == 1
    (account,) = result.new_accounts
    assert account.joint is True
    assert result.dropped == []


def test_an_unverifiable_new_account_is_re_asked_then_dropped_and_recorded() -> None:
    model = Scripted([_proposal("open a brand new offshore trust for the family")])
    result = extract_meeting(MEETING, model)
    assert len(model.calls) == 3  # MAX_ROUNDS
    assert result.new_accounts == []
    assert [d.description for d in result.dropped] == ["new account"]


def test_a_bad_quote_then_a_fixed_one_on_the_reask() -> None:
    model = Scripted(
        [
            _proposal("a made-up sentence"),
            _proposal("open a new jointly-held investment account for the balance"),
        ]
    )
    result = extract_meeting(MEETING, model)
    assert len(model.calls) == 2
    assert len(result.new_accounts) == 1


def test_owner_references_are_carried_for_a_single_holder_account() -> None:
    model = Scripted(
        [_proposal("new jointly-held investment account", joint=False, owners=["Jean"])]
    )
    (account,) = extract_meeting(MEETING, model).new_accounts
    assert account.joint is False
    assert account.owner_references == ["Jean"]


def test_a_meeting_with_no_new_account_has_none() -> None:
    assert extract_meeting(MEETING, Scripted([RawMeetingProposal()])).new_accounts == []


def test_the_source_doc_type_is_the_normal_one() -> None:
    assert isinstance(MEETING, SourceDoc)
