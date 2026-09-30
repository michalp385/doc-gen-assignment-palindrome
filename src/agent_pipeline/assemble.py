"""Outputs, the review sheet and the run summary (DESIGN.md sections 8.3, 8.5, 8.6).

`RunSummary`'s shape and `build_run_summary`'s aggregation are pure functions over
trace-line-shaped dicts, testable standalone; wiring them to a real `trace.jsonl` from an
actual run is `pipeline.py`'s job (T16), same as the `runs/<run_id>/` per-stage folder this
doesn't build yet.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import cast

from agent_pipeline.config import ReportConfig
from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from agent_pipeline.gates.release import ReleaseState
from agent_pipeline.ledger import Account, Ledger, Marker, ReviewItem
from agent_pipeline.reconcile.predicates import section_included
from agent_pipeline.sources.classify import ClassificationResult

# `handling_note` and `ambiguity` (D29): what the run did, or could not do, with a client-specific
# handling instruction. The adviser has to see both, in particular a note that was not applied.
_NOTE_KINDS = (
    "p4_note",
    "scope_flag",
    "currency",
    "image_discrepancy",
    "unverified",
    "handling_note",
    "ambiguity",
)


@dataclass(frozen=True)
class StageSummary:
    stage: str
    calls: int
    cache_hits: int
    live_calls: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: Decimal
    latency_s: float
    models: frozenset[str]
    prompt_versions: frozenset[str]


@dataclass(frozen=True)
class RunSummary:
    client: str
    release_state: ReleaseState
    gate_results: list[GateResult] = field(default_factory=list)
    stages: list[StageSummary] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return sum(s.calls for s in self.stages)

    @property
    def total_cache_hits(self) -> int:
        return sum(s.cache_hits for s in self.stages)

    @property
    def total_live_calls(self) -> int:
        return sum(s.live_calls for s in self.stages)

    @property
    def total_cost_usd(self) -> Decimal:
        return sum((s.cost_usd for s in self.stages), Decimal("0"))


def build_run_summary(
    client: str,
    release_state: ReleaseState,
    gate_results: list[GateResult],
    trace_entries: Sequence[Mapping[str, object]],
) -> RunSummary:
    by_stage: dict[str, list[Mapping[str, object]]] = {}
    for entry in trace_entries:
        by_stage.setdefault(str(entry["stage"]), []).append(entry)

    stages = []
    for stage_name, entries in by_stage.items():
        cache_hits = sum(1 for e in entries if e.get("cache_hit"))
        token_dicts: list[Mapping[str, int]] = [
            cast(Mapping[str, int], e["tokens"]) for e in entries if "tokens" in e
        ]
        stages.append(
            StageSummary(
                stage=stage_name,
                calls=len(entries),
                cache_hits=cache_hits,
                live_calls=len(entries) - cache_hits,
                input_tokens=sum(t["input_tokens"] for t in token_dicts),
                cached_input_tokens=sum(t.get("cached_input_tokens", 0) for t in token_dicts),
                output_tokens=sum(t["output_tokens"] for t in token_dicts),
                reasoning_tokens=sum(t.get("reasoning_tokens", 0) for t in token_dicts),
                cost_usd=sum(
                    (Decimal(str(e["cost_usd"])) for e in entries if "cost_usd" in e), Decimal("0")
                ),
                latency_s=sum(cast(float, e.get("latency_s", 0.0)) for e in entries),
                models=frozenset(str(e["model"]) for e in entries),
                prompt_versions=frozenset(str(e["prompt_version"]) for e in entries),
            )
        )
    return RunSummary(
        client=client, release_state=release_state, gate_results=gate_results, stages=stages
    )


def _run_summary_json(run_summary: RunSummary) -> dict:
    return {
        "client": run_summary.client,
        "release_state": run_summary.release_state,
        "gate_results": [
            {"gate": r.gate, "passed": r.passed, "detail": r.detail}
            for r in run_summary.gate_results
        ],
        "stages": [
            {
                "stage": s.stage,
                "calls": s.calls,
                "cache_hits": s.cache_hits,
                "live_calls": s.live_calls,
                "tokens": {
                    "input": s.input_tokens,
                    "cached_input": s.cached_input_tokens,
                    "output": s.output_tokens,
                    "reasoning": s.reasoning_tokens,
                },
                "cost_usd": str(s.cost_usd),
                "latency_s": s.latency_s,
                "models": sorted(s.models),
                "prompt_versions": sorted(s.prompt_versions),
            }
            for s in run_summary.stages
        ],
        "total_calls": run_summary.total_calls,
        "total_cache_hits": run_summary.total_cache_hits,
        "total_live_calls": run_summary.total_live_calls,
        "total_cost_usd": str(run_summary.total_cost_usd),
    }


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else "None."


def _account_left_out_reason(account: Account) -> str:
    if account.status == "closed":
        return "closed"
    if account.scope_reason:
        return account.scope_reason
    return "out of scope"


def _section_decisions(config: ReportConfig, ledger: Ledger) -> list[str]:
    lines = []
    for section in config.sections:
        if section.predicate is None:
            continue  # not a conditional section (DESIGN section 8.5 item 7); "always" or
            # model-judged inclusion isn't rendered here yet -- model-judged inclusion isn't
            # built (DESIGN section 7.1's no-predicate fallback), so there's nothing to show.
        try:
            included = section_included(section, ledger)
        except KeyError:
            continue
        verdict = "included" if included else "omitted"
        lines.append(f"{section.title}: {verdict} (predicate: {section.predicate})")
    return lines


def _marker_lines(markers: list[Marker]) -> list[str]:
    return [f"{m.id}: {m.text} ({m.reason}), section: {m.section}" for m in markers]


def _review_lines(items: list[ReviewItem], kinds: tuple[str, ...]) -> list[str]:
    return [f"{i.detail}" for i in items if i.kind in kinds]


def build_review_sheet(
    config: ReportConfig,
    ledger: Ledger,
    release_state: ReleaseState,
    run_summary: RunSummary,
    *,
    run_id: str = "",
    run_date: str = "",
) -> str:
    """DESIGN.md section 8.5's 9 sections, in order, always rendered -- a section with
    nothing to show prints "None." rather than being omitted, so the shape is stable."""
    passed = sum(1 for r in run_summary.gate_results if r.passed)
    total = len(run_summary.gate_results)
    status_lines = [f"Release state: {release_state}"]
    if run_id:
        status_lines.append(f"Run: {run_id}")
    if run_date:
        status_lines.append(f"Date: {run_date}")
    status_lines.append(
        f"Cache replay vs live: {run_summary.total_cache_hits} replayed, "
        f"{run_summary.total_live_calls} live"
    )
    status_lines.append(f"Gates: {passed}/{total} passed")

    blocking_open_actions = _review_lines(
        [i for i in ledger.review if i.kind == "open_action" and i.blocking], ("open_action",)
    )
    other_open_actions = _review_lines(
        [i for i in ledger.review if i.kind == "open_action" and not i.blocking], ("open_action",)
    )
    conflicts = _review_lines(ledger.review, ("conflict", "investigation"))
    superseded = _review_lines(ledger.review, ("superseded",))
    left_out = [f"{a.id}: {_account_left_out_reason(a)}" for a in ledger.accounts if not a.in_scope]
    notes = _review_lines(ledger.review, _NOTE_KINDS)
    degradations = _review_lines(ledger.review, ("degradation",))

    return "\n\n".join(
        [
            f"# Review sheet -- {ledger.client}",
            "## Status\n\n" + "\n".join(status_lines),
            "## Blocking before sign-off\n\n" + _bullets(blocking_open_actions),
            # Not one of DESIGN.md section 8.5's original 9 sections, which gives non-blocking
            # open actions no home of their own -- added so they don't get folded into
            # "Blocking before sign-off" and mislabelled (verifier report, T15 checkpoint,
            # finding #5).
            "## Other open actions (not blocking)\n\n" + _bullets(other_open_actions),
            "## Markers to fill\n\n" + _bullets(_marker_lines(ledger.markers)),
            "## Conflicts and how they were resolved\n\n" + _bullets(conflicts),
            "## Superseded values\n\n" + _bullets(superseded),
            "## Accounts left out\n\n" + _bullets(left_out),
            "## Section decisions\n\n" + _bullets(_section_decisions(config, ledger)),
            "## Notes\n\n" + _bullets(notes),
            "## How this draft degraded\n\n" + _bullets(degradations),
        ]
    )


def write_draft_or_failed(
    client: str,
    outputs_dir: Path,
    *,
    bundle: ReportBundle | None,
    ledger: Ledger,
    config: ReportConfig,
    release_state: ReleaseState,
    run_summary: RunSummary,
    failed_reason: str = "",
) -> None:
    """Draft xor failed generation (DESIGN.md section 8.3): writes the one release-state
    file that applies and removes the stale counterpart, so a previous run's draft is never
    mistaken for this run's, and vice versa."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    draft_path = outputs_dir / f"{client}.md"
    failed_path = outputs_dir / f"{client}.failed.md"

    if release_state == "draft":
        if bundle is None:
            raise ValueError("a draft release needs the assembled report bundle")
        draft_path.write_text(bundle.report_text, encoding="utf-8")
        failed_path.unlink(missing_ok=True)
    else:
        failing = [r for r in run_summary.gate_results if not r.passed]
        lines = [
            "**NOT ISSUED**",
            "",
            failed_reason or "one or more hard gates failed",
            "",
            "## Failing gates",
            "",
            _bullets([f"{r.gate}: {r.detail}" for r in failing]),
        ]
        if bundle is not None:
            lines += ["", "---", "", bundle.report_text]
        failed_path.write_text("\n".join(lines), encoding="utf-8")
        draft_path.unlink(missing_ok=True)

    (outputs_dir / f"{client}.review.md").write_text(
        build_review_sheet(config, ledger, release_state, run_summary), encoding="utf-8"
    )
    (outputs_dir / f"{client}.ledger.json").write_text(
        ledger.model_dump_json(indent=2), encoding="utf-8"
    )
    (outputs_dir / f"{client}.run.json").write_text(
        json.dumps(_run_summary_json(run_summary), indent=2), encoding="utf-8"
    )


