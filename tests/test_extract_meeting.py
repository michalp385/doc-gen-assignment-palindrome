"""Meeting extraction's verification loop (T13, DESIGN.md section 4.1-4.2). A scripted fake
model stands in for the real one -- offline, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_pipeline.extract.meeting import extract_meeting, find_in_source
from agent_pipeline.extract.quotes import CONSERVATIVE_DEFAULTS
from agent_pipeline.extract.schemas import (
    AgreedAction,
    Disposal,
    ExcludedItem,
    LabelEvidence,
    MoneyItem,
    OpenAction,
    Quote,
    RawMeetingProposal,
    ValueObservation,
)
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.document import SourceDoc

CLIENT_01_MEETING = read_docx(Path("data/client_01_clean/meeting_notes.docx"))


@dataclass
class ScriptedModel:
    """Returns queued proposals, one per call; the last is reused if the loop calls more
    than were queued (shouldn't happen within MAX_ROUNDS, but keeps tests simple)."""

    proposals: list[RawMeetingProposal]
    calls: list[list[str]] = field(default_factory=list)
    _index: int = 0

    def propose(self, doc_text: str, corrections: list[str]) -> RawMeetingProposal:
        self.calls.append(corrections)
        proposal = self.proposals[min(self._index, len(self.proposals) - 1)]
        self._index += 1
        return proposal


def _agreed_action(paragraph_id: str, quote: str) -> RawMeetingProposal:
    return RawMeetingProposal(
        agreed_actions=[AgreedAction(description=Quote(paragraph_id=paragraph_id, text=quote))]
    )


def test_a_good_quote_on_round_one_is_verified() -> None:
    model = ScriptedModel(
        [
            _agreed_action(
                "p5",
                "We agreed she would move £20,000 from the cash account into the Stocks & "
                "Shares ISA.",
            )
        ]
    )

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert len(model.calls) == 1
    assert len(result.agreed_actions) == 1
    assert result.dropped == []


def test_bad_quote_then_reask_then_fixed() -> None:
    model = ScriptedModel(
        [
            _agreed_action("p5", "this text does not exist in the document"),
            _agreed_action(
                "p5",
                "We agreed she would move £20,000 from the cash account into the Stocks & "
                "Shares ISA.",
            ),
        ]
    )

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert len(model.calls) == 2
    assert model.calls[0] == []  # round 1: no prior corrections
    assert "p5" in model.calls[1][0]  # round 2's correction names the failing paragraph
    assert len(result.agreed_actions) == 1
    assert result.agreed_actions[0].description.text.startswith("We agreed")
    assert result.dropped == []


def test_still_bad_after_three_rounds_is_dropped() -> None:
    model = ScriptedModel([_agreed_action("p5", "nonsense text never in the document")])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert len(model.calls) == 3
    assert result.agreed_actions == []
    assert len(result.dropped) == 1
    assert result.dropped[0].reason.startswith("could not verify")


def test_label_evidence_in_a_different_paragraph_falls_back_to_the_default() -> None:
    proposal = RawMeetingProposal(
        value_observations=[
            ValueObservation(
                account_reference="Stocks & Shares ISA",
                amount=Quote(paragraph_id="p5", text="£20,000"),
                basis="viewed_in_meeting",
                # Real evidence, but from a different paragraph than the fact itself.
                basis_evidence=LabelEvidence(paragraph_id="p4", text="cash sitting on deposit"),
            )
        ]
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert len(result.value_observations) == 1
    assert result.value_observations[0].basis == CONSERVATIVE_DEFAULTS["basis"]


def test_label_evidence_verified_in_the_same_paragraph_is_kept() -> None:
    proposal = RawMeetingProposal(
        excluded_items=[
            ExcludedItem(
                item_class="aspiration",
                text=Quote(paragraph_id="p7", text="gifting to her grandchildren"),
                class_evidence=LabelEvidence(
                    paragraph_id="p7", text="nothing should be actioned on it now"
                ),
            )
        ]
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert result.excluded_items[0].item_class == "aspiration"


def test_meeting_date_unparseable_or_unverified_quote_is_none() -> None:
    proposal = RawMeetingProposal(meeting_date=Quote(paragraph_id="p1", text="not in the text"))
    model = ScriptedModel([proposal])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert result.meeting_date is None


def test_meeting_date_with_a_verified_quote_is_kept() -> None:
    proposal = RawMeetingProposal(meeting_date=Quote(paragraph_id="p1", text="held 12 May 2026"))
    model = ScriptedModel([proposal])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert result.meeting_date is not None
    assert result.meeting_date.text == "held 12 May 2026"


def test_agreed_non_actions_count_as_actions() -> None:
    proposal = RawMeetingProposal(
        agreed_actions=[
            AgreedAction(
                description=Quote(
                    paragraph_id="p4",
                    text="would like to use this year's ISA allowance by moving some of it "
                    "into her Stocks & Shares ISA",
                ),
                is_non_action=True,
            )
        ]
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert len(result.agreed_actions) == 1
    assert result.agreed_actions[0].is_non_action is True


def test_blocking_defaults_true_when_evidence_is_elsewhere() -> None:
    proposal = RawMeetingProposal(
        open_actions=[
            OpenAction(
                text=Quote(
                    paragraph_id="p8",
                    text="confirm the ongoing charges with her once the report is issued",
                ),
                blocking=False,
                # Evidence from a different paragraph -- should default to blocking=True.
                blocking_evidence=LabelEvidence(paragraph_id="p1", text="held 12 May 2026"),
            )
        ]
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(CLIENT_01_MEETING, model)

    assert result.open_actions[0].blocking is True


def test_find_in_source_ranks_paragraphs_by_word_overlap() -> None:
    matches = find_in_source(CLIENT_01_MEETING, "move cash into the Stocks Shares ISA")
    assert matches
    assert matches[0].paragraph_id == "p5"


# --- Disposal's own fact-anchor quote (verifier report, T13 pre-commit checkpoint) ---------


def test_disposal_evidence_in_a_different_paragraph_defaults_to_unspecified() -> None:
    doc = SourceDoc(
        path=Path("synthetic.docx"),
        paragraphs={
            "p1": "We agreed to sell the General Investment Account.",
            "p2": "This will be done in full, with nothing partial.",
        },
    )
    proposal = RawMeetingProposal(
        disposals=[
            Disposal(
                account_reference="General Investment Account",
                quote=Quote(
                    paragraph_id="p1", text="We agreed to sell the General Investment Account."
                ),
                extent="full",
                # Evidence is real, but from a different paragraph than the disposal itself.
                extent_evidence=LabelEvidence(paragraph_id="p2", text="This will be done in full"),
            )
        ]
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(doc, model)

    assert len(result.disposals) == 1
    assert result.disposals[0].extent == "unspecified"


def test_disposal_with_unverifiable_quote_is_dropped() -> None:
    doc = SourceDoc(path=Path("synthetic.docx"), paragraphs={"p1": "Nothing about a sale here."})
    proposal = RawMeetingProposal(
        disposals=[
            Disposal(
                account_reference="General Investment Account",
                quote=Quote(paragraph_id="p1", text="sell the General Investment Account"),
                extent="full",
                extent_evidence=LabelEvidence(paragraph_id="p1", text="Nothing about a sale here"),
            )
        ]
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(doc, model)

    assert result.disposals == []
    assert len(result.dropped) == 1


# --- A genuine disposal's proceeds must not be suppressed by the internal-transfer rule ----
# (verifier report, T13 pre-commit checkpoint, finding #4). This guards the LOOP CODE's
# handling of a correctly-shaped model response -- it can't guard against the real model
# mis-happening to over-apply the internal-transfer exclusion, since that's model behaviour,
# which CLAUDE.md's own rule says is measured by the eval, not a scripted-model unit test.
# Client 02 (a real disposal-with-proceeds client, M2) is what will exercise the live model's
# actual calibration on this; tests/test_extract_live.py is the live-gated check until then.


def test_a_genuine_disposals_proceeds_are_not_suppressed_as_an_internal_transfer() -> None:
    doc = SourceDoc(
        path=Path("synthetic.docx"),
        paragraphs={
            "p1": "We agreed to sell the General Investment Account in full for £45,000 and "
            "move the proceeds into the Stocks & Shares ISA.",
        },
    )
    proposal = RawMeetingProposal(
        disposals=[
            Disposal(
                account_reference="General Investment Account",
                quote=Quote(
                    paragraph_id="p1",
                    text="We agreed to sell the General Investment Account in full",
                ),
                extent="full",
                extent_evidence=LabelEvidence(
                    paragraph_id="p1", text="sell the General Investment Account in full"
                ),
            )
        ],
        money_items=[
            MoneyItem(
                money_class="proceeds",
                purpose="proceeds of the General Investment Account sale",
                amount=Quote(paragraph_id="p1", text="£45,000"),
                class_evidence=LabelEvidence(
                    paragraph_id="p1", text="move the proceeds into the Stocks & Shares ISA"
                ),
            )
        ],
    )
    model = ScriptedModel([proposal])

    result = extract_meeting(doc, model)

    assert len(result.disposals) == 1
    assert len(result.money_items) == 1
    assert result.money_items[0].money_class == "proceeds"


# --- Prompt guardrail content (verifier report, T13 pre-commit checkpoint, finding #3) -----
# Cannot verify the real model still avoids these two mistakes without a live call (model
# behaviour is measured by the eval and the live check, not a unit test, CLAUDE.md's own
# rule) -- but an accidental future edit that deletes the corrective wording entirely is
# exactly the kind of silent regression a plain content check can catch for free.

_EXTRACT_MEETING_PROMPT = Path("config/prompts/extract_meeting.md").read_text(encoding="utf-8")


def test_prompt_still_excludes_internal_transfers_from_money_items() -> None:
    assert "not a money item at all" in _EXTRACT_MEETING_PROMPT


def test_prompt_still_distinguishes_routine_report_prep_from_a_genuine_open_action() -> None:
    assert "isn't one" in _EXTRACT_MEETING_PROMPT
    assert "split it" in _EXTRACT_MEETING_PROMPT.lower()
