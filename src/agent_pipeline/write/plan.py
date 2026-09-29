"""Section planning (DESIGN.md section 6): resolve each included section's config-declared
selectors against the ledger into a `SectionPlan` holding only that section's own facts
(description + role, never a number), its markers, and its extraction-derived text rewritten
digit-free. Pure code, no model call (stage 4).
"""

from __future__ import annotations

import fnmatch

from agent_pipeline.config import ReportConfig, Section
from agent_pipeline.gates.deterministic import (
    MONEY_RE,
    PERCENT_RE,
    WORD_FIGURE_RE,
    WORD_PERCENT_RE,
)
from agent_pipeline.ledger import Account, Ledger
from agent_pipeline.reconcile.predicates import section_included
from agent_pipeline.write.schemas import PlanFact, PlanMarker, SectionPlan, WithheldText


class PlanningError(Exception):
    """A section's predicate has no ledger-level resolution -- never a silent default."""


def _section_included(section: Section, ledger: Ledger) -> bool:
    try:
        return section_included(section, ledger)
    except KeyError as exc:
        raise PlanningError(str(exc)) from exc


def _match_any(patterns: list[str], value: str) -> bool:
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def has_figure(text: str) -> bool:
    """Any money or percentage figure, in digits or in words."""
    return bool(
        MONEY_RE.search(text)
        or PERCENT_RE.search(text)
        or WORD_FIGURE_RE.search(text)
        or WORD_PERCENT_RE.search(text)
    )


def rewrite_digit_free(
    text: str, facts: list[PlanFact], ledger: Ledger
) -> tuple[str | None, WithheldText | None]:
    """A span matching a known fact's quote becomes that fact's token; if a money or
    percentage figure (digits or words) remains unmatched, the whole text is withheld
    (DESIGN.md section 6)."""
    rewritten = text
    for fact in facts:
        ledger_fact = ledger.facts.get(fact.id)
        quote = ledger_fact.value.quote if ledger_fact and ledger_fact.value else ""
        if quote and quote in rewritten:
            rewritten = rewritten.replace(quote, f"{{fact:{fact.id}}}")
    if has_figure(rewritten):
        return None, WithheldText(
            original=text,
            reason="contains a money or percentage figure not matched to a known fact",
        )
    return rewritten, None


def _join(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _describe_scope(ledger: Ledger) -> str:
    """T19, client 02's three in-scope accounts: naming every one as "your <type>" and
    joining with "and" repeats "held with <platform>" once per account and can't tell two
    same-type accounts apart (client 02's own two ISAs) -- fine for client 01's one account,
    unusable past it. Same-type accounts with a single owner are named by that owner's
    first name instead (never for a genuinely joint account, which already reads as
    "your"); every in-scope account sharing one platform states it once, trailing."""
    in_scope = [a for a in ledger.accounts if a.in_scope]
    if not in_scope:
        return ""
    type_counts: dict[str, int] = {}
    for account in in_scope:
        type_counts[account.type] = type_counts.get(account.type, 0) + 1

    def _label(account: Account) -> str:
        if type_counts[account.type] > 1 and len(account.owners) == 1:
            return f"{account.owners[0].split()[0]}'s {account.type}"
        return f"your {account.type}"

    labels = [_label(a) for a in in_scope]
    platforms = {a.platform for a in in_scope if a.platform}
    # One trailing "held with X" is only true when every listed account has that platform; an
    # account with none (a new account's platform is unstated) is named without one.
    if len(platforms) != 1 or any(not a.platform for a in in_scope):
        return _join(
            [
                f"{label} held with {a.platform}" if a.platform else label
                for label, a in zip(labels, in_scope, strict=True)
            ]
        )
    platform = next(iter(platforms))
    if len(labels) == 1:
        return f"{labels[0]} held with {platform}"
    return f"{_join(labels)}, held with {platform}"


def _context_values(ledger: Ledger) -> dict[str, str]:
    """Every context key `plan_sections` can resolve from the ledger itself, keyed the same
    way a section's `context` selector names them. A key with nothing to resolve (e.g.
    `objectives` before real extraction/reconciliation populates `ledger.objectives`, T16) is
    simply absent, so `extra_context` can still supply it for now."""
    values = {"scope_description": _describe_scope(ledger)}
    if ledger.objectives:
        values["objectives"] = ledger.objectives
    return values


def unrouted_markers(ledger: Ledger, plans: list[SectionPlan]) -> list[str]:
    """The ledger markers that no included section's plan carries, in ledger order: a marker
    that reaches no section would silently vanish from the report while still counting on the
    review sheet (P1 needs each marker in the text). A value-cell marker
    (`section == "account_table"`) is placed by the table, not a section plan. The pipeline
    fails the run on any result rather than drop it."""
    routed = {marker.key for plan in plans for marker in plan.markers}
    return [m.key for m in ledger.markers if m.section != "account_table" and m.key not in routed]


def plan_sections(
    ledger: Ledger,
    config: ReportConfig,
    *,
    extra_context: dict[str, dict[str, str]] | None = None,
    spec_text: str = "",
    meeting_text: str = "",
) -> list[SectionPlan]:
    extra_context = extra_context or {}
    context_values = _context_values(ledger)
    plans: list[SectionPlan] = []

    for section in config.sections:
        if not _section_included(section, ledger):
            continue

        facts = [
            PlanFact(
                id=fact_id,
                description=fact.description,
                role=fact.role,
                transaction=fact.transaction,
            )
            for fact_id, fact in ledger.facts.items()
            if _match_any(section.facts, fact_id)
        ]
        markers = [
            PlanMarker(key=marker.key, text=marker.text)
            for marker in ledger.markers
            if _match_any(section.markers, marker.key)
        ]

        rewritten_texts: dict[str, str] = {}
        withheld: list[WithheldText] = []

        if "actions" in section.text_sources:
            for action in ledger.actions:
                rewritten, defect = rewrite_digit_free(action.description, facts, ledger)
                if defect is not None:
                    withheld.append(defect)
                elif rewritten is not None:
                    rewritten_texts[f"action.{action.id}"] = rewritten

        if "excluded" in section.text_sources:
            for item in ledger.excluded:
                if not _match_any(section.excluded, item.item_class):
                    continue
                rewritten, defect = rewrite_digit_free(item.description, facts, ledger)
                if defect is not None:
                    withheld.append(defect)
                elif rewritten is not None:
                    rewritten_texts[f"excluded.{item.id}"] = rewritten

        context: dict[str, str] = {
            key: context_values[key] for key in section.context if key in context_values
        }
        context.update(extra_context.get(section.id, {}))

        plans.append(
            SectionPlan(
                section_id=section.id,
                facts=facts,
                markers=markers,
                context=context,
                spec_text=spec_text,
                meeting_text=meeting_text,
                rewritten_texts=rewritten_texts,
                withheld=withheld,
            )
        )

    return plans
