"""A non-action's text reaches the writer exactly as extracted; the plan never adds a referent.

An extracted action's `accounts` is the account it is tied to, not necessarily what it concerns.
"We agreed to leave this for now", said right after a paper share certificate that relates to one
of two accounts, is tied to that account but concerns the certificate. Naming the account from
`accounts` made the report say the account itself was being left alone, which the meeting note
never says (G8 and P6 failed on all three judge samples). Pronoun-only wording stays vague until the
extractor resolves the referent itself, which is listed under "What I would do with more time"."""

from __future__ import annotations

from agent_pipeline.config import ReportConfig, Section, StageConfig
from agent_pipeline.ledger import Action, Ledger
from agent_pipeline.write.plan import plan_sections


def _texts(*actions: Action) -> dict[str, str]:
    section = Section(
        id="recommendations",
        title="Recommendations",
        use_if="always",
        template="<<recommendation>>",
        text_sources=["actions"],
    )
    config = ReportConfig(
        document_title="Investment Advice Report",
        global_instructions="Write in British English.",
        stages={"write": StageConfig(model="gpt-6-luna", reasoning_effort="low")},
        sections=[section],
    )
    plans = plan_sections(Ledger(client="x", actions=list(actions)), config)
    return plans[0].rewritten_texts


def test_a_pronoun_only_non_action_is_not_annotated_from_its_accounts() -> None:
    description = "We agreed to leave this for now and revisit if it becomes relevant."

    texts = _texts(
        Action(
            id="a2",
            description=description,
            kind="non_action",
            accounts=["one of his General Investment Accounts on Holloway"],
        )
    )

    assert texts["action.a2"] == description


def test_a_real_action_is_not_annotated_from_its_accounts() -> None:
    description = "we agreed to add to it"

    texts = _texts(
        Action(id="a3", description=description, kind="action", accounts=["Holloway joint GIA"])
    )

    assert texts["action.a3"] == description
