"""The per-slot writer loop (DESIGN.md section 8.1 stage 5, D1, D6): one model call per
generated placeholder, returning only `{fact:<id>}`/`{marker:<key>}` tokens for IDs in its
plan -- never a typed digit. Code checks the raw draft (invented tokens, digit-free, every
required marker exactly once, then the slot-level deterministic gates) before substituting
figures in; a failure is fed back verbatim as the next round's correction. A slot still
failing after 2 repairs stops the run (DESIGN section 8.4: writing is a required stage,
never a silent drop).
"""

from __future__ import annotations

import dataclasses
import difflib
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from agent_pipeline.config import PromptSpec, Section
from agent_pipeline.gates.deterministic import (
    DOUBLE_STOP_RE,
    FCA_LINE,
    MIDSENTENCE_CAP_RE,
    PARAPHRASE_THRESHOLD,
    RISK_WARNING,
    RISK_WARNING_2,
    RISK_WARNING_FULL,
    TABLE_HEADER,
    WORD_FIGURE_RE,
    WORD_PERCENT_RE,
    split_sentences,
    word_ngrams,
)
from agent_pipeline.gates.judge import intro_scope_problems
from agent_pipeline.ledger import Ledger
from agent_pipeline.llm import LLMClient
from agent_pipeline.write.schemas import SectionPlan
from agent_pipeline.write.tokens import TOKEN_RE, fill_tokens

MAX_ROUNDS = 3


class RawSlotDraft(BaseModel):
    paragraphs: list[str]


class WriterModel(Protocol):
    def write(self, plan: SectionPlan, corrections: list[str]) -> RawSlotDraft: ...


