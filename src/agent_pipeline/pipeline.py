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
import re
import time
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from agent_pipeline.assemble import (
    RunSummary,
    build_run_summary,
    write_draft_or_failed,
    write_input_stop,
)
from agent_pipeline.config import ReportConfig, load_prompt
from agent_pipeline.extract.image import LLMImageModel, extract_image
from agent_pipeline.extract.instruction import LLMInstructionModel, extract_instruction
from agent_pipeline.extract.meeting import LLMMeetingModel, extract_meeting
from agent_pipeline.extract.parsing import parse_amount, parse_date
from agent_pipeline.extract.schemas import NewAccount, OpenAction
from agent_pipeline.gates.deterministic import ReportBundle, TableRow, run_gates
from agent_pipeline.gates.judge import judge_models, majority_release_judge
from agent_pipeline.gates.release import ReleaseState, decide_release
from agent_pipeline.gates.truth import LedgerTruth
from agent_pipeline.investigate.model import LLMInvestigationModel
from agent_pipeline.investigate.stage import run_investigation
from agent_pipeline.ledger import (
    Account,
    Action,
    ExcludedItem,
    Ledger,
    Marker,
    MoneyItem,
    Value,
    number_markers,
    render_date,
    render_table,
)
from agent_pipeline.llm import LLMClient, OpenAITransport, Transport
from agent_pipeline.reconcile.account_state import check_account_states
from agent_pipeline.reconcile.amounts import instruction_figures, resolve_amount
from agent_pipeline.reconcile.decisions import DecisionCheck, check_selling_decision
from agent_pipeline.reconcile.degradation import (
    missing_platform_review_items,
    undated_meeting_review_item,
)
from agent_pipeline.reconcile.facts import build_facts
from agent_pipeline.reconcile.limits import (
    check_limits,
    limit_marker,
    limit_review_item,
    pension_contribution_accounts,
    pension_contribution_markers,
    pension_review_item,
    resolve_prior_use,
)
from agent_pipeline.reconcile.markers import (
    available_marker,
    bond_marker,
    cgt_marker,
    required_markers,
    tbc_field_markers,
)
from agent_pipeline.reconcile.meetings import (
    govern_meeting_records,
    several_records_review_item,
)
from agent_pipeline.reconcile.money import (
    attributable_stated_amount,
    available_now,
    build_money_items,
    classify_money,
)
from agent_pipeline.reconcile.new_accounts import NewAccountMention, build_new_accounts
from agent_pipeline.reconcile.ownership import resolve_ownership
from agent_pipeline.reconcile.predicates import evaluate
from agent_pipeline.reconcile.refs import accounts_matching_reference
from agent_pipeline.reconcile.review import ReviewItemInput, build_review_items, marker_review_items
from agent_pipeline.reconcile.scope import resolve_scope
from agent_pipeline.reconcile.scope_parts import (
    UNRESOLVED_ID_PREFIX,
    build_unresolved_scope,
    unresolved_scope_parts,
)
from agent_pipeline.reconcile.sections import Disposal as SectionDisposal
from agent_pipeline.reconcile.sections import SectionContext, unknown_wrapper_review_items
from agent_pipeline.reconcile.unspecified_amounts import (
    PartialDisposal,
    build_unspecified_amounts,
    is_funding_action,
)
from agent_pipeline.reconcile.values import (
    check_image_row,
    is_stated_gbp,
    match_image_row,
    record_candidate,
    select_values,
    superseded_values,
    tied_candidates,
)
from agent_pipeline.reconcile.wrappers import classify_wrapper
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.image import read_image
from agent_pipeline.sources.adapters.json_accounts import (
    AccountData,
    AccountDataError,
    AccountRecord,
    read_accounts,
)
from agent_pipeline.sources.adapters.markdown import read_markdown
from agent_pipeline.sources.classify import (
    ClassificationResult,
    ClassificationStopError,
    ClassifiedSource,
    LLMTextClassifier,
    classify,
)
from agent_pipeline.sources.document import SourceDoc
from agent_pipeline.write.plan import plan_sections, unrouted_markers
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


def _to_sentence_end(quote: str, paragraph: str | None) -> str:
    """The quote extended to the end of its own sentence in the source paragraph, verbatim.
    An aspiration's caveat ("not for today") often sits after the clause the model quoted."""
    if not paragraph or quote.rstrip().endswith((".", "!", "?")):
        return quote
    start = paragraph.find(quote)
    if start < 0:
        return quote
    end = start + len(quote)
    stop = re.search(r"[.!?](?=\s|$)", paragraph[end:])
    if stop is None:
        return paragraph[start:].strip()
    return paragraph[start : end + stop.end()].strip()


def _build_excluded(
    excluded_items, meeting_source_id: str, meeting_doc: SourceDoc
) -> list[ExcludedItem]:
    def _text(item) -> str:
        if item.item_class != "aspiration":
            return item.text.text
        return _to_sentence_end(item.text.text, meeting_doc.paragraph_text(item.text.paragraph_id))

    return [
        ExcludedItem.model_validate(
            {
                "id": f"e{i}",
                "class": item.item_class,
                "description": _text(item),
                "allowed_in": ["background_objectives"] if item.item_class == "aspiration" else [],
                "quote": _text(item),
            }
        )
        for i, item in enumerate(excluded_items, start=1)
    ]


