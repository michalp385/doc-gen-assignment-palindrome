"""D8: internal guidance becomes structured handling directives; the writer never sees its text.

The model proposes; code verifies. A directive is kept only when its evidence is a verbatim quote
of the guidance, its sections are real report sections, its named person resolves to a holder, and
its instruction does not repeat the guidance's own wording (G10 stays a backstop, not the only
defence). An unresolved person is a review item, never a guess."""

from __future__ import annotations

from agent_pipeline.extract.guidance import (
    RawDirective,
    RawGuidanceProposal,
    extract_directives,
)

GUIDANCE = (
    "# Internal notes\n\nGeneral notes about the data sources.\n\n## This client\n"
    "The new money is an inheritance the client received after the death of her mother. "
    "Reference its origin with appropriate sensitivity.\n"
)
SECTIONS = ["background_objectives", "recommendations", "tax_implications"]
PEOPLE = ["Robert Fletcher", "Jean Fletcher"]
EVIDENCE = "Reference its origin with appropriate sensitivity."


class _Model:
    def __init__(self, *directives: RawDirective) -> None:
        self.directives = list(directives)
        self.calls = 0

    def propose(self, guidance_text: str, people: list[str], sections: list[str]):
        self.calls += 1
        return RawGuidanceProposal(directives=self.directives)


def _directive(**overrides) -> RawDirective:
    base = {
        "sections": ["background_objectives"],
        "instruction": "Describe where the new money came from gently and briefly.",
        "person": "Jean",
        "evidence": EVIDENCE,
    }
    return RawDirective(**{**base, **overrides})


def test_a_verified_directive_is_kept_with_the_person_resolved_to_a_holder() -> None:
    result = extract_directives(GUIDANCE, PEOPLE, SECTIONS, _Model(_directive()))

    (directive,) = result.directives
    assert directive.sections == ("background_objectives",)
    assert directive.person == "Jean Fletcher"
    assert directive.instruction.startswith("Describe where the new money came from")
    # an applied directive is shown to the adviser as an informational row
    (item,) = result.review_items
    assert item.kind == "handling_note" and item.blocking is False
    assert "background_objectives" in item.detail
    assert "Describe where the new money" in item.detail


def test_no_guidance_means_no_model_call() -> None:
    model = _Model(_directive())

    result = extract_directives("", PEOPLE, SECTIONS, model)

    assert result.directives == [] and model.calls == 0


def test_evidence_that_is_not_a_quote_of_the_guidance_drops_the_directive() -> None:
    result = extract_directives(
        GUIDANCE, PEOPLE, SECTIONS, _Model(_directive(evidence="Mention the bereavement."))
    )

    assert result.directives == []


def test_an_unknown_section_is_dropped_and_a_directive_with_none_left_is_dropped() -> None:
    result = extract_directives(
        GUIDANCE, PEOPLE, SECTIONS, _Model(_directive(sections=["made_up_section"]))
    )

    assert result.directives == []


def test_an_unresolved_person_is_a_review_item_not_a_guess() -> None:
    result = extract_directives(GUIDANCE, PEOPLE, SECTIONS, _Model(_directive(person="Marjorie")))

    assert result.directives == []
    (item,) = result.review_items
    assert item.kind == "ambiguity" and item.blocking is False
    assert "Marjorie" in item.detail


def test_an_instruction_that_repeats_the_guidance_wording_is_dropped_with_a_review_item() -> None:
    leaked = _directive(instruction="Reference its origin with appropriate sensitivity always.")

    result = extract_directives(GUIDANCE, PEOPLE, SECTIONS, _Model(leaked))

    assert result.directives == []
    (item,) = result.review_items
    assert item.kind == "ambiguity" and "wording" in item.detail


def test_a_directive_with_no_person_needs_none() -> None:
    result = extract_directives(GUIDANCE, PEOPLE, SECTIONS, _Model(_directive(person=None)))

    (directive,) = result.directives
    assert directive.person is None


def test_evidence_shorter_than_four_words_is_not_an_anchor() -> None:
    result = extract_directives(
        GUIDANCE, PEOPLE, SECTIONS, _Model(_directive(evidence="the client"))
    )

    assert result.directives == []


def test_curly_quotes_in_the_evidence_still_anchor() -> None:
    guidance = "## This client\nThe client's mother died recently, so mention it with care."
    quoted = "The client’s mother died recently, so mention it with care."

    result = extract_directives(guidance, PEOPLE, SECTIONS, _Model(_directive(evidence=quoted)))

    assert len(result.directives) == 1


def test_an_instruction_with_a_figure_is_dropped_with_a_review_item() -> None:
    result = extract_directives(
        GUIDANCE, PEOPLE, SECTIONS, _Model(_directive(instruction="Avoid the 12,000 gift."))
    )

    assert result.directives == []
    (item,) = result.review_items
    assert item.kind == "ambiguity" and "figure" in item.detail
