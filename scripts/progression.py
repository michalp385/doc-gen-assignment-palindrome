"""Before/after table per client: `outputs/baseline/` (the starter pipeline) against `outputs/`.

Offline only. Both sides are scored with the eval's own scoring (`report_eval.run.score_client`:
deterministic gates and release state, plus the rubric judge where its answer is already in the
cache), through a transport that cannot reach the API. A cache miss on the judge leaves that
client's judge scores as n/a; a cache miss anywhere else stops the script, since the eval could
not otherwise score that client without a paid call.

Each side is written as an ordinary results file under eval/results/, and the table is rendered
from those files, so every figure in it is read from a results file, never typed by hand
(CLAUDE.md). The table is written to eval/progression.md.

Usage:
    uv run python scripts/progression.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from agent_pipeline.config import load_prompt, load_report_config
from agent_pipeline.llm import RawCompletion
from report_eval.expected import load_expected
from report_eval.results import (
    ClientResult,
    ResultsFile,
    git_commit_info,
    summarize_group,
    write_results_file,
)
from report_eval.run import MODELS_PATH, PROMPTS_DIR, _config_hash, _resolve_clients, score_client

ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = Path("outputs/baseline")
CURRENT_DIR = Path("outputs")
CONFIG_PATH = Path("config/template_config.json")
TABLE_PATH = Path("eval/progression.md")
QS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
NA = "n/a"


class CacheMiss(AssertionError):
    """Raised by the offline transport when a call was not in the cache. An AssertionError
    subclass so the eval's own "a replay transport raised" handling still re-raises it, but a
    distinct type so this script catches its own miss and no other assertion."""


class _NoNetworkTransport:
    """A transport that cannot make a live call: a cache miss raises CacheMiss and is counted."""

    def __init__(self) -> None:
        self.attempts = 0

    def responses_parse(
        self,
        *,
        model: str,
        input: list[dict],
        text_format: type[BaseModel],
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> RawCompletion:
        self.attempts += 1
        raise CacheMiss("cache miss: this script never makes a live call")


def _client(results: ResultsFile, name: str) -> ClientResult | None:
    return next((c for c in results.clients if c.client == name), None)


def _gates_passed(c: ClientResult | None) -> str:
    if c is None:
        return NA
    return f"{sum(g.passed for g in c.gate_results)} of {len(c.gate_results)}"


def _failing(c: ClientResult | None) -> str:
    if c is None:
        return NA
    failing = [g.gate for g in c.gate_results if not g.passed]
    return ", ".join(failing) if failing else "none"


NO_MARKERS = "n/a (no markers)"


def _q(c: ClientResult | None, criterion: str) -> str | None:
    if c is None:
        return None
    if criterion == "Q5" and c.marker_count == 0:
        # The judge scores a report with no markers 5, which says nothing about marker quality.
        return NO_MARKERS
    return next((str(q.score) for q in c.q_scores if q.criterion == criterion), None)


NO_RELEASE_STATE = "n/a (starter has no release states)"


def _failed_count(c: ClientResult | None) -> str:
    return NA if c is None else str(sum(not g.passed for g in c.gate_results))


def render(
    before: ResultsFile,
    before_name: str,
    after: ResultsFile,
    after_name: str,
    *,
    before_has_release_states: bool = True,
) -> str:
    """The before/after markdown, every figure read from the two results files. The starter
    pipeline has no release states (the eval reads "draft" off the file it finds), so
    `before_has_release_states=False` shows that instead of a misleading value."""
    lines = [
        "# Progression: baseline against the current pipeline",
        "",
        f"Baseline: `{before_name}` (commit `{before.commit}`). "
        f"Current: `{after_name}` (commit `{after.commit}`). n/a means that side has no value: "
        "no report for the client, or no judge answer in the cache.",
        "",
    ]
    names = sorted({c.client for c in before.clients} | {c.client for c in after.clients})
    for name in names:
        b, a = _client(before, name), _client(after, name)
        either = a or b
        expected = either.expected_release_state if either else NA
        lines += [
            f"### {name}",
            "",
            "| Measure | Baseline | Current |",
            "|---|---|---|",
            f"| Release state (expected {expected}) | "
            f"{(b.release_state if before_has_release_states else NO_RELEASE_STATE) if b else NA}"
            f" | {a.release_state if a else NA} |",
            f"| Failed deterministic gates | {_failed_count(b)} | {_failed_count(a)} |",
            f"| Deterministic gates passed | {_gates_passed(b)} | {_gates_passed(a)} |",
            f"| Failing gates | {_failing(b)} | {_failing(a)} |",
        ]
        for q in QS:
            bq, aq = _q(b, q), _q(a, q)
            if bq is None and aq is None:
                continue
            lines.append(f"| {q} | {bq or NA} | {aq or NA} |")
        lines.append("")
    if NO_MARKERS in "\n".join(lines):
        lines.append(
            f"{NO_MARKERS}: the report had no adviser-review markers, so the judge's Q5 of 5 "
            "is vacuous and is not shown as a score."
        )
        lines.append("")
    return "\n".join(lines)


def _score_side(
    outputs_dir: Path, clients: list[str], group: str, config, models: dict
) -> tuple[ResultsFile, int]:
    """Score one outputs dir offline. Returns the results and how many clients had no cached
    judge answer."""
    run_id = f"progression-{int(dt.datetime.now(dt.timezone.utc).timestamp())}-{group}"
    results: list[ClientResult] = []
    unjudged = 0
    for client in clients:
        expected = load_expected(client)
        for judge in (True, False):
            transport = _NoNetworkTransport()
            try:
                results.append(
                    score_client(
                        client,
                        expected=expected,
                        outputs_dir=outputs_dir,
                        data_dir=Path("data"),
                        config=config,
                        models=models,
                        cache_root=Path("cache/llm"),
                        fresh=False,
                        judge=judge,
                        run_id=run_id,
                        transport=transport,
                    )
                )
                break
            except CacheMiss:
                if not judge:
                    raise  # the miss is not the judge's: stop rather than score around it
                unjudged += 1
    commit, dirty = git_commit_info()
    total = sum((Decimal(c.cost_usd) for c in results), Decimal("0"))
    return (
        ResultsFile(
            generated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            commit=commit,
            dirty=dirty,
            config_hash=_config_hash(CONFIG_PATH),
            prompt_versions={
                name: load_prompt(PROMPTS_DIR / f"{name}.md").version
                for name in ("classify", "extract_meeting", "eval_judge")
                if (PROMPTS_DIR / f"{name}.md").exists()
            },
            stage_models={stage: cfg.model for stage, cfg in config.stages.items()},
            clients=results,
            group_summaries={group: summarize_group(group, results)},
            total_cost_usd=str(total),
        ),
        unjudged,
    )


_STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def later_stamp(earlier: str, candidate: str) -> str:
    """`candidate`, or one second after `earlier` if it is not later. A results file is named by
    its one-second timestamp and the commit, so two files from one run must not share a stamp."""
    if candidate > earlier:
        return candidate
    bumped = dt.datetime.strptime(earlier, _STAMP_FORMAT) + dt.timedelta(seconds=1)
    return bumped.strftime(_STAMP_FORMAT)


def main() -> int:
    config = load_report_config(CONFIG_PATH)
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    clients = _resolve_clients(["all"], BASELINE_DIR)
    # Both sides are built before either file is written, so the first write cannot make the
    # tree "dirty" for the second.
    before, before_unjudged = _score_side(BASELINE_DIR, clients, "baseline", config, models)
    after, after_unjudged = _score_side(CURRENT_DIR, clients, "real", config, models)
    after = after.model_copy(
        update={"generated_at": later_stamp(before.generated_at, after.generated_at)}
    )
    before_path = write_results_file(before)
    after_path = write_results_file(after)

    # Render from the files just written: the table reads only what a results file holds.
    before_file = ResultsFile.model_validate_json(before_path.read_text(encoding="utf-8"))
    after_file = ResultsFile.model_validate_json(after_path.read_text(encoding="utf-8"))
    table = render(
        before_file,
        before_path.as_posix(),
        after_file,
        after_path.as_posix(),
        before_has_release_states=False,
    )
    TABLE_PATH.write_text(table, encoding="utf-8")
    print(table)
    print(
        f"Wrote {TABLE_PATH}, {before_path}, {after_path} "
        f"(no cached judge answer: baseline {before_unjudged}, current {after_unjudged})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
