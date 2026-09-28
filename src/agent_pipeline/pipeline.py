"""The stage graph (DESIGN.md section 2): classify -> extract -> reconcile -> plan -> write
-> assemble draft -> gate/judge -> write outputs, for one client. Owns stage order; must
not decide facts itself (ARCHITECTURE.md) -- every decision below calls a `reconcile/`
function or an already-built stage module.

M1 scope (client 01's happy path): the `investigate/` agent, and every DESIGN.md section 8.4
degradation row that needs an input client 01 doesn't have (statement images, disposals,
scope ambiguity, currency items), are explicitly M2's job, not wired here.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from agent_pipeline.assemble import (
    RunSummary,
    build_run_summary,
    write_draft_or_failed,
    write_input_stop,
)
from agent_pipeline.config import ReportConfig, load_prompt
from agent_pipeline.extract.instruction import LLMInstructionModel, extract_instruction
from agent_pipeline.extract.meeting import LLMMeetingModel, extract_meeting
from agent_pipeline.extract.parsing import parse_amount, parse_date
from agent_pipeline.gates.deterministic import ReportBundle, TableRow, run_gates
from agent_pipeline.gates.judge import LLMJudgeModel, release_judge
from agent_pipeline.gates.release import ReleaseState, decide_release
from agent_pipeline.gates.truth import LedgerTruth
from agent_pipeline.ledger import (
    Account,
    Action,
    ExcludedItem,
    Ledger,
    Value,
    number_markers,
    render_table,
)
from agent_pipeline.llm import LLMClient, OpenAITransport, Transport
from agent_pipeline.reconcile.facts import build_facts
from agent_pipeline.reconcile.limits import limit_review_item
from agent_pipeline.reconcile.markers import required_markers
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.reconcile.predicates import evaluate
from agent_pipeline.reconcile.review import ReviewItemInput, build_review_items, marker_review_items
from agent_pipeline.reconcile.scope import resolve_scope
from agent_pipeline.reconcile.sections import Disposal as SectionDisposal
from agent_pipeline.reconcile.sections import SectionContext
from agent_pipeline.reconcile.values import select_values
from agent_pipeline.reconcile.wrappers import classify_wrapper
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.json_accounts import AccountDataError, read_accounts
from agent_pipeline.sources.adapters.markdown import read_markdown
from agent_pipeline.sources.classify import (
    ClassificationResult,
    ClassificationStopError,
    ClassifiedSource,
    LLMTextClassifier,
    classify,
)
from agent_pipeline.sources.document import SourceDoc
from agent_pipeline.write.plan import plan_sections
from agent_pipeline.write.table import build_table
from agent_pipeline.write.writer import LLMWriterModel, WriterStopError, write_slot
from document_formatter.formatting import format_document

PROMPTS_DIR = Path("config/prompts")
MODELS_PATH = Path("config/models.json")

# One writer call per generated slot (D6): the prompt file is bound per section, matching
# each section's own placeholder. A new report type needing a different slot set is a
# config + prompt-file change, not a code change here, once it declares its own mapping --
# this table covers exactly the six generated slots the shipped config has today.
_PROMPT_FILE_BY_SECTION = {
    "introduction": "write_scope.md",
    "fees_charges": "write_fees.md",
    "conclusion": "write_closing.md",
    "background_objectives": "write_summary.md",
    "recommendations": "write_recommendation.md",
    "tax_implications": "write_cgt_statement.md",
}


@dataclass(frozen=True)
class RunResult:
    client: str
    release_state: ReleaseState
    outputs_dir: Path
    run_summary: RunSummary


class _InputStop(Exception):
    """Raised internally to unwind to one place that writes the failed-generation file
    (DESIGN.md section 8.4) -- every stop condition below constructs the same shape."""

    def __init__(self, reason: str, classification: ClassificationResult) -> None:
        super().__init__(reason)
        self.reason = reason
        self.classification = classification


def _doc_text(doc: SourceDoc) -> str:
    return " ".join(doc.paragraphs.values())


def _source_by_role(classification: ClassificationResult, role: str) -> ClassifiedSource | None:
    return next((s for s in classification.sources if s.role == role), None)


def _load_llm(
    config: ReportConfig, *, fresh: bool, run_id: str, transport: Transport | None
) -> LLMClient:
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    return LLMClient(
        transport if transport is not None else OpenAITransport(),
        stages=config.stages,
        models=models,
        cache_root=Path("cache/llm"),
        fresh=fresh,
        trace_path=Path("runs") / run_id / "trace.jsonl",
    )


def _read_trace(run_id: str) -> list[dict]:
    trace_path = Path("runs") / run_id / "trace.jsonl"
    if not trace_path.exists():
        return []
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def _build_actions(agreed_actions, meeting_source_id: str) -> tuple[list[Action], dict[str, Value]]:
    actions: list[Action] = []
    action_amounts: dict[str, Value] = {}
    for i, agreed in enumerate(agreed_actions, start=1):
        action_id = f"a{i}"
        actions.append(
            Action(
                id=action_id,
                description=agreed.description.text,
                kind="non_action" if agreed.is_non_action else "action",
                accounts=agreed.accounts_referenced,
                quote=agreed.description.text,
                source_id=meeting_source_id,
            )
        )
        if agreed.amount is None:
            continue
        parsed = parse_amount(agreed.amount.text)
        if parsed is None:
            continue
        action_amounts[action_id] = Value(
            amount=parsed.amount,
            currency=parsed.currency,
            precision=parsed.precision,
            qualifier=parsed.qualifier,
            date=None,
            source_id=meeting_source_id,
            quote=agreed.amount.text,
            selected_by="action_amount",
        )
    return actions, action_amounts


def _build_excluded(excluded_items, meeting_source_id: str) -> list[ExcludedItem]:
    return [
        ExcludedItem.model_validate(
            {
                "id": f"e{i}",
                "class": item.item_class,
                "description": item.text.text,
                "allowed_in": ["background_objectives"] if item.item_class == "aspiration" else [],
                "quote": item.text.text,
            }
        )
        for i, item in enumerate(excluded_items, start=1)
    ]


def _resolve_viewed_values(
    value_observations, accounts: list[Account], source_id: str
) -> dict[str, list[Value]]:
    """R3: a meeting figure the model marked as actually viewed, matched to one account by
    type wording (`resolve_scope`'s own approach) -- ambiguous or unmatched never selects."""
    by_account: dict[str, list[Value]] = {}
    for obs in value_observations:
        if obs.basis != "viewed_in_meeting":
            continue
        parsed = parse_amount(obs.amount.text)
        if parsed is None:
            continue
        matches = [a for a in accounts if obs.account_reference.lower() in a.type.lower()]
        if len(matches) != 1:
            continue
        by_account.setdefault(matches[0].id, []).append(
            Value(
                amount=parsed.amount,
                currency=parsed.currency,
                precision=parsed.precision,
                qualifier=parsed.qualifier,
                date=None,
                source_id=source_id,
                quote=obs.amount.text,
                selected_by="R3",
            )
        )
    return by_account


def _limit_review_items(
    actions: list[Action],
    action_amounts: dict[str, Value],
    accounts: list[Account],
    meeting_date,
) -> list[ReviewItemInput]:
    """P4's note case. An action's `accounts` are free text as extracted (e.g. "the cash
    account"), matched to a real account by type wording -- the same convention as R3's
    viewed-value matching and the disposal matching above -- so only an account whose
    wrapper actually carries an allowance (`classify_wrapper`) is ever checked; a cash
    account or GIA referenced by the same action has no `allowance_family` and is silently
    skipped, no config or per-client branching needed.

    Prior use is always "unknown" here, never inferred "confirmed" from the presence of a
    `limit_signals` quote: client 01's own meeting mentions the ISA allowance only for the
    top-up being agreed today, not any earlier use, and an early version of this function
    that treated any limit-signal quote as a confirmation silently swallowed the note it was
    meant to add (live run, T17 checkpoint). Distinguishing a genuine prior-use confirmation
    from an unrelated mention needs real labeled-evidence resolution (DESIGN.md section 4.2),
    not built until T20 widens P4 with client 03's real signals -- until then this never
    triggers `check_limits`' marker case."""
    items: list[ReviewItemInput] = []
    for action in actions:
        amount = action_amounts.get(action.id)
        if amount is None:
            continue
        for ref in action.accounts:
            matches = [a for a in accounts if ref.lower() in a.type.lower()]
            if len(matches) != 1:
                continue
            allowance_family = classify_wrapper(matches[0].type).allowance_family
            if allowance_family is None:
                continue
            item = limit_review_item(
                amount, allowance_family, "unknown", meeting_date, matches[0].id
            )
            if item is not None:
                items.append(item)
    return items


def _computed_placeholder(name: str, ledger: Ledger) -> str:
    """Every "computed" placeholder: built in code from the ledger, never by the model
    (P9, G13). `risk_profile`/`initial_charge` reach the report this way, not as a fact
    token: G13 needs them verbatim, but the writer's digit-free rule (D1) forbids typing a
    number, and Fact/Value's rendering is money-shaped, not a fit for a plain profile label
    (T16 checkpoint)."""
    if name == "holdings_table":
        return build_table(ledger)
    if name == "risk_profile":
        return ledger.risk_profile or "not stated"
    if name == "initial_charge":
        return ledger.initial_charge or "not stated"
    raise ValueError(f"no computed handling for placeholder {name!r}")


def run(
    client_dir: Path,
    config: ReportConfig,
    *,
    outputs_dir: Path = Path("outputs"),
    fresh: bool = False,
    estimate: bool = False,
    transport: Transport | None = None,
) -> RunResult:
    """`transport` is for tests only: a `FakeTransport`/similar that never touches the
    network, so a pure cache replay (`tests/test_pipeline_replay.py`) doesn't need a real
    `OpenAI()` client, which raises immediately without an API key even though a full cache
    hit never calls it (matching every other offline test's `FakeTransport` pattern)."""
    if estimate:
        raise NotImplementedError(
            "--estimate needs an estimate-mode entry point on every stage's model wrapper; "
            "not built yet. Run for real and read the printed cost."
        )

    client = client_dir.name
    run_id = f"{client}-{int(time.time())}"
    llm = _load_llm(config, fresh=fresh, run_id=run_id, transport=transport)

    try:
        bundle, ledger, gate_results = _run_stages(client_dir, config, llm)
    except _InputStop as stop:
        write_input_stop(
            client, outputs_dir, reason=stop.reason, classification=stop.classification
        )
        return RunResult(client, "failed", outputs_dir, RunSummary(client, "failed"))
    except WriterStopError as exc:
        write_input_stop(
            client,
            outputs_dir,
            reason=f"writing failed: {exc}",
            classification=ClassificationResult(),
        )
        return RunResult(client, "failed", outputs_dir, RunSummary(client, "failed"))

    release_state = decide_release(gate_results)
    run_summary = build_run_summary(client, release_state, gate_results, _read_trace(run_id))
    write_draft_or_failed(
        client,
        outputs_dir,
        bundle=bundle,
        ledger=ledger,
        config=config,
        release_state=release_state,
        run_summary=run_summary,
        failed_reason="" if release_state == "draft" else "a hard gate failed",
    )
    print(
        f"{run_summary.total_calls} calls: {run_summary.total_cache_hits} replayed from "
        f"cache, {run_summary.total_live_calls} live, ${run_summary.total_cost_usd}"
    )
    return RunResult(client, release_state, outputs_dir, run_summary)


def _run_stages(
    client_dir: Path, config: ReportConfig, llm: LLMClient
) -> tuple[ReportBundle, Ledger, list]:
    client = client_dir.name

    # --- Stage 1: classify ---------------------------------------------------------------
    classifier = LLMTextClassifier(llm, load_prompt(PROMPTS_DIR / "classify.md"))
    try:
        classification = classify(client_dir, classifier)
    except ClassificationStopError as exc:
        raise _InputStop(str(exc), ClassificationResult(notes=[str(exc)])) from exc

    account_source = _source_by_role(classification, "account_data")
    meeting_source = _source_by_role(classification, "meeting_record")
    instruction_source = _source_by_role(classification, "report_instruction")
    guidance_source = _source_by_role(classification, "internal_guidance")
    spec_source = _source_by_role(classification, "report_spec")

    if account_source is None:
        raise _InputStop("no account data classified", classification)
    if meeting_source is None:
        raise _InputStop("no meeting record classified", classification)
    if instruction_source is None:
        raise _InputStop("no report instruction classified", classification)

    # --- Stage 2: extract -----------------------------------------------------------------
    try:
        account_data = read_accounts(account_source.path)
    except AccountDataError as exc:
        raise _InputStop(str(exc), classification) from exc

    ownership = resolve_ownership(account_data)
    accounts = ownership.accounts

    meeting_doc = read_docx(meeting_source.path)
    meeting_model = LLMMeetingModel(llm, load_prompt(PROMPTS_DIR / "extract_meeting.md"))
    meeting_extraction = extract_meeting(meeting_doc, meeting_model)

    instruction_doc = read_docx(instruction_source.path)
    instruction_model = LLMInstructionModel(
        llm,
        load_prompt(PROMPTS_DIR / "extract_instruction.md"),
        load_prompt(PROMPTS_DIR / "scope_mapping.md"),
    )
    instruction_extraction = extract_instruction(instruction_doc, accounts, instruction_model)

    guidance_text = _doc_text(read_markdown(guidance_source.path)) if guidance_source else ""
    spec_text = _doc_text(read_markdown(spec_source.path)) if spec_source else ""
    meeting_text = _doc_text(meeting_doc)

    # --- Stage 3: reconcile (code only) ---------------------------------------------------
    fields_by_canonical = {f.canonical: f for f in instruction_extraction.fields if f.canonical}
    scope_field = fields_by_canonical.get("scope")
    if scope_field is None or scope_field.is_tbc:
        raise _InputStop("the report instruction's scope is missing or TBC", classification)

    scope_result = resolve_scope(scope_field.value, accounts)
    if scope_result.unresolved:
        raise _InputStop(
            f"scope phrase {scope_field.value!r} did not resolve to exactly one account",
            classification,
        )

    account_by_id = {a.id: a for a in accounts}
    for account_id in scope_result.resolved_ids:
        account_by_id[account_id] = account_by_id[account_id].model_copy(update={"in_scope": True})

    observations_by_account = _resolve_viewed_values(
        meeting_extraction.value_observations, accounts, meeting_source.path.name
    )
    records_by_id = {
        r.account_id: r
        for holder in account_data.holders.values()
        for r in holder.accounts
        if r.account_id
    }
    for account_id, account in list(account_by_id.items()):
        record = records_by_id.get(account_id)
        if record is None:
            continue
        value = select_values(
            record.value,
            record.valuation_date,
            record.currency,
            observations_by_account.get(account_id, []),
        )
        account_by_id[account_id] = account.model_copy(update={"value": value})
    resolved_accounts = list(account_by_id.values())

    actions, action_amounts = _build_actions(
        meeting_extraction.agreed_actions, meeting_source.path.name
    )
    excluded = _build_excluded(meeting_extraction.excluded_items, meeting_source.path.name)

    disposals = [
        SectionDisposal(wrapper_class=classify_wrapper(matches[0].type).wrapper_class)
        for d in meeting_extraction.disposals
        for matches in [
            [a for a in resolved_accounts if d.account_reference.lower() in a.type.lower()]
        ]
        if matches
    ]
    tax_section = evaluate("taxable_disposal", SectionContext(disposals=disposals))

    in_scope_platforms = {a.platform for a in resolved_accounts if a.in_scope and a.platform}
    markers = required_markers(in_scope_platforms)

    facts = build_facts(resolved_accounts, action_amounts)
    objectives = " ".join(o.text.text for o in meeting_extraction.objectives_and_circumstances)
    meeting_date = (
        parse_date(meeting_extraction.meeting_date.text)
        if meeting_extraction.meeting_date
        else None
    )
    limit_items = (
        _limit_review_items(actions, action_amounts, resolved_accounts, meeting_date)
        if meeting_date is not None
        else []
    )

    review_inputs: list[ReviewItemInput] = [
        *ownership.set_aside,
        *(
            ReviewItemInput(kind="open_action", blocking=oa.blocking, detail=oa.text.text, refs=[])
            for oa in meeting_extraction.open_actions
        ),
        *marker_review_items(markers),
        *limit_items,
    ]

    def _field_value(canonical: str) -> str | None:
        field = fields_by_canonical.get(canonical)
        return field.value if field is not None and not field.is_tbc else None

    ledger = number_markers(
        Ledger(
            client=client,
            meeting_date=meeting_date,
            risk_profile=_field_value("risk_profile"),
            initial_charge=_field_value("initial_charge"),
            objectives=objectives or None,
            tax_section=tax_section,
            accounts=resolved_accounts,
            actions=actions,
            excluded=excluded,
            markers=markers,
            review=build_review_items(review_inputs),
            facts=facts,
        ),
        # number_markers wants marker keys in order of first appearance in the assembled
        # report, but that report doesn't exist yet at reconciliation time -- the writer
        # fills {marker:<key>} tokens from the id this assigns (T16 checkpoint). required_
        # markers' own order (platforms sorted, then advice_charge) already matches the
        # only place these markers appear (fees_charges), same as T9's reference bundle.
        report_order=[m.key for m in markers],
    )

    # --- Stage 4: plan ---------------------------------------------------------------------
    plans_by_section = {
        p.section_id: p
        for p in plan_sections(ledger, config, spec_text=spec_text, meeting_text=meeting_text)
    }
    sections_by_id = {s.id: s for s in config.sections}

    # --- Stage 5: write, Stage 6: assemble draft -------------------------------------------
    filled_sections: dict[str, str] = {}
    for section_id, plan in plans_by_section.items():
        section = sections_by_id[section_id]
        content = section.template
        for name, placeholder in section.placeholders.items():
            if placeholder.kind == "computed":
                content = content.replace(f"<<{name}>>", _computed_placeholder(name, ledger))
                continue
            model = LLMWriterModel(
                llm, load_prompt(PROMPTS_DIR / _PROMPT_FILE_BY_SECTION[section_id])
            )
            draft = write_slot(plan, section, ledger, model, guidance_text=guidance_text)
            content = content.replace(f"<<{name}>>", draft.filled_text)
        filled_sections[section_id] = content

    ordered_sections = [
        {"title": sections_by_id[sid].title, "content": text}
        for sid, text in filled_sections.items()
    ]
    report_text = format_document({"document_title": config.document_title}, ordered_sections)
    table_rows = [
        TableRow(
            account_id=a.id,
            owners=a.owners,
            value_text=(
                "To be opened"
                if a.is_new
                else render_table(a.value)
                if a.value is not None
                else "marker"
            ),
        )
        for a in resolved_accounts
        if a.in_scope
    ]
    bundle = ReportBundle(
        report_text=report_text,
        sections=filled_sections,
        table_rows=table_rows,
        ledger=ledger,
        internal_guidance_text=guidance_text,
        meeting_text=meeting_text,
        spec_text=spec_text,
    )

    # --- Stage 7: gate + release judge -----------------------------------------------------
    deterministic_results = run_gates(bundle, LedgerTruth(ledger))
    judge_sources: dict[str, SourceDoc] = {meeting_source.path.name: meeting_doc}
    judge_sources[instruction_source.path.name] = instruction_doc
    judge_model = LLMJudgeModel(llm, load_prompt(PROMPTS_DIR / "release_judge.md"))
    judge_results = release_judge(bundle, ledger, judge_sources, judge_model)

    return bundle, ledger, [*deterministic_results, *judge_results]
