"""The release judge (DESIGN.md section 8.2, stage 7): one structured call covering the
gates only a model can check -- G16 (claim support, sentence coverage enforced in code), G8
(agreed-action coverage), and simple pass/fail findings for G2's role check, G4/G10
paraphrase, G7 and P6's judge part (G12's judge part folds into the same findings list).

This evaluates one draft; it does not retry the writer. The cross-stage repair loop ("if the
judge finds a problem in one section, that section gets one repair round, then gates and
judge re-run once") needs real stage orchestration and is `pipeline.py`'s job (T16).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import BaseModel

from agent_pipeline.config import PromptSpec
from agent_pipeline.extract.quotes import Verified, verify_quote
from agent_pipeline.gates.deterministic import (
    MONEY_RE,
    PERCENT_RE,
    GateResult,
    ReportBundle,
    split_sentences,
)
from agent_pipeline.ledger import Ledger
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.document import SourceDoc
from agent_pipeline.write.table import build_table

_SIMPLE_GATES = ("G2", "G4", "G7", "G10", "G12", "P6")


class JudgeMaterialClaim(BaseModel):
    claim: str
    report_quote: str  # the report's own sentence/phrase this claim supports
    source_id: str  # a key into the `sources` mapping, e.g. "meeting_notes.docx"
    paragraph_id: str
    quote: str  # the source's exact backing quote


class JudgeActionCoverage(BaseModel):
    action_id: str
    report_quote: str | None = None  # null = the judge can't find it covered (a G8 finding)


class JudgeRecommendationMapping(BaseModel):
    report_quote: str  # a sentence from Recommendations
    action_id: str | None = None  # null = implements no agreed action (a G8 finding)


class JudgeFinding(BaseModel):
    gate: Literal["G2", "G4", "G7", "G10", "G12", "P6"]
    detail: str
    quote: str | None = None


class RawJudgeVerdict(BaseModel):
    """The model's own output schema. No entry in `findings` for a gate means that gate's
    judge part passes; the deterministic part of that same gate (already in
    `gates/deterministic.py`) runs separately and is unaffected by this verdict."""

    material_claims: list[JudgeMaterialClaim]
    action_coverage: list[JudgeActionCoverage]
    recommendation_mappings: list[JudgeRecommendationMapping]
    findings: list[JudgeFinding]


class JudgeModel(Protocol):
    def judge(
        self,
        bundle: ReportBundle,
        ledger: Ledger,
        sources: Mapping[str, SourceDoc],
        corrections: list[str],
    ) -> RawJudgeVerdict: ...


class LLMJudgeModel:
    """The real `JudgeModel`, wrapping T11's `LLMClient` and `config/prompts/release_judge.md`."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def judge(
        self,
        bundle: ReportBundle,
        ledger: Ledger,
        sources: Mapping[str, SourceDoc],
        corrections: list[str],
    ) -> RawJudgeVerdict:
        result = self._llm.structured(
            stage="release_judge",
            prompt=self._prompt,
            inputs={
                "report_text": bundle.report_text,
                "actions": [
                    {"id": a.id, "description": a.description, "kind": a.kind}
                    for a in ledger.actions
                ],
                "sources": {
                    source_id: [f"[{pid}] {text}" for pid, text in doc.paragraphs.items()]
                    for source_id, doc in sources.items()
                },
                "corrections": corrections,
            },
            schema=RawJudgeVerdict,
        )
        return result.output


_TAX_TERM_RE = re.compile(r"\btax\b|\bcgt\b|capital gains", re.IGNORECASE)


