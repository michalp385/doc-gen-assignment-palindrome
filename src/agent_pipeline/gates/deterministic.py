"""Deterministic gates (SCOPING.md section 2.1, DESIGN.md section 8.1): whether an
assembled draft actually reflects its `Truth` (gates/truth.py). Stage 7 runs every gate
here on the real draft (`truth` = the ledger); the eval and `tests/test_gate_mutations.py`
run the same functions with `truth` = a client's expected facts. One `_check_g<n>` function
per gate, cited by number, so nothing here has to be re-derived from prose at review time.

Scope (the plan's T9 line): G1, G2 (list check), G3, G4 (exact-and-once plus a *provisional*
paraphrase threshold -- DESIGN says real calibration is T25's job), G5, G6, G9, G10, G11, G12
(deterministic slice only), G13, G14, G15, and P6's at-most-once rule. G7, G8 and G16 are
judge territory or not in T9's list, and are not implemented here.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from agent_pipeline.gates.truth import Truth
from agent_pipeline.ledger import Ledger

# Must match scripts/check_repo.py's copies exactly; duplicated intentionally, since that
# script has to run standalone, dependency-free of the package it's checking. T10's
# config/base.json becomes the single real source for the pipeline's own copy.
FCA_LINE = "This firm is authorised and regulated by the Financial Conduct Authority."
RISK_WARNING = (
    "The value of investments can fall as well as rise and you may get back less than you invest."
)
RISK_WARNING_2 = "Past performance is not a guide to future returns."
RISK_WARNING_FULL = f"{RISK_WARNING} {RISK_WARNING_2}"

TABLE_HEADER = "| Account | Owner | Type | Value |"

_PARAPHRASE_THRESHOLD = 0.6  # provisional (DESIGN section 8.1); real calibration is T25's job


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class TableRow:
    account_id: str
    owners: list[str]
    value_text: str


@dataclass(frozen=True)
class ReportBundle:
    report_text: str
    sections: dict[str, str] = field(default_factory=dict)
    table_rows: list[TableRow] = field(default_factory=list)
    ledger: Ledger = field(default_factory=lambda: Ledger(client=""))
    internal_guidance_text: str = ""
    meeting_text: str = ""
    spec_text: str = ""


def _split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", text)


def _word_ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = re.findall(r"[A-Za-z']+", text.lower())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


_MONEY_RE = re.compile(r"£\s?\d[\d,]*(?:\.\d+)?k?\b")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?%")
_NUMBER_WORDS = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|thousand|million)"
)
_WORD_FIGURE_RE = re.compile(rf"(?:{_NUMBER_WORDS}[\s-]+)+{_NUMBER_WORDS}\s+pounds", re.IGNORECASE)


def _check_g1(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G1: the table is exactly the in-scope accounts, each appearing once, owners named."""
    seen_ids = [row.account_id for row in bundle.table_rows]
    if len(seen_ids) != len(set(seen_ids)):
        dupes = sorted({i for i in seen_ids if seen_ids.count(i) > 1})
        return GateResult("G1", False, f"account listed more than once: {dupes}")
    expected = {a.id: a for a in truth.table_accounts()}
    actual_ids = set(seen_ids)
    if actual_ids != set(expected):
        missing = sorted(set(expected) - actual_ids)
        extra = sorted(actual_ids - set(expected))
        return GateResult("G1", False, f"missing {missing}, unexpected {extra}")
    for row in bundle.table_rows:
        exp = expected[row.account_id]
        if sorted(row.owners) != sorted(exp.owners):
            return GateResult(
                "G1", False, f"{row.account_id}: owners {row.owners} != expected {exp.owners}"
            )
    return GateResult("G1", True)