def _classify_disposals(
    disposals,
    meeting_money_items,
    accounts: list[Account],
    meeting_source_id: str,
) -> tuple[list[SectionDisposal], list[MoneyItem], dict[str, Value]]:
    """P5, G5/P7: matches each meeting disposal to one account by type wording (R3's own
    convention), builds its `SectionDisposal` (G5's predicate reads only the wrapper class)
    and its proceeds `MoneyItem` (`classify_money`, counted only when the disposal is full
    and a "proceeds"-classified money item shows the sources state where the money goes --
    that's what "destination known" means here, distinct from the *amount sold*, which is
    always the disposed account's own R3-selected value, never a second re-extracted
    figure). Returns the disposed accounts' counted proceeds by account id, for
    `_apply_proceeds_to_actions` to fund an action's fact from."""
    matches = []
    unmatched = 0
    for d in disposals:
        found = accounts_matching_reference(d.account_reference, accounts)
        if len(found) == 1:
            matches.append((d, found[0]))
        else:
            unmatched += 1
    section_disposals = [
        SectionDisposal(
            wrapper_class=classify_wrapper(account.type).wrapper_class, account_id=account.id
        )
        for _, account in matches
    ]
    # G5 case b: a disposal that matches no single account is never silently dropped -- it
    # is a possible taxable disposal pending confirmation (an "unknown" wrapper).
    section_disposals += [SectionDisposal(wrapper_class="unknown") for _ in range(unmatched)]
    destination_known = any(mi.money_class == "proceeds" for mi in meeting_money_items)
    money_items: list[MoneyItem] = []
    proceeds_by_account: dict[str, Value] = {}
    for disposal, account in matches:
        if account.value is None:
            continue
        # A stated portion amount is attributed only to a sole disposal (see
        # `attributable_stated_amount`).
        stated_amount = (
            attributable_stated_amount(
                meeting_money_items,
                meeting_source_id,
                matched_disposals=len(matches),
                unmatched=unmatched,
                account_value=account.value,
            )
            if disposal.extent != "full"
            else None
        )
        result = classify_money(account.value, disposal.extent, destination_known, stated_amount)
        money_items.append(
            MoneyItem.model_validate(
                {
                    "id": f"m{len(money_items) + 1}",
                    "class": "proceeds",
                    "amount": result.amount,
                    "counted": result.counted,
                    "reason": result.reason,
                    "quote": disposal.quote.text,
                    "source_id": meeting_source_id,
                }
            )
        )
        if result.counted and result.amount is not None:
            proceeds_by_account[account.id] = result.amount
    return section_disposals, money_items, proceeds_by_account


def _apply_proceeds_to_actions(
    actions: list[Action],
    action_amounts: dict[str, Value],
    accounts: list[Account],
    proceeds_by_account: dict[str, Value],
    skip_ids: Collection[str] = frozenset(),
) -> set[str]:
    """P5: funds an action's fact from a disposal's own counted proceeds, never a
    separately re-extracted quote -- the agreed-action sentence often states no figure at
    all (client 02's doesn't). Mutates `action_amounts` in place (matching `_build_actions`'
    own dict, which the caller already owns); only fills an action with no amount yet, and
    only when it matches exactly one disposed, counted account. Returns the action ids it
    filled, so the caller (`build_facts`) can carry P5's proceeds qualifiers into that
    fact's own description -- gross, before any CGT, not yet realised -- distinct from a
    plain internal transfer's generic one."""
    filled: set[str] = set()
    for action in actions:
        if action.id in skip_ids:
            continue  # its amount was dropped for an R5 conflict; never refilled
        matched_ids = {
            a.id for ref in action.accounts for a in accounts_matching_reference(ref, accounts)
        }
        proceeds = [proceeds_by_account[i] for i in matched_ids if i in proceeds_by_account]
        if action.id in action_amounts:
            # An action that states its own amount is still proceeds-funded when that amount
            # is exactly a disposed account's counted proceeds (a stated portion), so it
            # carries P5's qualifiers too.
            if any(p.amount == action_amounts[action.id].amount for p in proceeds):
                filled.add(action.id)
            continue
        if len(proceeds) == 1:
            action_amounts[action.id] = proceeds[0]
            filled.add(action.id)
    return filled


def _resolve_viewed_values(
    value_observations,
    accounts: list[Account],
    source_id: str,
    meeting_date,
) -> dict[str, list[Value]]:
    """R3: a meeting figure the model marked as actually viewed, matched to one account by
    reference text (`reconcile/refs.py`) -- ambiguous or unmatched never selects. Dated with
    the meeting's own date, not `None`: `select_values`' "latest date wins" comparison
    (`v.date or date.min`) otherwise always loses a genuinely later live-viewed figure to
    the account data's own dated snapshot, whatever that date is -- a real bug no client
    before client 02 exercised (T19 checkpoint: the GIA's live-viewed figure was silently
    losing to the stale statement value until this was found and fixed)."""
    by_account: dict[str, list[Value]] = {}
    for obs in value_observations:
        if obs.basis != "viewed_in_meeting":
            continue
        parsed = parse_amount(obs.amount.text)
        if parsed is None:
            continue
        matches = accounts_matching_reference(obs.account_reference, accounts)
        if len(matches) != 1:
            continue
        by_account.setdefault(matches[0].id, []).append(
            Value(
                amount=parsed.amount,
                currency=parsed.currency,
                precision=parsed.precision,
                qualifier=parsed.qualifier,
                date=meeting_date,
                source_id=source_id,
                quote=obs.amount.text,
                selected_by="R3",
            )
        )
    return by_account