def _requires_coverage(text: str, ledger: Ledger) -> bool:
    """G16: text containing a filled fact token (now a real figure), an account name or
    type, or a tax term must map to at least one claim (DESIGN.md section 8.2).

    Three spans are exempt, all T19, client 02's checkpoint -- none can ever pass coverage
    by construction, not because a judge missed something: a claim's quote is verified
    against a *source document* (`verify_quote`), and none of these is drawn from one.
    - The account table (with its footnote): synthesised straight from the ledger (G1/G6
      already check it deterministically), never any one source document.
    - "The initial charge that applies is <value>.": a fixed template sentence
      (config/base.json), the value inserted by a *computed* placeholder, never the model
      (G13 already checks it matches the instruction verbatim).
    - A marker's own bracket text ("[ADVISER TO CONFIRM #n: ...]"): inserted by code from
      the ledger (P1), never typed by the model (G14 already checks every marker exists and
      maps to a review row) -- a sentence built around one, like the CGT marker's own
      sentence in Tax Implications, needing a *claim* makes no sense: there is nothing for
      a source document to back, the whole point of a marker is that no source states it."""
    table = build_table(ledger)
    if text.strip() and text.strip() in table:
        return False
    if (
        ledger.initial_charge
        and text.strip() == f"The initial charge that applies is {ledger.initial_charge}."
    ):
        return False
    if "[ADVISER TO CONFIRM" in text:
        return False
    if MONEY_RE.search(text) or PERCENT_RE.search(text):
        return True
    if _TAX_TERM_RE.search(text):
        return True
    return any(account.id in text or account.type in text for account in ledger.accounts)


_CLAUSE_SPLIT_RE = re.compile(r"\s*(?<!\d),(?!\d)\s*|\s*;\s*")


def _clauses(sentence: str) -> list[str]:
    """Coverage is checked per clause, not per whole sentence: checking only that *some*
    claim's quote appears *somewhere* in the sentence let a fabricated fact spliced onto a
    genuinely-covered one via a comma ride along uncovered, reusing the real fact's own
    figure so the fabrication read as already-supported (verifier report, T15 checkpoint,
    second FAIL). Splitting on comma/semicolon means the fabricated clause has to earn its
    own claim; a claim's `report_quote` spanning more than one clause no longer fits inside
    either one, so it stops counting as covering any of them (this is deliberate, not a
    regression -- DESIGN.md section 8.2 wants one claim per fact, not one claim borrowed
    across several)."""
    return [c for c in _CLAUSE_SPLIT_RE.split(sentence) if c.strip()]


def _clause_covered(clause: str, claims: list[JudgeMaterialClaim]) -> bool:
    """A claim covers a clause only if its own `report_quote` sits *inside* that specific
    clause -- never the reverse, which would let one oversized quote cover several clauses
    at once (verifier report, T15 checkpoint, first FAIL, finding #1)."""
    stripped = clause.strip()
    return any(c.report_quote in stripped for c in claims)


def _verify_claims(
    claims: list[JudgeMaterialClaim], sources: Mapping[str, SourceDoc], report_text: str
) -> list[JudgeMaterialClaim]:
    verified = []
    for claim in claims:
        if claim.report_quote not in report_text:
            continue  # the claim doesn't even point at real report text
        doc = sources.get(claim.source_id)
        if doc is None:
            continue
        if isinstance(verify_quote(doc, claim.paragraph_id, claim.quote), Verified):
            verified.append(claim)
    return verified


def _coverage_scan_text(bundle: ReportBundle) -> str:
    """G16 scans generated section content, not the fully assembled `report_text` -- a
    heading never carries a claim of its own, and `bundle.sections` holds each section's
    own content without the "## <title>" markdown `document_formatter/formatting.py` adds
    (T19, client 02's checkpoint: a bare "## Tax Implications" heading was being flagged as
    an uncovered claim, which it structurally can never be). Every section's real content,
    tax_implications included, still needs real coverage -- a fabricated CGT figure planted
    there must still be caught (`test_g16_cannot_be_gamed_...`, T15 checkpoint)."""
    return "\n\n".join(bundle.sections.values())


def _uncovered_clauses(
    report_text: str, ledger: Ledger, claims: list[JudgeMaterialClaim]
) -> list[str]:
    return [
        clause.strip()
        for sentence in split_sentences(report_text)
        for clause in _clauses(sentence)
        if _requires_coverage(clause, ledger) and not _clause_covered(clause, claims)
    ]