def _check_g2(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G2: every money/percent figure in the report is a reportable figure for this client."""
    if m := _WORD_FIGURE_RE.search(bundle.report_text):
        return GateResult("G2", False, f"figure written in words: {m.group(0)!r}")
    allowed = truth.reportable_figures()
    found = {re.sub(r"£\s+", "£", f) for f in _MONEY_RE.findall(bundle.report_text)}
    found |= set(_PERCENT_RE.findall(bundle.report_text))
    extra = sorted(found - allowed)
    if extra:
        return GateResult("G2", False, f"figure(s) not in the reportable set: {extra}")
    return GateResult("G2", True)


_RATE_KEYWORDS = ("platform charge", "advice charge", "cgt", "capital gains tax")
_FIGURE_NEAR_RE = re.compile(r"£\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?%")


def _check_g3(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G3: CGT/platform/advice-charge rates never appear as figures, only as markers.

    Scoped to one sentence at a time, not a raw character window: a character window bleeds
    across sentence and section boundaries (e.g. an unrelated "(0%)" landing near the start
    of the next sentence's "platform charge" would otherwise false-fire).
    """
    for sentence in _split_sentences(bundle.report_text):
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in _RATE_KEYWORDS) and _FIGURE_NEAR_RE.search(
            sentence
        ):
            return GateResult("G3", False, f"a figure with a charge/CGT keyword: {sentence!r}")
    return GateResult("G3", True)


