"""A slot that starts with a client's name is accepted only after the repair rounds (tests first;
hand-written case 03).

The boundary check refuses a capital where the template continues a lowercase sentence, and it
cannot tell a name from a careless capital. Every round the model gets is judged exactly as
before, so a run whose first answer was corrected keeps the wording it always had (the committed
clients' cache depends on it). Only when the model has used every repair round and still starts
with a client's first name or a platform is that answer accepted: at that point it is correct
English, not an error. Any other capital still stops the run.
"""

from __future__ import annotations

import pytest

from agent_pipeline.config import Placeholder, Section
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.write.schemas import SectionPlan
from agent_pipeline.write.writer import MAX_ROUNDS, RawSlotDraft, WriterStopError, write_slot

SECTION = Section(
    id="introduction",
    title="Introduction",
    use_if="always",
    template="We are writing about <<scope>>.",
    placeholders={"scope": Placeholder(kind="generated", prompt="Say which accounts.")},
)
LEDGER = Ledger(
    client="c",
    accounts=[
        Account(
            id="A",
            type="Stocks & Shares ISA",
            owners=["Ian Walsh"],
            platform="Holloway",
            in_scope=True,
        )
    ],
)


class Scripted:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    def write(self, plan: SectionPlan, corrections: list[str]) -> RawSlotDraft:
        text = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return RawSlotDraft(paragraphs=[text])


def _write(model: Scripted):  # type: ignore[no-untyped-def]
    return write_slot(
        SectionPlan(section_id="introduction"), SECTION, LEDGER, model, guidance_text=""
    )


def test_a_name_at_the_start_is_accepted_after_the_last_repair_round() -> None:
    model = Scripted(["Ian's Stocks & Shares ISA"])
    draft = _write(model)
    assert draft.filled_text == "Ian's Stocks & Shares ISA"
    assert draft.repairs_used == MAX_ROUNDS - 1 and model.calls == MAX_ROUNDS


def test_a_corrected_answer_wins_over_the_name_and_keeps_the_committed_flow() -> None:
    model = Scripted(["Ian's Stocks & Shares ISA", "the Stocks & Shares ISA held by Ian"])
    draft = _write(model)
    assert draft.filled_text == "the Stocks & Shares ISA held by Ian"
    assert draft.repairs_used == 1 and model.calls == 2


def test_any_other_capital_still_stops_the_run() -> None:
    with pytest.raises(WriterStopError, match="capitalised"):
        _write(Scripted(["The accounts comprising your ISA"]))
