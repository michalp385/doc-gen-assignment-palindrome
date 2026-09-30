"""The eval results-file schema and writer (DESIGN.md section 10.4): commit, dirty flag,
config hash, prompt versions, models per stage, per-client per-gate results, extraction and
investigation scores, Q1-Q6 scores, tokens, cost, cache hits vs live, and, per client group,
the issued rate, release-state match rate and wrongly-issued count. Every metric quoted in
docs must be read from one of these files, never typed by hand (CLAUDE.md), so the schema is
the single source every number downstream (`scripts/progression.py`) reads from.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RESULTS_ROOT = Path("eval/results")

ReleaseState = Literal["draft", "failed"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GateOutcome(_Strict):
    gate: str
    passed: bool
    detail: str = ""


class QCriterionScore(_Strict):
    """One of Q1-Q6 (SCOPING.md). Q1-Q5 come from the eval judge; Q6 is read off the G14
    gate result wherever expected facts exist (SCOPING.md: "deterministic where expected
    facts exist; judge only on clients without them") -- no client scored yet lacks expected
    facts, so Q6 here is always derived, never a judge call."""

    criterion: Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    score: int = Field(ge=1, le=5)
    evidence: list[str] = Field(default_factory=list)
    detail: str = ""


class CategoryScore(_Strict):
    """Precision/recall for one extraction category (value_observations, money_items,
    disposals, open_actions). `None` when the expected count is 0 and nothing was extracted
    either -- there is nothing to score, not a score of 0."""

    category: str
    expected_count: int
    actual_count: int
    matched: int
    precision: float | None
    recall: float | None


class LabelScore(_Strict):
    """Accuracy of one decisive label (basis, money class, blocking, disposal extent),
    counted only over matched pairs -- an unmatched item has no expected label to compare."""

    label: str
    correct: int
    total: int
    accuracy: float | None


class ExtractionScore(_Strict):
    categories: list[CategoryScore] = Field(default_factory=list)
    labels: list[LabelScore] = Field(default_factory=list)


class InvestigationScore(_Strict):
    """Not built until T22's investigation agent exists -- every field defaults to 0 rather
    than the field being omitted, so a results file always shows this headline number
    (accepted_and_wrong) explicitly instead of silently skipping it, same convention as G15
    failing by construction for the baseline (DESIGN.md section 10.4)."""

    questions_raised: int = 0
    answered_correctly: int = 0
    stayed_unresolved_correctly: int = 0
    accepted_and_wrong: int = 0


class ClientResult(_Strict):
    client: str
    release_state: ReleaseState
    expected_release_state: ReleaseState
    gate_results: list[GateOutcome] = Field(default_factory=list)
    q_scores: list[QCriterionScore] = Field(default_factory=list)
    extraction_score: ExtractionScore | None = None
    investigation_score: InvestigationScore = Field(default_factory=InvestigationScore)
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: str = "0"
    cache_hits: int = 0
    live_calls: int = 0
    # How many adviser-review markers the report had. Q5 is scored 5 on a report with none, which
    # says nothing about marker quality; None in a file written before this was recorded.
    marker_count: int | None = None
    # Freeform, e.g. "G10 not checked: source classification failed for the eval re-run" --
    # a gate that couldn't be evaluated is dropped from gate_results and explained here,
    # never left in as a false pass (verifier checkpoint, T17).
    notes: list[str] = Field(default_factory=list)

    @property
    def issued(self) -> bool:
        return self.release_state == "draft"

    @property
    def release_state_matches(self) -> bool:
        return self.release_state == self.expected_release_state

    @property
    def wrongly_issued(self) -> bool:
        """The dangerous case: issued when it should have failed (DESIGN.md section 8.4)."""
        return self.release_state == "draft" and self.expected_release_state == "failed"

    @property
    def hard_gates_passed(self) -> bool:
        return all(g.passed for g in self.gate_results)


class GroupSummary(_Strict):
    group: str
    client_count: int
    issued_rate: float
    release_state_match_rate: float
    wrongly_issued: int
    accepted_and_wrong: int
    cost_per_report_usd: str


def summarize_group(group: str, clients: list[ClientResult]) -> GroupSummary:
    n = len(clients)
    total_cost = sum((float(c.cost_usd) for c in clients), 0.0)
    return GroupSummary(
        group=group,
        client_count=n,
        issued_rate=(sum(1 for c in clients if c.issued) / n) if n else 0.0,
        release_state_match_rate=(sum(1 for c in clients if c.release_state_matches) / n)
        if n
        else 0.0,
        wrongly_issued=sum(1 for c in clients if c.wrongly_issued),
        accepted_and_wrong=sum(c.investigation_score.accepted_and_wrong for c in clients),
        cost_per_report_usd=f"{(total_cost / n) if n else 0.0:.4f}",
    )


class SkippedClient(_Strict):
    """A requested client that was never scored at all, distinct from one that was scored
    and failed -- e.g. no `eval/expected/<client>.json` on disk yet. Recorded here rather
    than just printed, so a skip is traceable from the results file itself (CLAUDE.md: every
    metric quoted in docs is read from an eval output file)."""

    client: str
    reason: str


class ResultsFile(_Strict):
    generated_at: str  # UTC, ISO 8601
    commit: str
    dirty: bool
    config_hash: str
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    stage_models: dict[str, str] = Field(default_factory=dict)
    clients: list[ClientResult] = Field(default_factory=list)
    skipped_clients: list[SkippedClient] = Field(default_factory=list)
    group_summaries: dict[str, GroupSummary] = Field(default_factory=dict)
    total_cost_usd: str = "0"

    @property
    def cost_per_report_usd(self) -> str:
        n = len(self.clients)
        total = sum((float(c.cost_usd) for c in self.clients), 0.0)
        return f"{(total / n) if n else 0.0:.4f}"


def git_commit_info(root: Path = Path(".")) -> tuple[str, bool]:
    """(short sha, dirty). `git` failures (e.g. a shallow clone) degrade to "unknown"/dirty,
    never crash the run -- a results file is still worth writing without provenance."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown", True
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
    )
    dirty = bool(status.stdout.strip())
    return sha, dirty


def results_filename(generated_at: dt.datetime, commit: str, dirty: bool) -> str:
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    suffix = "-dirty" if dirty else ""
    return f"{stamp}_{commit}{suffix}.json"


def write_results_file(results: ResultsFile, root: Path = RESULTS_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.strptime(results.generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )
    path = root / results_filename(generated_at, results.commit, results.dirty)
    path.write_text(results.model_dump_json(indent=2), encoding="utf-8")
    return path