class LLMWriterModel:
    """The real `WriterModel` for one generated slot, wrapping T11's `LLMClient` and that
    slot's own `config/prompts/write_<slot>.md`. One instance per placeholder (D6): the
    caller binds the right prompt, `write_slot` never chooses one itself."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def write(self, plan: SectionPlan, corrections: list[str]) -> RawSlotDraft:
        result = self._llm.structured(
            stage="write",
            prompt=self._prompt,
            inputs={
                "spec_text": plan.spec_text,
                "facts": [dataclasses.asdict(fact) for fact in plan.facts],
                "markers": [dataclasses.asdict(marker) for marker in plan.markers],
                "context": plan.context,
                "rewritten_texts": plan.rewritten_texts,
                "corrections": corrections,
                # Only when there is one, so a section with no directive keeps its cache key.
                **({"handling": plan.handling} if plan.handling else {}),
            },
            schema=RawSlotDraft,
        )
        return result.output


@dataclass(frozen=True)
class SlotDraft:
    section_id: str
    filled_text: str
    repairs_used: int


class WriterStopError(Exception):
    """A slot still fails its gates after 2 repair rounds -- writing is a required stage
    (DESIGN.md section 8.4); an exhausted slot stops the run, never a silent drop."""


class WriterConfigError(Exception):
    """A section's config doesn't have exactly one generated placeholder -- write_slot has
    no slot to write, so this is a config mistake, not a per-attempt writer failure."""


_MARKDOWN_ARTIFACT_RE = re.compile(r"^\s*(?:\|.*\||#{1,6}\s)", re.MULTILINE)


def _generated_placeholder_name(section: Section) -> str:
    generated = [name for name, p in section.placeholders.items() if p.kind == "generated"]
    if len(generated) != 1:
        raise WriterConfigError(
            f"section {section.id!r} has {len(generated)} generated placeholder(s), expected 1"
        )
    return generated[0]


def _check_invented_tokens(text: str, plan: SectionPlan) -> str | None:
    known_facts = {fact.id for fact in plan.facts}
    known_markers = {marker.key for marker in plan.markers}
    for match in TOKEN_RE.finditer(text):
        kind, name = match.group(1), match.group(2)
        if kind == "fact" and name not in known_facts:
            return f"invented fact token {{fact:{name}}}: not in this section's plan"
        if kind == "marker" and name not in known_markers:
            return f"invented marker token {{marker:{name}}}: not in this section's plan"
    return None


def _check_digit_free(text: str) -> str | None:
    stripped = TOKEN_RE.sub("", text)
    if m := re.search(r"\d", stripped):
        return f"a digit appears outside a token: {m.group(0)!r} in {stripped!r}"
    if m := WORD_FIGURE_RE.search(stripped):
        return f"a money figure written in words: {m.group(0)!r}"
    if m := WORD_PERCENT_RE.search(stripped):
        return f"a percentage written in words: {m.group(0)!r}"
    return None


def _check_required_markers(text: str, plan: SectionPlan) -> str | None:
    for marker in plan.markers:
        count = text.count(f"{{marker:{marker.key}}}")
        if count != 1:
            return f"marker {{marker:{marker.key}}} appears {count} times, expected exactly 1"
    return None


def _check_g4_paraphrase(text: str) -> str | None:
    for sentence in split_sentences(text):
        stripped = sentence.strip()
        if not stripped or stripped in (FCA_LINE, RISK_WARNING, RISK_WARNING_2):
            continue
        for target in (FCA_LINE, RISK_WARNING_FULL):
            ratio = difflib.SequenceMatcher(None, stripped, target).ratio()
            if ratio > PARAPHRASE_THRESHOLD:
                return f"possible paraphrase of static text: {stripped!r}"
    return None


def _check_g9_no_transaction_facts(text: str, plan: SectionPlan, section: Section) -> str | None:
    if section.id != "background_objectives":
        return None
    facts_by_id = {fact.id: fact for fact in plan.facts}
    for match in TOKEN_RE.finditer(text):
        if match.group(1) != "fact":
            continue
        fact = facts_by_id.get(match.group(2))
        if fact is not None and fact.transaction:
            return f"transaction fact {{fact:{fact.id}}} used in Background"
    return None


def _check_g10_no_guidance_leak(text: str, plan: SectionPlan, guidance_text: str) -> str | None:
    """DESIGN.md section 8.1: n-grams shared with internal guidance, excluding any 6-gram
    that also occurs in the meeting record or the spec (legitimate shared facts and
    vocabulary) -- both, not just the spec, or a meeting-derived phrase that happens to
    overlap the guidance's own wording gets wrongly rejected as a leak."""
    if not guidance_text:
        return None
    guidance_grams = word_ngrams(guidance_text, 6)
    excluded = word_ngrams(plan.spec_text, 6) | word_ngrams(plan.meeting_text, 6)
    overlap = (guidance_grams - excluded) & word_ngrams(text, 6)
    if overlap:
        sample = " ".join(next(iter(overlap)))
        return f"internal guidance text found in slot: {sample!r}"
    return None


def _check_g11_no_structure(text: str) -> str | None:
    if TABLE_HEADER in text:
        return "account table markup found in a generated slot"
    if m := _MARKDOWN_ARTIFACT_RE.search(text):
        return f"markdown table/heading markup found in a generated slot: {m.group(0)!r}"
    return None


def _proper_nouns(ledger: Ledger) -> frozenset[str]:
    """The names a slot may legitimately start with: each account holder's first name and each
    platform, lower-cased. From the ledger, so no client name lives in code."""
    names = {o.split()[0].lower() for a in ledger.accounts for o in a.owners if o.split()}
    names |= {a.platform.lower() for a in ledger.accounts if a.platform}
    return frozenset(names)


def _starts_with_a_name(text: str, proper_nouns: frozenset[str]) -> bool:
    """Whether the slot's first word is a name it may capitalise: a client's first name or a
    platform the ledger knows (lower-cased), possessive or not."""
    first = re.match(r"[\w-]+", text)
    return first is not None and first.group(0).lower() in proper_nouns