def _recalled_figure_conflicts(
    value_observations, accounts: list[Account]
) -> list[ReviewItemInput]:
    """R3: a figure the client recalled is not one the adviser saw, so it never selects a value;
    it only confirms or conflicts. One that matches a single account and differs from the value
    selected for it is a non-blocking conflict naming both figures, so the adviser sees the
    disagreement. A recalled figure that agrees, or that matches no single account or one with
    no selected value, raises nothing."""
    items: list[ReviewItemInput] = []
    for obs in value_observations:
        if obs.basis != "recalled":
            continue
        parsed = parse_amount(obs.amount.text)
        matches = accounts_matching_reference(obs.account_reference, accounts)
        if parsed is None or len(matches) != 1 or matches[0].value is None:
            continue
        selected = matches[0].value
        if parsed.amount == selected.amount and parsed.currency == selected.currency:
            continue
        items.append(
            ReviewItemInput(
                kind="conflict",
                blocking=False,
                detail=(
                    f"{matches[0].id}: the meeting note has a recalled figure, "
                    f"{obs.amount.text!r}, which differs from the selected value "
                    f"{render_table(selected)}; a recalled figure never selects a value (R3)."
                ),
                refs=[matches[0].id],
            )
        )
    return items


def _full_date(day) -> str:  # type: ignore[no-untyped-def]  # a datetime.date
    """ "15 April 2026": the day, month and year, so a blocking item names the date exactly."""
    return f"{day.day} {day:%B} {day.year}"


def _candidate_values(
    account_id: str,
    record: AccountRecord,
    observations_by_account: dict[str, list[Value]],
    other_copies: dict[str, list[AccountRecord]] | None,
) -> list[Value]:
    """The figures competing for an account under R3: any live-viewed meeting figure, plus (R9)
    each other copy of the joint account whose figure or date differs from the record's own.
    An identical copy is one answer and adds nothing."""
    extra: list[Value] = []
    for copy in (other_copies or {}).get(account_id, []):
        if (copy.value, copy.valuation_date) == (record.value, record.valuation_date):
            continue
        candidate = record_candidate(copy.value, copy.valuation_date, copy.currency)
        if candidate is not None:
            extra.append(candidate)
    return [*observations_by_account.get(account_id, []), *extra]


def _tied_account_ids(
    account_by_id: dict[str, Account],
    records_by_id: dict[str, AccountRecord],
    observations_by_account: dict[str, list[Value]],
    other_copies: dict[str, list[AccountRecord]] | None = None,
) -> set[str]:
    """The accounts whose latest-dated figures disagree (R3, R9): their value is unresolved."""
    tied: set[str] = set()
    for account_id in account_by_id:
        record = records_by_id.get(account_id)
        if record is None:
            continue
        viewed = _candidate_values(account_id, record, observations_by_account, other_copies)
        if tied_candidates(record.value, record.valuation_date, record.currency, viewed) and (
            is_stated_gbp(record.currency)
        ):
            tied.add(account_id)
    return tied


def _apply_values(
    account_by_id: dict[str, Account],
    records_by_id: dict[str, AccountRecord],
    observations_by_account: dict[str, list[Value]],
    other_copies: dict[str, list[AccountRecord]] | None = None,
) -> tuple[dict[str, Account], list[ReviewItemInput]]:
    """R3, R9, G15: selects each account's value (the account data plus any live-viewed
    meeting figure) and, wherever a candidate lost, records it in `Account.superseded`
    (the table's own footnote, `write/table.py`) and builds a review-sheet item quoting
    both the superseded and the current value with their dates -- T19, client 02's GIA."""
    accounts = dict(account_by_id)
    review_items: list[ReviewItemInput] = []
    for account_id, account in account_by_id.items():
        record = records_by_id.get(account_id)
        if record is None:
            continue
        viewed = _candidate_values(account_id, record, observations_by_account, other_copies)
        value = select_values(record.value, record.valuation_date, record.currency, viewed)
        tie = tied_candidates(record.value, record.valuation_date, record.currency, viewed)
        if tie and is_stated_gbp(record.currency):
            # R3 / R9: same-date candidates that disagree select nothing; the account's value
            # cell becomes a marker (`_apply_account_states`) and the adviser sees why.
            tie_date = tie[0].date
            when = _full_date(tie_date) if tie_date is not None else "undated"
            # Copies of one joint account disagreeing is R9: the adviser must settle it. A tie
            # with a live-viewed meeting figure keeps its earlier, non-blocking form.
            copies_only = all(v.source_id == "client_data_db.json" for v in tie)
            figures = "; ".join(f"{render_table(v)} ({v.source_id})" for v in tie)
            review_items.append(
                ReviewItemInput(
                    kind="conflict",
                    # R9 blocks only for an account the report covers.
                    blocking=copies_only and account.in_scope,
                    detail=(
                        f"{account_id}: sources give different values on the same date "
                        f"({when}): {figures}; no value is selected"
                        + (
                            "; confirm which is right before anything is finalised."
                            if copies_only
                            else "."
                        )
                    ),
                    refs=[account_id],
                )
            )
        superseded = superseded_values(
            record.value, record.valuation_date, record.currency, viewed, value
        )
        accounts[account_id] = account.model_copy(update={"value": value, "superseded": superseded})
        # A value withheld for its currency (P12) never reaches the review sheet as an
        # unlabelled figure: the account's own currency item covers it.
        if (
            superseded
            and value is not None
            and value.date is not None
            and is_stated_gbp(record.currency)
        ):
            superseded_text = "; ".join(
                f"superseded value {render_table(s)} ({s.source_id}, {render_date(s.date)})"
                if s.date is not None
                else f"superseded value {render_table(s)} ({s.source_id})"
                for s in superseded
            )
            review_items.append(
                ReviewItemInput(
                    kind="superseded",
                    blocking=False,
                    detail=(
                        f"{account_id}: {superseded_text}; current value {render_table(value)} "
                        f"({value.source_id}, {render_date(value.date)})."
                    ),
                    refs=[account_id],
                )
            )
    return accounts, review_items


