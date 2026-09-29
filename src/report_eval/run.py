"""The eval CLI (DESIGN.md section 10, T17):

    python -m report_eval.run --clients <list|all> [--judge] [--fresh]
        [--stage-models stage=model,...] [--outputs-dir <dir>] [--config <path>]

Scores whatever is already on disk under `--outputs-dir` against each client's
`eval/expected/<client>.json` -- it never imports or calls `agent_pipeline.pipeline`. This is
the same path for the baseline (`outputs/baseline/`, no ledger or review sheet, so G14/G15
fail by construction) and a real pipeline run (`outputs/`, with a ledger): one `ReportBundle`
reconstruction, built from whatever of `<client>.md`/`.failed.md`/`.ledger.json` exists
(ARCHITECTURE.md: report_eval depends on agent_pipeline, never the reverse).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from agent_pipeline.config import ReportConfig, load_prompt, load_report_config
from agent_pipeline.extract.meeting import LLMMeetingModel, extract_meeting
from agent_pipeline.gates.deterministic import (
    TABLE_HEADER,
    GateResult,
    ReportBundle,
    TableRow,
    run_gates,
)
from agent_pipeline.ledger import Ledger
from agent_pipeline.llm import LLMClient, OpenAITransport, Transport
from agent_pipeline.reconcile.new_accounts import NEW_ACCOUNT_LABEL
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.markdown import read_markdown
from agent_pipeline.sources.classify import (
    ClassificationResult,
    ClassificationStopError,
    ClassifiedSource,
    LLMTextClassifier,
    classify,
)
from agent_pipeline.sources.document import SourceDoc
from report_eval.expected import ExpectedFacts, load_expected
from report_eval.extraction_score import score_extraction
from report_eval.judge_rubric import LLMEvalJudgeModel, MarkerSummary, derive_q6, score_q1_to_q5
from report_eval.results import (
    ClientResult,
    GateOutcome,
    ReleaseState,
    ResultsFile,
    SkippedClient,
    git_commit_info,
    summarize_group,
    write_results_file,
)
from report_eval.truth import ExpectedTruth

PROMPTS_DIR = Path("config/prompts")
MODELS_PATH = Path("config/models.json")

_TABLE_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$"
)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _parse_table_rows(report_text: str, new_account_ids: list[str]) -> list[TableRow]:
    """The report's table as rows. A new account is printed as "To be opened", not its
    synthetic id; each such row takes the next of the ledger's `new_account_ids`, so G1 still
    checks it. A label beyond their number stays as printed and G1 reports it unexpected."""
    lines = report_text.splitlines()
    pending_new = list(new_account_ids)
    rows: list[TableRow] = []
    in_table = False
    for line in lines:
        if line.strip() == TABLE_HEADER:
            in_table = True
            continue
        if not in_table:
            continue
        if set(line.strip()) <= {"|", "-"} and line.strip():
            continue  # the "|---|---|---|---|" separator row
        match = _TABLE_ROW_RE.match(line)
        if not match:
            break  # the table ended
        account_id, owner, _account_type, value = (g.strip() for g in match.groups())
        if account_id == NEW_ACCOUNT_LABEL and pending_new:
            account_id = pending_new.pop(0)
        rows.append(
            TableRow(
                account_id=account_id,
                owners=[o.strip() for o in owner.split(" & ")],
                value_text=value,
            )
        )
    return rows


def _split_sections(report_text: str, config: ReportConfig) -> dict[str, str]:
    id_by_title = {s.title: s.id for s in config.sections}
    matches = list(_HEADING_RE.finditer(report_text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        section_id = id_by_title.get(m.group(1).strip())
        if section_id is None:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(report_text)
        sections[section_id] = report_text[start:end].strip()
    return sections


def _load_bundle(
    client: str, outputs_dir: Path, config: ReportConfig
) -> tuple[ReportBundle | None, ReleaseState]:
    """Reconstructs a `ReportBundle` from whatever `<client>.md`/`.failed.md`/`.ledger.json`
    exists under `outputs_dir` -- "scoring saved files" for every client, baseline or real,
    not a special case for the baseline (T17's own plan). Returns `(None, release_state)` when
    there's no report text to run gates against at all (e.g. an input stop before stage 3, per
    `agent_pipeline.assemble.write_input_stop` -- no draft, ever)."""
    md_path = outputs_dir / f"{client}.md"
    failed_path = outputs_dir / f"{client}.failed.md"
    ledger_path = outputs_dir / f"{client}.ledger.json"

    release_state: ReleaseState
    if md_path.exists():
        report_text = md_path.read_text(encoding="utf-8")
        release_state = "draft"
    elif failed_path.exists():
        release_state = "failed"
        text = failed_path.read_text(encoding="utf-8")
        marker = "\n\n---\n\n"
        report_text = text.split(marker, 1)[1] if marker in text else ""
    else:
        raise FileNotFoundError(f"no {client}.md or {client}.failed.md under {outputs_dir}")

    if not report_text.strip():
        return None, release_state

    ledger = (
        Ledger.model_validate_json(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.exists()
        else Ledger(client=client)
    )
    bundle = ReportBundle(
        report_text=report_text,
        sections=_split_sections(report_text, config),
        table_rows=_parse_table_rows(
            report_text, [a.id for a in ledger.accounts if a.is_new and a.in_scope]
        ),
        ledger=ledger,
    )
    return bundle, release_state


def _read_doc(source: ClassifiedSource) -> SourceDoc:
    return (
        read_docx(source.path)
        if source.path.suffix.lower() == ".docx"
        else read_markdown(source.path)
    )


def _doc_text(doc: SourceDoc) -> str:
    return " ".join(doc.paragraphs.values())


def _source_by_role(classification: ClassificationResult, role: str) -> ClassifiedSource | None:
    return next((s for s in classification.sources if s.role == role), None)


def _load_client_sources(
    client: str, data_dir: Path, llm: LLMClient
) -> tuple[str, str, str, dict[str, SourceDoc], ClassificationResult, bool]:
    """Guidance/meeting/spec text and the judge's source paragraphs -- read straight from
    `data/<client>/`, independent of which output variant is being scored (a property of the
    client's sources, not the report). Degrades to empty text rather than raising on a
    classification stop: a client whose sources don't classify cleanly still gets
    deterministic-gate scoring. The trailing `bool` says whether classification actually
    succeeded -- G10 (guidance leak) computes its overlap from `internal_guidance_text`, and
    an empty string there reads as "no overlap found", i.e. a *pass*, not "not checked"; the
    caller needs to know which one it actually got (verifier checkpoint, T17) rather than
    silently reporting a clean G10 result off text that was never really read."""
    classifier = LLMTextClassifier(llm, load_prompt(PROMPTS_DIR / "classify.md"))
    try:
        classification = classify(data_dir / client, classifier)
    except ClassificationStopError:
        return "", "", "", {}, ClassificationResult(), False

    guidance = _source_by_role(classification, "internal_guidance")
    meeting = _source_by_role(classification, "meeting_record")
    spec = _source_by_role(classification, "report_spec")
    instruction = _source_by_role(classification, "report_instruction")

    guidance_text = _doc_text(_read_doc(guidance)) if guidance else ""
    spec_text = _doc_text(_read_doc(spec)) if spec else ""
    sources: dict[str, SourceDoc] = {}
    meeting_text = ""
    if meeting is not None:
        meeting_doc = _read_doc(meeting)
        meeting_text = _doc_text(meeting_doc)
        sources[meeting.path.name] = meeting_doc
    if instruction is not None:
        sources[instruction.path.name] = _read_doc(instruction)

    return guidance_text, meeting_text, spec_text, sources, classification, True


def _score_extraction(classification: ClassificationResult, llm: LLMClient):
    meeting = _source_by_role(classification, "meeting_record")
    if meeting is None:
        return None
    try:
        expected = load_expected(_client_from_classification(classification))
    except (FileNotFoundError, ValueError):
        return None
    meeting_doc = _read_doc(meeting)
    model = LLMMeetingModel(llm, load_prompt(PROMPTS_DIR / "extract_meeting.md"))
    actual = extract_meeting(meeting_doc, model)
    return score_extraction(actual, expected.extraction)


def _client_from_classification(classification: ClassificationResult) -> str:
    # Every classified source lives under data/<client>/<file> -- the client name is the
    # source folder's own name, read back rather than threaded through another parameter.
    account_source = classification.sources[0] if classification.sources else None
    if account_source is None:
        raise ValueError("no classified sources")
    return account_source.path.parent.name


def _config_hash(config_path: Path) -> str:
    """A stable fingerprint of the config file used for this run. Python's built-in `hash()`
    is randomised per process (`PYTHONHASHSEED`), so it changed on every invocation even for
    an identical config, defeating the point of a fingerprint meant to say "was this the same
    config" across runs (caught replaying a run twice in a row, T17 checkpoint)."""
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def _apply_stage_overrides(config: ReportConfig, overrides: str) -> ReportConfig:
    if not overrides:
        return config
    stages = dict(config.stages)
    for pair in overrides.split(","):
        stage, _, model = pair.partition("=")
        if not stage or not model or stage not in stages:
            raise ValueError(f"--stage-models: unknown stage or malformed pair {pair!r}")
        stages[stage] = stages[stage].model_copy(update={"model": model})
    return config.model_copy(update={"stages": stages})


def _resolve_clients(requested: list[str], outputs_dir: Path) -> list[str]:
    if requested != ["all"]:
        return requested
    names: set[str] = set()
    for path in sorted(outputs_dir.glob("*.md")):
        if path.name.endswith(".failed.md"):
            names.add(path.name[: -len(".failed.md")])
        else:
            names.add(path.stem)
    return sorted(names)


def _read_trace(trace_path: Path) -> list[dict]:
    if not trace_path.exists():
        return []
    return [
        json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line
    ]


@dataclass(frozen=True)
class TraceTotals:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    cache_hits: int
    live_calls: int


def _trace_totals(entries: list[dict]) -> TraceTotals:
    cache_hits = sum(1 for e in entries if e.get("cache_hit"))
    return TraceTotals(
        input_tokens=sum(e.get("tokens", {}).get("input_tokens", 0) for e in entries),
        cached_input_tokens=sum(e.get("tokens", {}).get("cached_input_tokens", 0) for e in entries),
        output_tokens=sum(e.get("tokens", {}).get("output_tokens", 0) for e in entries),
        cost_usd=sum(
            (Decimal(str(e["cost_usd"])) for e in entries if "cost_usd" in e), Decimal("0")
        ),
        cache_hits=cache_hits,
        live_calls=len(entries) - cache_hits,
    )


def score_client(
    client: str,
    *,
    expected: ExpectedFacts,
    outputs_dir: Path,
    data_dir: Path,
    config: ReportConfig,
    models: dict,
    cache_root: Path,
    fresh: bool,
    judge: bool,
    run_id: str,
    transport: Transport | None = None,
) -> ClientResult:
    """`transport` is for tests only, same pattern as `agent_pipeline.pipeline.run`: a
    `FakeTransport`/similar that never touches the network, so an offline replay doesn't need
    a real `OpenAI()` client. `expected` is loaded by the caller (`main`), not here: a
    missing `eval/expected/<client>.json` is a per-client skip, decided once, before any LLM
    client or trace file for that client is even created (verifier checkpoint, T17 -- an
    earlier version loaded it internally and crashed the whole batch on the first client
    that lacked one)."""
    bundle, release_state = _load_bundle(client, outputs_dir, config)

    trace_path = Path("runs") / run_id / client / "trace.jsonl"
    llm = LLMClient(
        transport if transport is not None else OpenAITransport(),
        stages=config.stages,
        models=models,
        cache_root=cache_root,
        fresh=fresh,
        trace_path=trace_path,
    )

    gate_results: list[GateResult] = []
    q_scores = []
    extraction_score = None
    notes: list[str] = []
    if bundle is not None:
        guidance_text, meeting_text, spec_text, sources, classification, classified_ok = (
            _load_client_sources(client, data_dir, llm)
        )
        # G10 (guidance leak) needs the client's raw source text, only available after
        # `_load_client_sources` classifies the client folder -- one bundle, built once,
        # not scored before it's complete.
        bundle = ReportBundle(
            report_text=bundle.report_text,
            sections=bundle.sections,
            table_rows=bundle.table_rows,
            ledger=bundle.ledger,
            internal_guidance_text=guidance_text,
            meeting_text=meeting_text,
            spec_text=spec_text,
        )
        gate_results = run_gates(bundle, ExpectedTruth(expected))
        if not classified_ok:
            # An empty internal_guidance_text reads as "no overlap found" -- a G10 pass that
            # never actually checked anything. Drop it rather than report a false clean bill.
            gate_results = [g for g in gate_results if g.gate != "G10"]
            notes.append(
                "G10 not checked: source classification failed for the eval re-run "
                "(ClassificationStopError)"
            )
        extraction_score = _score_extraction(classification, llm)

        if judge:
            markers = [MarkerSummary(key=m.key, description=m.text) for m in bundle.ledger.markers]
            judge_model = LLMEvalJudgeModel(llm, load_prompt(PROMPTS_DIR / "eval_judge.md"))
            q_scores = score_q1_to_q5(bundle, spec_text, sources, markers, judge_model)
            g14 = next((g for g in gate_results if g.gate == "G14"), None)
            if g14 is not None:
                q_scores.append(derive_q6(g14))

    totals = _trace_totals(_read_trace(trace_path))
    return ClientResult(
        client=client,
        release_state=release_state,
        expected_release_state=expected.release.state,
        gate_results=[
            GateOutcome(gate=g.gate, passed=g.passed, detail=g.detail) for g in gate_results
        ],
        q_scores=q_scores,
        extraction_score=extraction_score,
        notes=notes,
        input_tokens=totals.input_tokens,
        cached_input_tokens=totals.cached_input_tokens,
        output_tokens=totals.output_tokens,
        cost_usd=str(totals.cost_usd),
        cache_hits=totals.cache_hits,
        live_calls=totals.live_calls,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", nargs="+", default=["all"])
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--stage-models", default="")
    parser.add_argument("--outputs-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("config/template_config.json"))
    parser.add_argument("--group", default="real")
    args = parser.parse_args()

    load_dotenv()
    config = _apply_stage_overrides(load_report_config(args.config), args.stage_models)
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    clients = _resolve_clients(args.clients, args.outputs_dir)
    run_id = f"eval-{int(time.time())}"

    client_results: list[ClientResult] = []
    skipped_clients: list[SkippedClient] = []
    for client in clients:
        try:
            expected = load_expected(client)
        except FileNotFoundError:
            skipped_clients.append(
                SkippedClient(client=client, reason="no eval/expected/<client>.json on disk")
            )
            continue
        client_results.append(
            score_client(
                client,
                expected=expected,
                outputs_dir=args.outputs_dir,
                data_dir=args.data_dir,
                config=config,
                models=models,
                cache_root=Path("cache/llm"),
                fresh=args.fresh,
                judge=args.judge,
                run_id=run_id,
            )
        )

    commit, dirty = git_commit_info()
    config_hash = _config_hash(args.config)
    prompt_versions = {
        name: load_prompt(PROMPTS_DIR / f"{name}.md").version
        for name in ("classify", "extract_meeting", "eval_judge")
        if (PROMPTS_DIR / f"{name}.md").exists()
    }
    stage_models = {stage: cfg.model for stage, cfg in config.stages.items()}
    total_cost = sum((Decimal(c.cost_usd) for c in client_results), Decimal("0"))

    results = ResultsFile(
        generated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        commit=commit,
        dirty=dirty,
        config_hash=config_hash,
        prompt_versions=prompt_versions,
        stage_models=stage_models,
        clients=client_results,
        skipped_clients=skipped_clients,
        group_summaries={args.group: summarize_group(args.group, client_results)},
        total_cost_usd=str(total_cost),
    )
    path = write_results_file(results)
    skip_note = f", {len(skipped_clients)} skipped" if skipped_clients else ""
    print(f"Wrote {path}: {len(client_results)} client(s){skip_note}, ${total_cost} total")


if __name__ == "__main__":
    main()
