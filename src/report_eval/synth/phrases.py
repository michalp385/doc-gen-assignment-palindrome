"""The synthetic clients' phrase bank (D4, DESIGN.md section 10.8): several wordings per pattern
for the facts a meeting note must state in a way extraction can be scored on -- a live viewing,
a recalled figure, a sale, a commitment, a contingency, a precondition -- none copied from the
four real clients. `bank_overlap` is the six-word overlap check between the bank and the real
documents under `data/`, so the synthetic clients don't just re-test the real clients' wording.

Each wording is a `str.format` template. Name and figure pools are sampled elsewhere
(`scenario.py`), so this module holds no client values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.markdown import read_markdown

PHRASE_BANK: dict[str, tuple[str, ...]] = {
    # The meeting date is a required phrase: extraction reads it from here.
    "meeting_open": (
        "Annual review with {names}, which took place on {date}.",
        "Notes from the review appointment with {names} on {date}.",
        "{names} attended their scheduled review on {date}.",
    ),
    # A figure the adviser saw on screen during the meeting: it selects the account's value.
    "live_view": (
        "During the appointment I opened the {account} on screen and it was showing {amount_text}.",
        "I checked the {account} online while we talked, and the balance displayed was "
        "{amount_text}.",
        "Looking at the {account} in real time with {names}, the valuation on the screen read "
        "{amount_text}.",
    ),
    # A figure quoted from memory or old paperwork: it never selects a value.
    "recalled": (
        "{names} believed the {account} was worth {amount_text}, going on what they remembered "
        "from an old letter.",
        "From memory, {names} put the {account} at {amount_text}, though nobody had the current "
        "statement to hand.",
        "{names} quoted {amount_text} for the {account}, which came from paperwork they had "
        "kept at home.",
    ),
    "sale_full": (
        "The decision was to sell the {account} entirely and pass the proceeds to {destination}.",
        "{names} chose to cash in the whole of the {account}, with the money going to "
        "{destination}.",
        "It was settled that the {account} would be sold down completely, and the sale money "
        "directed to {destination}.",
    ),
    "topup": (
        "It was decided to move {amount} out of the {source} and into {destination}.",
        "{names} chose to transfer {amount} from the {source} to {destination}.",
        "The plan agreed is a transfer of {amount}, taken from the {source} and paid to "
        "{destination}.",
    ),
    "no_sale": (
        "Nothing is being sold as part of this advice.",
        "There is no selling of any holding involved in what was agreed.",
        "No existing holding is to be sold under this recommendation.",
    ),
    # Earlier use of the ISA allowance: a confirmed prior-use signal (P4).
    "part_funded": (
        "Both ISAs have already received money this tax year, so only part of the allowance "
        "remains for each.",
        "Money has already gone into the ISAs during the current tax year; the unused part of "
        "the allowance is what is left.",
        "The ISAs were partly funded earlier in the tax year, and the remaining room is limited.",
    ),
    "part_funded_single": (
        "The ISA has already received money this tax year, so only part of the allowance remains.",
        "Money has already gone into the ISA during the current tax year; the unused part of "
        "the allowance is what is left.",
        "The ISA was partly funded earlier in the tax year, and the remaining room is limited.",
    ),
    "received": (
        "{amount} from {origin} has now arrived in the client's bank account.",
        "A payment of {amount} from {origin} has been received and is sitting in cash.",
        "The {amount} due from {origin} has landed, and the client already holds it.",
    ),
    "committed": (
        "Of that money, {amount} is already earmarked for {purpose}.",
        "{amount} of it has been set aside for {purpose} and is not part of what can be invested.",
        "The client has promised {amount} of it towards {purpose}.",
    ),
    "contingent": (
        "A further payment of up to {amount} may follow one day, but none of it has arrived and "
        "nothing has been agreed about it.",
        "There could be up to {amount} more from a pending arrangement; it is uncertain, it has "
        "not been paid, and it forms no part of the plan.",
        "Up to {amount} is possible from a later settlement, though it is not in hand and has "
        "not been discussed as money to use.",
    ),
    "tangent": (
        "{names} spoke about {subject}; this has no relevance to the advice.",
        "In passing, {names} brought up {subject}, which is unconnected with the recommendation.",
        "{names} chatted about {subject}, and it does not affect the advice in any way.",
    ),
    "aspiration": (
        "{names} may later wish to {subject}, but do not want anything done about that now.",
        "One day {names} might like to {subject}; they asked for no action on it at present.",
        "Looking further ahead, {names} could {subject}, though they want it left alone for now.",
    ),
    # A precondition that must be settled before anything is finalised: a blocking open action.
    "precondition_blocking": (
        "Before anything goes ahead, {holder}'s cash account at {platform} must be checked, "
        "because its balance is unknown.",
        "We cannot finalise the plan until {holder}'s {platform} cash account has been looked at, "
        "as no balance is recorded for it.",
        "It is essential to establish the balance of {holder}'s cash account with {platform} "
        "first; nothing is final until then.",
    ),
    # A loose follow-up that does not hold anything up: a non-blocking open action.
    "precondition_soft": (
        "At some stage we should look at {holder}'s cash account with {platform}, whose balance "
        "is not on file.",
        "Separately, someone ought to review {holder}'s {platform} cash account when convenient, "
        "since it shows no balance.",
        "A tidy-up point for later: {holder}'s cash account at {platform} has no recorded balance.",
    ),
    "new_account": (
        "The remaining money is to go into a new joint investment account opened for {names}.",
        "Whatever is left after the ISAs will be used to start a new joint investment account "
        "in the names of {names}.",
        "A new joint investment account for {names} will receive the balance.",
    ),
}


@dataclass(frozen=True)
class RequiredPhrase:
    """A sentence the meeting note must contain verbatim, and the money figures in it (the
    only figures the note may state, D4)."""

    pattern: str
    text: str
    figures: tuple[str, ...] = ()


def render(pattern: str, variant: int, **fields: str) -> str:
    """One wording of a pattern, chosen by `variant` (any integer: wraps around)."""
    wordings = PHRASE_BANK[pattern]
    return wordings[variant % len(wordings)].format(**fields)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


_MAX_FILL = 4  # a placeholder stands for one to four words
_WINDOW = 6
_MIN_FIXED = 4  # a window of mostly placeholders would match anything


def _template_tokens(template: str) -> list[str | None]:
    """A wording as words, with `None` for each `{field}` (its value is sampled)."""
    tokens: list[str | None] = []
    for part in re.split(r"(\{[^}]*\})", template):
        if part.startswith("{") and part.endswith("}"):
            tokens.append(None)
        else:
            tokens.extend(_words(part))
    return tokens


def _matches_at(window: list[str | None], words: list[str], pos: int) -> bool:
    if not window:
        return True
    head, rest = window[0], window[1:]
    if head is None:
        return any(
            _matches_at(rest, words, pos + k)
            for k in range(1, _MAX_FILL + 1)
            if pos + k <= len(words)
        )
    return pos < len(words) and words[pos] == head and _matches_at(rest, words, pos + 1)


def bank_overlap(corpus: list[str], n: int = 6) -> list[tuple[str, tuple[str, ...]]]:
    """Every (pattern, run) where a bank wording shares an n-word run with a corpus document.
    A run may span a placeholder: it counts as one to four words of anything, so a wording
    whose fixed text is broken up by its fields is still compared against the real documents
    as it will read once rendered. Empty means the bank is clear of the corpus."""
    corpus_words = [_words(text) for text in corpus]
    corpus_grams: set[tuple[str, ...]] = set()
    for words in corpus_words:
        corpus_grams |= _ngrams(words, n)
    found: list[tuple[str, tuple[str, ...]]] = []
    for pattern, wordings in PHRASE_BANK.items():
        for wording in wordings:
            tokens = _template_tokens(wording)
            for start in range(len(tokens) - n + 1):
                window = tokens[start : start + n]
                fixed = [t for t in window if t is not None]
                if window[0] is None or len(fixed) < _MIN_FIXED:
                    continue
                shown = tuple(t if t is not None else "*" for t in window)
                if len(fixed) == n:
                    hit = tuple(fixed) in corpus_grams
                else:
                    hit = any(
                        _matches_at(window, words, pos)
                        for words in corpus_words
                        for pos in range(len(words))
                        if words[pos] == window[0]
                    )
                if hit:
                    found.append((pattern, shown))
    return found


def corpus_texts(data_root: Path) -> list[str]:
    """The text of every source document under `data_root` -- the real clients' notes,
    requests, guidance and general documents, and the hand-written cases' -- except the report
    spec, which is the requirement the phrases serve, not a client source."""
    texts: list[str] = []
    for path in sorted(data_root.rglob("*")):
        if path.name == "template_spec.md":
            continue
        if path.suffix == ".docx":
            doc = read_docx(path)
            texts.append(" ".join(doc.paragraphs.values()))
            for table in doc.tables:
                texts.append(" ".join(" ".join(row) for row in table))
        elif path.suffix == ".md":
            texts.append(" ".join(read_markdown(path).paragraphs.values()))
    return texts