def _pension_markers(
    actions: list[Action], accounts: list[Account]
) -> tuple[list[Marker], list[ReviewItemInput]]:
    """P4: pension contribution amounts are always adviser-review markers, whether or not
    the sources state an amount (client 04's "SIPP contributions for both, sized within
    allowances" states none). Triggered by an agreed action naming an in-scope pension
    account; the review row states no limit."""
    pensions = pension_contribution_accounts(actions, accounts)
    item = pension_review_item(pensions)
    return pension_contribution_markers(pensions), [item] if item is not None else []


def _apply_money(
    extracted,
    source_id: str,
    start_index: int,
    instruction_figures: list[Value] | None = None,
) -> tuple[list[MoneyItem], Value | None, list[Marker], list[ReviewItemInput]]:
    """P5: the meeting's received, committed and external money items as ledger items, and
    the available-now value (received minus committed, in code). When it cannot be computed
    without a guess -- a commitment with no stated amount -- the amount becomes a marker
    with a review row explaining why, never a subtracted guess. Proceeds are not built here:
    `_classify_disposals` owns them. `start_index` keeps ids unique against those."""
    build = build_money_items(extracted, source_id, start_index, instruction_figures)
    result = available_now(build.items)
    markers: list[Marker] = []
    review_items = list(build.review_items)
    if result.marker_reason is not None:
        markers.append(available_marker(result.marker_reason))
        review_items.append(
            ReviewItemInput(
                kind="ambiguity",
                blocking=False,
                detail=(f"the amount available to invest is a marker: {result.marker_reason}."),
                refs=[],
            )
        )
    return build.items, result.value, markers, review_items


def _reconcile_instruction_amount(
    actions: list[Action],
    action_amounts: dict[str, Value],
    accounts: list[Account],
    instruction_amounts: list[Value],
) -> tuple[list[Marker], list[ReviewItemInput]]:
    """R5 (SCOPING section 3.1 rule 5): the report instruction's exact figure against the one
    amount the meeting states for an action. The same amount uses the exact figure. Any
    difference is a blocking conflict and an amount marker, and the action's amount is dropped
    so that neither figure reaches the report. Made only when it is a single pair: exactly one
    exact instruction figure and exactly one funding action stating an amount. That does not
    prove they mean the same money (a total across accounts against one action's part of it
    would raise a false conflict, which the adviser then sees and settles). Mutates
    `action_amounts`."""
    stated = [
        a for a in actions if a.kind == "action" and a.id in action_amounts and is_funding_action(a)
    ]
    if len(instruction_amounts) != 1 or len(stated) != 1:
        return [], []
    action = stated[0]
    matched = [m for ref in action.accounts for m in accounts_matching_reference(ref, accounts)]
    allowance = any(classify_wrapper(a.type).allowance_family is not None for a in matched)
    label = "topup_amount" if allowance else "investment_amount"
    meeting = action_amounts[action.id]
    resolution = resolve_amount(instruction_amounts[0], meeting, label=label)
    if resolution.value is not None:
        # The same amount. Only an approximate meeting figure is replaced by the exact one
        # (R5); two exact figures need no change and keep the meeting's own value.
        if meeting.precision != "exact":
            action_amounts[action.id] = resolution.value
        return [], []
    del action_amounts[action.id]
    return (
        [resolution.marker] if resolution.marker is not None else [],
        [resolution.conflict] if resolution.conflict is not None else [],
    )


def _partial_disposals(
    disposals, accounts: list[Account], counted_account_ids: set[str]
) -> list[PartialDisposal]:
    """P5: each disposal that matches one account and whose extent is a portion, or is not
    stated -- its amount sold is an unspecified amount, not the account's whole value."""
    partial: list[PartialDisposal] = []
    for disposal in disposals:
        found = accounts_matching_reference(disposal.account_reference, accounts)
        # A portion whose stated amount P5 counted has no unspecified amount.
        if len(found) == 1 and disposal.extent != "full" and found[0].id not in counted_account_ids:
            partial.append(
                PartialDisposal(
                    account=found[0], reference=disposal.account_reference, extent=disposal.extent
                )
            )
    return partial


def _open_action_item(action: OpenAction, meeting_doc: SourceDoc) -> ReviewItemInput:
    """An open action's review item. The quote alone is often a bare pronoun sentence, so the
    detail is its source paragraph verbatim, which contains the quote: the subject is in the
    note, not in code."""
    quote = action.text.text
    paragraph = meeting_doc.paragraph_text(action.text.paragraph_id)
    detail = paragraph if paragraph and paragraph.strip() != quote.strip() else quote
    return ReviewItemInput(kind="open_action", blocking=action.blocking, detail=detail, refs=[])