def _check_g16(
    raw: RawJudgeVerdict,
    model: JudgeModel,
    bundle: ReportBundle,
    ledger: Ledger,
    sources: Mapping[str, SourceDoc],
) -> tuple[GateResult, RawJudgeVerdict]:
    verified = _verify_claims(raw.material_claims, sources, bundle.report_text)
    uncovered = _uncovered_clauses(_coverage_scan_text(bundle), ledger, verified)

    if uncovered:
        correction = "these clauses have no supporting claim yet, add one for each: " + "; ".join(
            repr(c) for c in uncovered
        )
        raw = model.judge(bundle, ledger, sources, [correction])
        verified = _verify_claims(raw.material_claims, sources, bundle.report_text)
        uncovered = _uncovered_clauses(_coverage_scan_text(bundle), ledger, verified)

    unsupported = [c for c in raw.material_claims if c not in verified]
    if unsupported:
        return (
            GateResult("G16", False, f"unsupported claim(s): {[c.claim for c in unsupported]}"),
            raw,
        )
    if uncovered:
        return GateResult("G16", False, f"uncovered clause(s): {uncovered}"), raw
    return GateResult("G16", True), raw


def _check_g8(raw: RawJudgeVerdict, bundle: ReportBundle, ledger: Ledger) -> GateResult:
    recommendations_text = bundle.sections.get("recommendations", "")
    known_action_ids = {a.id for a in ledger.actions}
    coverage_by_id = {c.action_id: c for c in raw.action_coverage}
    # A quote used to cover one action can't also cover a different one -- otherwise a
    # single real quote can rubber-stamp an action that was never actually recommended
    # (verifier report, T15 checkpoint, finding #2).
    action_id_by_quote: dict[str, str] = {}
    for action in ledger.actions:
        coverage = coverage_by_id.get(action.id)
        if coverage is None or coverage.report_quote is None:
            return GateResult("G8", False, f"agreed action not covered: {action.id}")
        if coverage.report_quote not in recommendations_text:
            return GateResult(
                "G8",
                False,
                f"quote for {action.id} not in Recommendations: {coverage.report_quote!r}",
            )
        prior_action_id = action_id_by_quote.get(coverage.report_quote)
        if prior_action_id is not None:
            return GateResult(
                "G8",
                False,
                f"same quote covers both {prior_action_id!r} and {action.id!r}: "
                f"{coverage.report_quote!r}",
            )
        action_id_by_quote[coverage.report_quote] = action.id
    for mapping in raw.recommendation_mappings:
        if mapping.report_quote not in recommendations_text:
            return GateResult(
                "G8",
                False,
                f"recommendation quote not in Recommendations: {mapping.report_quote!r}",
            )
        if mapping.action_id is None:
            return GateResult(
                "G8",
                False,
                f"recommendation not tied to an agreed action: {mapping.report_quote!r}",
            )
        if mapping.action_id not in known_action_ids:
            return GateResult(
                "G8", False, f"recommendation maps to an unknown action id: {mapping.action_id!r}"
            )
    return GateResult("G8", True)


def _check_simple_gates(raw: RawJudgeVerdict) -> list[GateResult]:
    findings_by_gate: dict[str, JudgeFinding] = {}
    for finding in raw.findings:
        findings_by_gate.setdefault(finding.gate, finding)
    results = []
    for gate in _SIMPLE_GATES:
        finding = findings_by_gate.get(gate)
        if finding is None:
            results.append(GateResult(gate, True))
        else:
            detail = (
                finding.detail if finding.quote is None else f"{finding.detail} ({finding.quote!r})"
            )
            results.append(GateResult(gate, False, detail))
    return results


def release_judge(
    bundle: ReportBundle,
    ledger: Ledger,
    sources: Mapping[str, SourceDoc],
    model: JudgeModel,
) -> list[GateResult]:
    raw = model.judge(bundle, ledger, sources, [])
    g16, raw = _check_g16(raw, model, bundle, ledger, sources)
    return [g16, _check_g8(raw, bundle, ledger), *_check_simple_gates(raw)]