def _check_g12_pre(
    section: Section,
    placeholder_name: str,
    text: str,
    proper_nouns: frozenset[str] = frozenset(),
) -> str | None:
    """Template-aware, not a general grammar scan: only the placeholder's own immediate
    boundary in `section.template` is inspected. A run of whitespace before the placeholder
    (including a paragraph break) is a same-sentence continuation only if the nearest real
    character before it is itself a lowercase letter -- a period (a fresh paragraph/sentence)
    is not, so a slot starting a new sentence is never wrongly forced to start lowercase."""
    marker = f"<<{placeholder_name}>>"
    idx = section.template.find(marker)
    if idx == -1:
        return None
    stripped_before = section.template[:idx].rstrip()
    continues_lowercase = bool(stripped_before) and stripped_before[-1].islower()
    if continues_lowercase and text[:1].isupper() and not _starts_with_a_name(text, proper_nouns):
        return "slot text starts capitalised where the template continues a lowercase sentence"
    following_idx = idx + len(marker)
    following = section.template[following_idx] if following_idx < len(section.template) else ""
    if following == "." and text.rstrip().endswith("."):
        return "slot text ends with a full stop where the template already adds one"
    return None


def _check_g12_post(text: str) -> str | None:
    if DOUBLE_STOP_RE.search(text):
        return "double full stop found after substitution"
    if m := MIDSENTENCE_CAP_RE.search(text):
        return f"capitalised sentence starts mid-sentence after substitution: {m.group(0)!r}"
    return None


def _check_intro_scope(section: Section, text: str, ledger: Ledger) -> str | None:
    """The Introduction's scope sentence is checked against the ledger in code (G16's own
    check), here in the writer so a wrong count or a missing type is repaired in the slot's
    repair rounds, not found later as a failed generation."""
    if section.id != "introduction":
        return None
    problems = intro_scope_problems(text, ledger)
    return "; ".join(problems) if problems else None


def write_slot(
    plan: SectionPlan,
    section: Section,
    ledger: Ledger,
    model: WriterModel,
    *,
    guidance_text: str,
) -> SlotDraft:
    """`guidance_text` has no default: G10 (no internal-guidance leak) is meant to run at
    this stage (DESIGN.md section 8.1), so a caller must pass the real text (or an explicit
    `""` if there genuinely is none) rather than silently disabling the check by omission.

    There's no separate G3 check here (CGT/charge figures never appearing as report text):
    `_check_digit_free` already bans every digit outside a token, and `fees_charges`/
    `tax_implications` never carry a fee/CGT amount as a `Fact` in the first place (only as
    a marker) -- reconcile never creates one, so G3 can't structurally fire at this stage.
    """
    placeholder_name = _generated_placeholder_name(section)
    corrections: list[str] = []

    for attempt in range(MAX_ROUNDS):
        raw = model.write(plan, corrections)
        text = "\n\n".join(raw.paragraphs)

        failure = (
            _check_invented_tokens(text, plan)
            or _check_digit_free(text)
            or _check_required_markers(text, plan)
            or _check_g4_paraphrase(text)
            or _check_g9_no_transaction_facts(text, plan, section)
            or _check_g10_no_guidance_leak(text, plan, guidance_text)
            or _check_g11_no_structure(text)
            or _check_g12_pre(
                section,
                placeholder_name,
                text,
                # Every round is judged as it always was; a name is accepted only when the
                # model has used its repair rounds and still starts with one.
                _proper_nouns(ledger) if attempt == MAX_ROUNDS - 1 else frozenset(),
            )
        )
        if failure is not None:
            corrections.append(failure)
            continue

        filled = fill_tokens(text, ledger)
        failure = _check_g12_post(filled) or _check_intro_scope(section, filled, ledger)
        if failure is not None:
            corrections.append(failure)
            continue

        return SlotDraft(section_id=section.id, filled_text=filled, repairs_used=attempt)

    raise WriterStopError(
        f"section {section.id!r} still fails its gates after {MAX_ROUNDS - 1} repair round(s): "
        f"{corrections[-1]}"
    )