def _apply_new_accounts(
    mentions: list[NewAccount], scope_phrase: str, account_data: AccountData
) -> tuple[list[Account], list[Marker], list[ReviewItemInput]]:
    """R1, P9, P2: the accounts the advice opens, from the meeting's verified mentions and the
    report instruction's scope (`reconcile/new_accounts.py`). Owners come from the account data's
    holders. Not put through `_apply_account_states`: a new account's value is "To be opened",
    not a missing value."""
    result = build_new_accounts(
        [
            NewAccountMention(
                quote=m.description.text, joint=m.joint, owner_references=tuple(m.owner_references)
            )
            for m in mentions
        ],
        scope_phrase,
        [holder.name for holder in account_data.holders.values()],
    )
    return result.accounts, result.markers, result.review_items


def _apply_account_states(
    accounts: list[Account],
    currency_by_id: dict[str, str | None],
    tied_ids: frozenset[str] = frozenset(),
) -> tuple[list[Account], list[Marker], list[ReviewItemInput]]:
    """R6, P12: applies `check_account_states` to the ledger's accounts -- a null value, or a
    value whose currency is not GBP or not stated (a missing currency is not-GBP, DESIGN.md
    section 3.3), becomes a value-cell marker in scope (the value is also cleared, so it can
    never reach a fact or the superseded footnote as if it were sterling), and a
    closed account the scope names leaves the table with a blocking conflict. Returns the
    markers and review items for the caller to add to the ledger; a closed or valueless
    out-of-scope account is left as it was."""
    states = check_account_states(accounts, currency_by_id, tied_ids)
    updated: list[Account] = []
    markers: list[Marker] = []
    review_items: list[ReviewItemInput] = []
    for account in accounts:
        state = states[account.id]
        update: dict[str, object] = {}
        if state.value_marker is not None:
            update["value_marker"] = state.value_marker.key
            markers.append(state.value_marker)
        if state.withhold_value:
            update["value"] = None
            update["superseded"] = []
        if account.in_scope and not state.in_table:
            update["in_scope"] = False
            update["scope_reason"] = "closed in the account data (R6)"
        updated.append(account.model_copy(update=update) if update else account)
        review_items.extend(state.review_items)
    return updated, markers, review_items


@dataclass(frozen=True)
class _LimitGroup:
    action_amount: Value
    allowance_family: str
    account_ids: list[str]


def _limit_groups(
    actions: list[Action], action_amounts: dict[str, Value], accounts: list[Account]
) -> list[_LimitGroup]:
    """P4: an action's `accounts` are free text as extracted (e.g. "the cash account"),
    matched to a real account by type wording -- the same convention as R3's viewed-value
    matching and the disposal matching below -- so only an account whose wrapper actually
    carries an allowance (`classify_wrapper`) is ever checked; a cash account or GIA
    referenced by the same action has no `allowance_family` and is silently skipped, no
    config or per-client branching needed. Matching is scoped to in-scope accounts only --
    an out-of-scope account with matching type wording (e.g. a second ISA this report
    doesn't cover) must never receive a note that points at an account absent from the
    table, and must never silently steal the match from an in-scope account with the same
    wording (verifier checkpoint, T17: an earlier version matched every account).

    Every allowance-bearing account an action references is grouped together (T19: client
    02's top-up touches both ISAs at once), not one group per account -- so one note or
    marker covers the whole family, not a near-duplicate per account. Shared by
    `_limit_review_items` and `_limit_markers` so the matching logic lives in one place."""
    in_scope_accounts = [a for a in accounts if a.in_scope]
    groups: list[_LimitGroup] = []
    for action in actions:
        amount = action_amounts.get(action.id)
        if amount is None:
            continue
        matches = []
        for ref in action.accounts:
            ref_matches = accounts_matching_reference(ref, in_scope_accounts)
            if len(ref_matches) == 1:
                matches.append(ref_matches[0])
        # Pensions take their own path (`_pension_markers`): a pension amount is always a
        # marker, stated or not, never an ISA-shaped allowance question.
        allowance_families = {
            af
            for a in matches
            if (af := classify_wrapper(a.type).allowance_family) not in (None, "pension")
        }
        for allowance_family in allowance_families:
            family_accounts = [
                a for a in matches if classify_wrapper(a.type).allowance_family == allowance_family
            ]
            groups.append(
                _LimitGroup(
                    action_amount=amount,
                    allowance_family=allowance_family,
                    account_ids=[a.id for a in family_accounts],
                )
            )
    return groups


def _limit_review_items(
    actions: list[Action],
    action_amounts: dict[str, Value],
    accounts: list[Account],
    meeting_date,
    limit_signals: list | None = None,
) -> list[ReviewItemInput]:
    """P4's review-sheet side: one note or marker-context row per `_limit_groups` group.
    `resolve_prior_use` (T19) resolves prior use from the meeting's verified
    `limit_signals` -- omitted (client 01's own call sites), it stays "unknown", same as
    before T19 widened this."""
    items: list[ReviewItemInput] = []
    for group in _limit_groups(actions, action_amounts, accounts):
        prior_use = resolve_prior_use(limit_signals or [], group.allowance_family)
        item = limit_review_item(
            group.action_amount, group.allowance_family, prior_use, meeting_date, group.account_ids
        )
        if item is not None:
            items.append(item)
    return items