def _check_g4(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G4: the FCA line and risk warning appear verbatim, exactly once each; no paraphrase."""
    fca_count = bundle.report_text.count(FCA_LINE)
    if fca_count != 1:
        return GateResult("G4", False, f"FCA line appears {fca_count} times, expected exactly 1")
    warning_count = bundle.report_text.count(RISK_WARNING_FULL)
    if warning_count != 1:
        return GateResult(
            "G4", False, f"risk warning appears {warning_count} times, expected exactly 1"
        )
    for sentence in _split_sentences(bundle.report_text):
        stripped = sentence.strip()
        if not stripped or stripped in (FCA_LINE, RISK_WARNING, RISK_WARNING_2):
            continue
        for target in (FCA_LINE, RISK_WARNING_FULL):
            ratio = difflib.SequenceMatcher(None, stripped, target).ratio()
            if ratio > _PARAPHRASE_THRESHOLD:
                return GateResult("G4", False, f"possible paraphrase of static text: {stripped!r}")
    return GateResult("G4", True)


def _check_g5(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G5: Tax Implications is present iff a taxable disposal is expected."""
    present = "tax_implications" in bundle.sections
    expected = truth.tax_section_expected()
    if present != expected:
        return GateResult("G5", False, f"tax section present={present}, expected={expected}")
    return GateResult("G5", True)


def _check_g6(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G6: each account shows the trust rules' selected value, rendered correctly."""
    expected = {a.id: a for a in truth.table_accounts()}
    for row in bundle.table_rows:
        exp = expected.get(row.account_id)
        if exp is None:
            continue  # an unexpected row is G1's concern, not G6's
        if row.value_text != exp.value_text:
            return GateResult(
                "G6",
                False,
                f"{row.account_id}: shows {row.value_text!r}, expected {exp.value_text!r}",
            )
    return GateResult("G6", True)


def _check_g9(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G9: Background contains no transaction amounts (top-ups, proceeds, tax figures)."""
    background = bundle.sections.get("background_objectives", "")
    for figure in sorted(truth.transaction_figures()):
        if figure and figure in background:
            return GateResult("G9", False, f"transaction amount {figure!r} appears in Background")
    return GateResult("G9", True)


def _check_g10(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G10: internal guidance text never appears in the report (n-gram screen)."""
    guidance_grams = _word_ngrams(bundle.internal_guidance_text, 6)
    excluded = _word_ngrams(bundle.meeting_text, 6) | _word_ngrams(bundle.spec_text, 6)
    screened = guidance_grams - excluded
    overlap = screened & _word_ngrams(bundle.report_text, 6)
    if overlap:
        sample = " ".join(next(iter(overlap)))
        return GateResult("G10", False, f"internal guidance text found in report: {sample!r}")
    return GateResult("G10", True)


def _check_g11(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G11: each section holds only its own content; the account table appears once."""
    table_count = bundle.report_text.count(TABLE_HEADER)
    if table_count != 1:
        return GateResult("G11", False, f"account table appears {table_count} times, expected 1")
    for name, text in bundle.sections.items():
        if name != "conclusion" and RISK_WARNING_FULL in text:
            return GateResult("G11", False, f"risk warning appears in {name!r}, not Conclusion")
        if name != "introduction" and FCA_LINE in text:
            return GateResult("G11", False, f"FCA line appears in {name!r}, not Introduction")
        if name != "background_objectives" and TABLE_HEADER in text:
            return GateResult("G11", False, f"account table appears in {name!r}, not Background")
    return GateResult("G11", True)


_DOUBLE_STOP_RE = re.compile(r"\.\s*\.")
_MIDSENTENCE_CAP_RE = re.compile(r"[a-z]\s+(?:This report|That report|The report)\b")


def _check_g12(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G12 (deterministic slice): a placeholder substitution left ungrammatical text --
    a capitalised sentence starting abruptly mid-sentence, or a double full stop."""
    if _DOUBLE_STOP_RE.search(bundle.report_text):
        return GateResult("G12", False, "double full stop found")
    if m := _MIDSENTENCE_CAP_RE.search(bundle.report_text):
        return GateResult("G12", False, f"capitalised sentence starts mid-sentence: {m.group(0)!r}")
    return GateResult("G12", True)


def _check_g13(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G13: risk profile, initial charge and client names match verbatim; new accounts
    show 'To be opened'."""
    risk = truth.risk_profile()
    if risk and risk not in bundle.report_text:
        return GateResult("G13", False, f"risk profile {risk!r} not found verbatim")
    charge = truth.initial_charge()
    if charge and charge not in bundle.report_text:
        return GateResult("G13", False, f"initial charge {charge!r} not found verbatim")
    for name in sorted(truth.client_names()):
        if name not in bundle.report_text:
            return GateResult("G13", False, f"client name {name!r} not found verbatim")
    expected_new = {a.id for a in truth.table_accounts() if a.is_new}
    for row in bundle.table_rows:
        if row.account_id in expected_new and row.value_text != "To be opened":
            return GateResult(
                "G13", False, f"{row.account_id}: new account not shown as 'To be opened'"
            )
    return GateResult("G13", True)


def _check_g14(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G14: every expected marker is present; nothing the sources settle carries one."""
    required = {m.key: m for m in truth.required_markers()}
    actual = {m.key: m for m in bundle.ledger.markers}
    missing = sorted(set(required) - set(actual))
    if missing:
        return GateResult("G14", False, f"missing required marker(s): {missing}")
    extra = sorted(set(actual) - set(required))
    if extra:
        return GateResult("G14", False, f"marker for a settled fact: {extra}")
    return GateResult("G14", True)


def _check_g15(bundle: ReportBundle, truth: Truth) -> GateResult:
    """G15: the review sheet has every expected item, and every marker has a matching row."""
    for spec in truth.expected_review_items():
        match = next(
            (
                r
                for r in bundle.ledger.review
                if r.kind == spec.kind
                and r.blocking == spec.blocking
                and all(term in r.detail for term in spec.must_mention)
            ),
            None,
        )
        if match is None:
            return GateResult("G15", False, f"missing review item: {spec.key} ({spec.kind})")
    marker_keys = {m.key for m in bundle.ledger.markers}
    referenced = {ref for r in bundle.ledger.review for ref in r.refs}
    orphaned = sorted(marker_keys - referenced)
    if orphaned:
        return GateResult("G15", False, f"marker(s) without a review row: {orphaned}")
    return GateResult("G15", True)


def _check_p6(bundle: ReportBundle, truth: Truth) -> GateResult:
    """P6: an aspiration's subject appears at most once, and only in Background."""
    for subject in sorted(truth.excluded_item_subjects()):
        total = sum(text.count(subject) for text in bundle.sections.values())
        if total > 1:
            return GateResult("P6", False, f"{subject!r} appears {total} times, expected at most 1")
        outside = sum(
            text.count(subject)
            for name, text in bundle.sections.items()
            if name != "background_objectives"
        )
        if outside:
            return GateResult("P6", False, f"{subject!r} appears outside Background")
    return GateResult("P6", True)


_GATES: dict[str, Callable[[ReportBundle, Truth], GateResult]] = {
    "G1": _check_g1,
    "G2": _check_g2,
    "G3": _check_g3,
    "G4": _check_g4,
    "G5": _check_g5,
    "G6": _check_g6,
    "G9": _check_g9,
    "G10": _check_g10,
    "G11": _check_g11,
    "G12": _check_g12,
    "G13": _check_g13,
    "G14": _check_g14,
    "G15": _check_g15,
    "P6": _check_p6,
}


def run_gates(bundle: ReportBundle, truth: Truth) -> list[GateResult]:
    return [fn(bundle, truth) for fn in _GATES.values()]
