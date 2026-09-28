"""T19: `split_sentences` must not treat `render_table`'s "c. " prefix as a sentence
boundary -- a naive `(?<=[.!?])\\s+` split severs "...of c." from "£45,000..." mid-sentence,
which broke G16's clause coverage for client 02's Recommendations text (the only client
whose approximate figure sits mid-sentence rather than at the very start of one)."""

from __future__ import annotations

from agent_pipeline.gates.deterministic import split_sentences


def test_c_prefix_mid_sentence_is_not_a_sentence_boundary() -> None:
    text = "We recommend using the gross proceeds of c. £45,000 to top up the ISAs."
    sentences = split_sentences(text)
    assert sentences == [text]


def test_a_real_sentence_boundary_still_splits() -> None:
    text = "This is one sentence. This is another sentence."
    assert split_sentences(text) == ["This is one sentence.", "This is another sentence."]


def test_a_sentence_ending_right_after_a_c_prefixed_figure_still_splits() -> None:
    # "c. £45,000." is the account table's own value cell, not a sentence -- but a real
    # sentence ending in an approximate figure (e.g. "...worth c. £45,000. We recommend...")
    # must still split at the second period, only the first ("c.") is protected.
    text = "Your account is worth c. £45,000. We recommend keeping it invested."
    assert split_sentences(text) == [
        "Your account is worth c. £45,000.",
        "We recommend keeping it invested.",
    ]