def _limit_markers(
    actions: list[Action],
    action_amounts: dict[str, Value],
    accounts: list[Account],
    meeting_date,
    limit_signals: list,
):
    """P2, P4 (T19): `check_limits`' marker case (a breach, or confirmed prior use) builds a
    report marker, one per allowance family across every action that hits it -- not built
    until T19 needed it (client 01 never triggers the marker branch)."""
    marker_by_family = {}
    for group in _limit_groups(actions, action_amounts, accounts):
        prior_use = resolve_prior_use(limit_signals, group.allowance_family)
        result = check_limits(
            group.action_amount.amount, group.allowance_family, prior_use, meeting_date
        )
        if result.marker and group.allowance_family not in marker_by_family:
            marker_by_family[group.allowance_family] = limit_marker(
                group.allowance_family, group.account_ids
            )
    return list(marker_by_family.values())


def _image_review_items(
    image_source: ClassifiedSource | None,
    accounts: list[Account],
    account_currency_by_id: dict[str, str | None],
    llm: LLMClient,
) -> list[ReviewItemInput]:
    """P10: a statement image never selects a value (`select_values` never sees it) -- this
    runs after the fact, against whichever value each in-scope account already has, and can
    only confirm it (silent) or raise a review item. A row that doesn't match any in-scope
    account (`match_image_row`) is itself a review item, not a silent drop -- flag rather
    than guess, same principle as everywhere else, even though no current client's image
    exercises this path (all match cleanly).

    `account_currency_by_id` is the account data's own, possibly-missing `currency` field
    (`record.currency`, the same value `select_values` reads) -- not `account.value.currency`,
    which is `UNKNOWN` when the record is silent (P12, DESIGN.md section 3.3: a missing
    currency is not-GBP; `_apply_account_states` has already withheld such a value and
    marked it). The record's own field is used here so a genuinely-unknown currency takes
    `check_image_row`'s "unknown, skip" branch instead of being mislabelled a "possible read
    error" (verifier checkpoint, T18)."""
    if image_source is None:
        return []
    in_scope_accounts = [a for a in accounts if a.in_scope]
    image = read_image(image_source.path)
    model = LLMImageModel(llm, load_prompt(PROMPTS_DIR / "extract_image.md"))
    extraction = extract_image(image, model)
    if not extraction.readable:
        return [
            ReviewItemInput(
                kind="image_discrepancy",
                blocking=False,
                detail=f"could not read the statement image: {image_source.path.name}",
                refs=[],
            )
        ]
    items: list[ReviewItemInput] = []
    for row in extraction.rows:
        account = match_image_row(row, in_scope_accounts)
        if account is None:
            items.append(
                ReviewItemInput(
                    kind="image_discrepancy",
                    blocking=False,
                    detail=(
                        f"statement image row {row.account_label!r} did not match any "
                        "in-scope account"
                    ),
                    refs=[],
                )
            )
            continue
        account_currency = account_currency_by_id.get(account.id)
        item = check_image_row(account.value, row, account_currency)
        if item is not None:
            items.append(item)
    return items


def _tbc_slot(ledger: Ledger, key: str) -> str | None:
    """P11: the bracketed marker text for a TBC request field, as the table does for a value
    cell, or None when the field has no such marker."""
    marker = next((m for m in ledger.markers if m.key == key), None)
    return f"[ADVISER TO CONFIRM {marker.id}: {marker.text}]" if marker is not None else None


def _computed_placeholder(name: str, ledger: Ledger) -> str:
    """Every "computed" placeholder: built in code from the ledger, never by the model
    (P9, G13). `risk_profile`/`initial_charge` reach the report this way, not as a fact
    token: G13 needs them verbatim, but the writer's digit-free rule (D1) forbids typing a
    number, and Fact/Value's rendering is money-shaped, not a fit for a plain profile label
    (T16 checkpoint)."""
    if name == "holdings_table":
        return build_table(ledger)
    if name == "risk_profile":
        return ledger.risk_profile or _tbc_slot(ledger, "risk_profile_tbc") or "not stated"
    if name == "initial_charge":
        return ledger.initial_charge or _tbc_slot(ledger, "initial_charge_tbc") or "not stated"
    raise ValueError(f"no computed handling for placeholder {name!r}")


