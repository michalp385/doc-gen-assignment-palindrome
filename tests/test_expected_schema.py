"""The expected-facts schema: the truth every eval-mode gate is scored against (DESIGN §10.1)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from report_eval.expected import ExpectedFacts, load_expected


def minimal() -> dict:
    """The smallest valid fixture: a client issued as a draft with one table row."""
    return {
        "client": "example_client",
        "meeting_date": "2026-05-12",
        "risk_profile": "4 (moderate)",
        "initial_charge": "0%",
        "release": {"state": "draft"},
        "table_rows": [
            {
                "account": "ACC-1",
                "owners": ["Alex Example"],
                "type": "Stocks & Shares ISA",
                "value": "£10,000",
            }
        ],
        "sections": {"tax_implications": False},
    }


def test_minimal_fixture_loads_with_empty_defaults() -> None:
    facts = ExpectedFacts.model_validate(minimal())
    assert facts.release.state == "draft"
    assert facts.markers == []
    assert facts.review_items == []
    assert facts.extraction.value_observations == []


def test_round_trip_preserves_everything() -> None:
    data = minimal()
    data["reportable_figures"] = [
        {"value": "£10,000", "placement": "table"},
        {"value": "£8,000", "placement": "footnote_only"},
        {"value": "c. £18,000", "optional": True, "derived_from": ["£10,000", "£8,000"]},
    ]
    data["markers"] = [{"key": "platform_charge", "description": "ongoing platform charge rate"}]
    facts = ExpectedFacts.model_validate(data)
    again = ExpectedFacts.model_validate_json(facts.model_dump_json(by_alias=True))
    assert again == facts


@pytest.mark.parametrize(
    "path",
    [
        (),  # top level
        ("table_rows", 0),
        ("release",),
    ],
)
def test_unknown_keys_are_rejected_at_every_level(path: tuple) -> None:
    data = minimal()
    target = data
    for step in path:
        target = target[step]
    target["unexpected"] = 1
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)


def test_release_state_is_draft_or_failed_and_failed_needs_a_reason() -> None:
    data = minimal()
    data["release"] = {"state": "issued"}
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)

    data["release"] = {"state": "failed"}
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)

    data["release"] = {"state": "failed", "reason": "two report instructions disagree"}
    assert ExpectedFacts.model_validate(data).release.reason


def test_placement_is_restricted() -> None:
    data = minimal()
    data["reportable_figures"] = [{"value": "£1", "placement": "anywhere"}]
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)


def test_judgement_call_lists_acceptable_alternatives() -> None:
    data = minimal()
    data["judgement_calls"] = [
        {
            "id": "isa_subscriptions",
            "description": "full ISA allowances, prior use unstated",
            "alternatives": [
                {"label": "note", "markers": [], "review_items": ["isa_prior_use"]},
                {"label": "marker", "markers": ["isa_amounts"], "review_items": []},
            ],
        }
    ]
    facts = ExpectedFacts.model_validate(data)
    assert [a.label for a in facts.judgement_calls[0].alternatives] == ["note", "marker"]


def test_a_judgement_call_needs_at_least_two_alternatives() -> None:
    data = minimal()
    data["judgement_calls"] = [{"id": "x", "description": "d", "alternatives": [{"label": "only"}]}]
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)


def test_excluded_items_use_class_as_the_json_key() -> None:
    data = minimal()
    data["excluded_items"] = [{"class": "aspiration", "subject": "gifting"}]
    facts = ExpectedFacts.model_validate(data)
    assert facts.excluded_items[0].item_class == "aspiration"
    assert json.loads(facts.model_dump_json(by_alias=True))["excluded_items"][0]["class"] == (
        "aspiration"
    )


def test_extraction_labels_are_restricted() -> None:
    data = minimal()
    data["extraction"] = {
        "value_observations": [
            {
                "account": "ACC-1",
                "amount_quote": "around £12,000",
                "basis": "viewed_in_meeting",
                "evidence_quote": "pulled it up during the meeting",
            }
        ]
    }
    assert ExpectedFacts.model_validate(data).extraction.value_observations[0].basis == (
        "viewed_in_meeting"
    )
    data["extraction"]["value_observations"][0]["basis"] = "guessed"
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)


def test_investigation_expects_an_answer_or_stays_unresolved() -> None:
    data = minimal()
    data["investigation"] = [
        {"question": "which account is the old cash account", "expected": "ACC-2"},
        {"question": "which of two ISAs is meant", "stays_unresolved": True},
    ]
    facts = ExpectedFacts.model_validate(data)
    assert facts.investigation[1].stays_unresolved

    data["investigation"] = [{"question": "q"}]  # neither an answer nor unresolved
    with pytest.raises(ValidationError):
        ExpectedFacts.model_validate(data)


def test_load_expected_reads_a_named_fixture(tmp_path: Path) -> None:
    (tmp_path / "example_client.json").write_text(json.dumps(minimal()), encoding="utf-8")
    facts = load_expected("example_client", root=tmp_path)
    assert facts.client == "example_client"


def test_load_expected_rejects_a_fixture_named_for_another_client(tmp_path: Path) -> None:
    (tmp_path / "other_client.json").write_text(json.dumps(minimal()), encoding="utf-8")
    with pytest.raises(ValueError, match="other_client"):
        load_expected("other_client", root=tmp_path)