def write_input_stop(
    client: str,
    outputs_dir: Path,
    *,
    reason: str,
    classification: ClassificationResult,
) -> None:
    """DESIGN.md section 8.3: an input stop before stage 3 writes the reason and the
    classification result only -- no draft, no ledger (there is no ledger yet)."""
    outputs_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "**NOT ISSUED**",
        "",
        reason,
        "",
        "## Classification",
        "",
        _bullets([f"{s.path.name}: {s.role} ({s.method})" for s in classification.sources]),
    ]
    if classification.notes:
        lines += ["", "## Notes", "", _bullets(classification.notes)]
    (outputs_dir / f"{client}.failed.md").write_text("\n".join(lines), encoding="utf-8")
    (outputs_dir / f"{client}.md").unlink(missing_ok=True)
    # A prior successful run's ledger belongs to that run, not this stop -- this state has
    # no ledger at all (verifier report, T15 checkpoint, finding #3).
    (outputs_dir / f"{client}.ledger.json").unlink(missing_ok=True)

    (outputs_dir / f"{client}.review.md").write_text(
        f"# Review sheet -- {client}\n\n## Status\n\nRelease state: failed\n\n{reason}\n",
        encoding="utf-8",
    )
    (outputs_dir / f"{client}.run.json").write_text(
        json.dumps({"client": client, "release_state": "failed", "reason": reason}, indent=2),
        encoding="utf-8",
    )