def run(
    client_dir: Path,
    config: ReportConfig,
    *,
    outputs_dir: Path = Path("outputs"),
    fresh: bool = False,
    transport: Transport | None = None,
) -> RunResult:
    """`transport` is for tests only: a `FakeTransport`/similar that never touches the
    network, so a pure cache replay (`tests/test_pipeline_replay.py`) doesn't need a real
    `OpenAI()` client, which raises immediately without an API key even though a full cache
    hit never calls it (matching every other offline test's `FakeTransport` pattern)."""
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
    meeting_sources = [s for s in classification.sources if s.role == "meeting_record"]
    instruction_source = _source_by_role(classification, "report_instruction")
    guidance_source = _source_by_role(classification, "internal_guidance")
    spec_source = _source_by_role(classification, "report_spec")
    image_source = _source_by_role(classification, "statement_image")

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

    meeting_model = LLMMeetingModel(llm, load_prompt(PROMPTS_DIR / "extract_meeting.md"))
    # R10: with several meeting records the latest-dated one governs decisions; earlier ones
    # contribute dated values only. One record (every real client) takes the same path as ever.
    meeting_docs = [read_docx(s.path) for s in meeting_sources]
    meeting_extractions = [extract_meeting(d, meeting_model) for d in meeting_docs]
    record_dates = [
        parse_date(e.meeting_date.text) if e.meeting_date else None for e in meeting_extractions
    ]
    governing, earlier_records = govern_meeting_records(record_dates)
    meeting_source = meeting_sources[governing]
    meeting_doc = meeting_docs[governing]
    meeting_extraction = meeting_extractions[governing]

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

    scope_mapping = instruction_extraction.scope_mapping
    candidate_account_ids = (
        scope_mapping.candidate_account_ids
        if scope_mapping is not None and scope_mapping.phrase == scope_field.value
        else None
    )
    scope_result = resolve_scope(scope_field.value, accounts, candidate_account_ids)
    if scope_result.unresolved:
        raise _InputStop(
            f"scope phrase {scope_field.value!r} did not resolve to any account",
            classification,
        )

    account_by_id = {a.id: a for a in accounts}
    for account_id in scope_result.resolved_ids:
        account_by_id[account_id] = account_by_id[account_id].model_copy(update={"in_scope": True})

    meeting_date = (
        parse_date(meeting_extraction.meeting_date.text)
        if meeting_extraction.meeting_date
        else None
    )
    observations_by_account = _resolve_viewed_values(
        meeting_extraction.value_observations, accounts, meeting_source.path.name, meeting_date
    )
    for index in earlier_records:
        # An earlier record adds its own dated figures; R3 decides which is latest.
        for account_id, values in _resolve_viewed_values(
            meeting_extractions[index].value_observations,
            accounts,
            meeting_sources[index].path.name,
            record_dates[index],
        ).items():
            observations_by_account.setdefault(account_id, []).extend(values)
    records_by_id = {
        r.account_id: r
        for holder in account_data.holders.values()
        for r in holder.accounts
        if r.account_id
    }
    # R9: every copy of a joint account, so disagreeing copies compete under R3.
    copies_by_id: dict[str, list[AccountRecord]] = {}
    for holder in account_data.holders.values():
        for r in holder.accounts:
            if r.account_id:
                copies_by_id.setdefault(r.account_id, []).append(r)
    tied_ids = frozenset(
        _tied_account_ids(account_by_id, records_by_id, observations_by_account, copies_by_id)
    )
    account_by_id, superseded_review_items = _apply_values(
        account_by_id, records_by_id, observations_by_account, copies_by_id
    )
    superseded_review_items.extend(
        _recalled_figure_conflicts(
            meeting_extraction.value_observations, list(account_by_id.values())
        )
    )
    account_currency_by_id = {aid: r.currency for aid, r in records_by_id.items()}
    resolved_accounts, state_markers, state_review_items = _apply_account_states(
        list(account_by_id.values()), account_currency_by_id, tied_ids
    )
    new_accounts, new_account_markers, new_account_review_items = _apply_new_accounts(
        meeting_extraction.new_accounts, scope_field.value, account_data
    )
    resolved_accounts = [*resolved_accounts, *new_accounts]

    # R8: a part of the scope phrase naming an account type the client does not hold.
    unresolved_scope = build_unresolved_scope(
        unresolved_scope_parts(
            scope_field.value, accounts, [h.name for h in account_data.holders.values()]
        ),
        scope_field.label_as_written,
    )
    resolved_accounts = [*resolved_accounts, *unresolved_scope.accounts]

    # Stage 3a (D14): open questions where more evidence could change the outcome. A client
    # whose mentions all resolve opens none, so the model is never called for it.
    investigation = run_investigation(
        meeting_extraction.accounts_mentioned,
        resolved_accounts,
        {meeting_source.path.name: meeting_doc, instruction_source.path.name: instruction_doc},
        meeting_source.path.name,
        LLMInvestigationModel(llm, load_prompt(PROMPTS_DIR / "investigate.md")),
    )

    # R1/R9: two copies of the same account_id may disagree on value or date -- always a
    # review-sheet conflict (which one wins is R3's job above).
    superseded_review_items.extend(ownership.conflicts)
    superseded_review_items.extend(state_review_items)

    disposals, money_items, disposal_proceeds_by_account = _classify_disposals(
        meeting_extraction.disposals,
        meeting_extraction.money_items,
        resolved_accounts,
        meeting_source.path.name,
    )
    # R4 (G5 case b): the instruction's selling decision against the meeting's disposals.
    selling_field = fields_by_canonical.get("selling_existing_investments")
    selling_decision = (
        check_selling_decision(
            selling_field.label_as_written,
            selling_field.value,
            [d.quote.text for d in meeting_extraction.disposals],
        )
        if selling_field is not None and not selling_field.is_tbc
        else DecisionCheck()
    )
    # An instruction that says yes with no sale in the meeting is a possible taxable
    # disposal: the tax section and CGT marker are kept, not omitted.
    tax_disposals = (
        [*disposals, SectionDisposal(wrapper_class="unknown")]
        if selling_decision.add_possible_disposal
        else disposals
    )
    tax_section = evaluate("taxable_disposal", SectionContext(disposals=tax_disposals))
    disposal_review_items = unknown_wrapper_review_items(disposals)

    amount_field = fields_by_canonical.get("investment_amount")
    # R5: the instruction's exact figures, read in code from its amount field.
    instruction_amounts = (
        instruction_figures(amount_field.value, instruction_source.path.name)
        if amount_field is not None and not amount_field.is_tbc
        else []
    )
    other_money_items, available, available_markers, money_review_items = _apply_money(
        meeting_extraction.money_items,
        meeting_source.path.name,
        len(money_items) + 1,
        instruction_amounts,
    )
    money_items = [*money_items, *other_money_items]

    actions, action_amounts = _build_actions(
        meeting_extraction.agreed_actions, meeting_source.path.name
    )
    amounts_before = set(action_amounts)
    amount_markers, amount_review_items = _reconcile_instruction_amount(
        actions, action_amounts, resolved_accounts, instruction_amounts
    )
    conflicted_action_ids = amounts_before - set(action_amounts)
    proceeds_action_ids = _apply_proceeds_to_actions(
        actions,
        action_amounts,
        resolved_accounts,
        disposal_proceeds_by_account,
        skip_ids=conflicted_action_ids,
    )

    excluded = _build_excluded(
        meeting_extraction.excluded_items, meeting_source.path.name, meeting_doc
    )

    in_scope_platforms = {a.platform for a in resolved_accounts if a.in_scope and a.platform}
    no_platform_types = [
        a.type
        for a in resolved_accounts
        if a.in_scope
        and not a.is_new
        and not a.id.startswith(UNRESOLVED_ID_PREFIX)
        and not a.platform
    ]
    # Value-cell markers (R6, P12) sit in the account table, which opens the report, so
    # they come first in the order number_markers numbers them by (P1).
    pension_markers, pension_review_items = _pension_markers(actions, resolved_accounts)
    markers = [
        *state_markers,
        *required_markers(in_scope_platforms, no_platform_types),
        *new_account_markers,
        *unresolved_scope.markers,
        *cgt_marker(tax_disposals),
        *bond_marker(disposals),
        *pension_markers,
        *available_markers,
        *amount_markers,
        *([selling_decision.marker] if selling_decision.marker else []),
        *tbc_field_markers(fields_by_canonical),
    ]

    facts = build_facts(
        resolved_accounts,
        action_amounts,
        proceeds_action_ids,
        money_items=other_money_items,
        available=available,
    )
    objectives = " ".join(o.text.text for o in meeting_extraction.objectives_and_circumstances)
    if meeting_date is not None:
        limit_items = _limit_review_items(
            actions,
            action_amounts,
            resolved_accounts,
            meeting_date,
            meeting_extraction.limit_signals,
        )
        markers += _limit_markers(
            actions,
            action_amounts,
            resolved_accounts,
            meeting_date,
            meeting_extraction.limit_signals,
        )
    else:
        limit_items = []

    unspecified = build_unspecified_amounts(
        actions,
        action_amounts,
        resolved_accounts,
        partial_disposals=_partial_disposals(
            meeting_extraction.disposals, resolved_accounts, set(disposal_proceeds_by_account)
        ),
        disposal_quotes=[d.quote.text for d in meeting_extraction.disposals],
        other_unspecified=len(pension_markers) + len(available_markers),
        taken_keys={m.key for m in markers},
        available=available,
        skip_action_ids=conflicted_action_ids,
    )
    markers += unspecified.markers

    image_items = _image_review_items(image_source, resolved_accounts, account_currency_by_id, llm)

    review_inputs: list[ReviewItemInput] = [
        *ownership.set_aside,
        *superseded_review_items,
        *(_open_action_item(oa, meeting_doc) for oa in meeting_extraction.open_actions),
        *money_review_items,
        *amount_review_items,
        *([selling_decision.review_item] if selling_decision.review_item else []),
        *new_account_review_items,
        *investigation.review_items,
        *(
            [several]
            if (
                several := several_records_review_item(
                    [s.path.name for s in meeting_sources], record_dates, governing
                )
            )
            else []
        ),
        *unresolved_scope.review_items,
        *missing_platform_review_items(resolved_accounts),
        *([undated] if (undated := undated_meeting_review_item(meeting_date)) else []),
        *disposal_review_items,
        *unspecified.review_items,
        *pension_review_items,
        *marker_review_items(markers),
        *limit_items,
        *image_items,
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
            money=money_items,
            actions=actions,
            excluded=excluded,
            markers=markers,
            review=build_review_items(review_inputs),
            questions=investigation.questions,
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
    plans = plan_sections(ledger, config, spec_text=spec_text, meeting_text=meeting_text)
    dangling = unrouted_markers(ledger, plans)
    if dangling:
        # A marker no section carries would vanish from the report silently; stop instead.
        raise WriterStopError(f"marker(s) reach no section (add a config selector): {dangling}")
    plans_by_section = {p.section_id: p for p in plans}
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
    for index in earlier_records:
        judge_sources[meeting_sources[index].path.name] = meeting_docs[index]
    judge_results = majority_release_judge(
        bundle,
        ledger,
        judge_sources,
        judge_models(
            llm,
            load_prompt(PROMPTS_DIR / "release_judge.md"),
            config.stages["release_judge"].samples,
        ),
    )

    return bundle, ledger, [*deterministic_results, *judge_results]
