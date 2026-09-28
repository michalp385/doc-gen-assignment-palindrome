"""The seeded scenario sampler for the synthetic clients (T27, D4, DESIGN.md section 10.8).

`sample_scenario(seed)` varies the SCOPING section 5 patterns: single or joint clients, a top-up
from cash or a sale of the GIA (stale statement value vs a live-viewed figure, a recalled
decoy), out-of-scope cash, an open account with no value (a blocking or a soft follow-up), a
closed account, a new joint account, money received / committed / contingent, tangents and
aspirations, and a distractor general document. From a scenario, code derives the account
JSON, the report-instruction fields, the phrases the meeting note must contain, the
distractor document and `ExpectedFacts` -- deterministically.

The generator encodes the same rules the pipeline implements (D4), so it catches
implementation errors, not rule errors; the hand-written cases cover the rules. Name and
figure pools are sampled, so this module holds no real client's values. Not yet sampled:
pension contributions and non-GBP accounts (the hand-written cases cover P4 pensions and P12).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from agent_pipeline.ledger import render_date
from report_eval.expected import ExpectedFacts
from report_eval.synth.phrases import RequiredPhrase, render

TAX_RULES = Path("config/tax_rules.json")
SNAPSHOT_DATE = date(2026, 4, 30)
TAX_YEAR = "2026/27"  # every sampled meeting date falls in May 2026

FIRST_NAMES = (
    "Alan Beatrice Colin Dorothy Edwin Frances Gordon Helen Ian Joyce Kenneth Lorna Malcolm "
    "Nora Oliver Patricia Quentin Rosalind Stuart Thelma Ursula Victor Wendy Xavier Yvonne Zachary"
).split()
SURNAMES = (
    "Ashworth Bellamy Cartwright Denholm Ellery Fairbrother Garrick Hollis Ingram Jessop Kerr "
    "Lambourn Marchant Norcott Oakden Pelham Quayle Rowntree Sedgwick Thackeray Umfreville "
    "Vickery Wadsworth Yardley"
).split()
ADVISERS = ("Priya Nandakumar", "Owen Trelawney", "Imogen Ashby", "Callum Dresner")
PLATFORMS = ("Ashgrove", "Tallowmere", "Wexcombe", "Pennington")
FUNDS = (
    "Larkspur Growth Fund",
    "Fenwick Income Fund",
    "Harrowgate Global Portfolio",
    "Cobalt Strategic Fund",
)
RISK_PROFILES = (
    "3 (cautious)",
    "4 (moderate)",
    "5 (balanced)",
    "4 (balanced to moderate)",
    "6 (adventurous)",
)
INITIAL_CHARGES = ("0%", "0.5%", "1%")
TANGENTS = (
    "a cruise they have booked for next spring",
    "a caravan they are thinking of buying",
    "their allotment and the new greenhouse",
    "a reunion with old university friends",
)
ASPIRATIONS = (
    "make gifts to their nephews and nieces",
    "help pay for a family wedding",
    "fund a bench in memory of a friend",
)
ORIGINS = ("a legacy from a relative", "the sale of a second home", "a maturing endowment policy")
PURPOSES = ("essential roof repairs", "clearing an outstanding loan", "a daughter's house deposit")
QUALIFIERS = ("a little over", "around", "a little under")


@dataclass(frozen=True)
class SynthAccount:
    id: str
    platform: str
    type: str
    owners: tuple[str, ...]
    status: str  # "open" | "closed"
    value: Decimal | None
    valuation_date: date | None
    in_scope: bool
    role: str  # "isa" | "cash" | "gia" | "dormant" | "closed"


@dataclass(frozen=True)
class MoneyPlan:
    received: Decimal
    committed: Decimal
    external: Decimal | None
    origin: str
    purpose: str


@dataclass(frozen=True)
class Scenario:
    seed: int
    client_id: str
    holders: tuple[str, ...]
    adviser: str
    meeting_date: date
    risk_profile: str
    initial_charge: str
    platform: str
    accounts: tuple[SynthAccount, ...]
    advice: str  # "topup" | "gia_sale"
    topup_amount: Decimal | None
    live_gia_value: Decimal | None
    live_qualifier: str
    stale_gia_date: date | None
    recalled_value: Decimal | None
    new_account: bool
    null_cash: bool
    null_cash_blocking: bool
    closed_cash: bool
    money: MoneyPlan | None
    tangent: str | None
    aspiration: str | None
    distractor_fund: str
    distractor_figure: Decimal
    variant: int

    @property
    def recalled_decoy(self) -> bool:
        return self.recalled_value is not None

    @property
    def names(self) -> str:
        return " and ".join(self.holders)

    def account(self, role: str) -> SynthAccount:
        return next(a for a in self.accounts if a.role == role)


def gbp(amount: Decimal) -> str:
    return f"£{int(amount):,}"


def _isa_allowance() -> Decimal:
    raw = json.loads(TAX_RULES.read_text(encoding="utf-8"))
    return Decimal(str(raw["isa"][TAX_YEAR]))


class _Amounts:
    """Round amounts drawn from the rng that never repeat, so a figure identifies one fact."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._used: set[Decimal] = set()

    def draw(self, low: int, high: int, step: int) -> Decimal:
        while True:
            amount = Decimal(self._rng.randrange(low, high, step))
            if amount not in self._used:
                self._used.add(amount)
                return amount

    def reserve(self, amount: Decimal) -> Decimal:
        self._used.add(amount)
        return amount


def sample_scenario(seed: int) -> Scenario:
    rng = random.Random(seed)
    amounts = _Amounts(rng)
    allowance = amounts.reserve(_isa_allowance())

    couple = rng.random() < 0.6
    firsts = rng.sample(FIRST_NAMES, 2 if couple else 1)
    surname = rng.choice(SURNAMES)
    holders = tuple(f"{first} {surname}" for first in firsts)
    platform = rng.choice(PLATFORMS)
    prefix = f"{platform[0]}{seed % 9 + 1}"
    initials = [first[0] for first in firsts]

    advice = "gia_sale" if rng.random() < 0.6 else "topup"
    accounts: list[SynthAccount] = [
        SynthAccount(
            id=f"{prefix}-ISA-{initial}",
            platform=platform,
            type="Stocks & Shares ISA",
            owners=(holder,),
            status="open",
            value=amounts.draw(85_000, 140_000, 500),
            valuation_date=SNAPSHOT_DATE,
            in_scope=True,
            role="isa",
        )
        for holder, initial in zip(holders, initials, strict=True)
    ]

    topup_amount: Decimal | None = None
    live_value: Decimal | None = None
    stale_date: date | None = None
    recalled: Decimal | None = None
    qualifier = rng.choice(QUALIFIERS)
    if advice == "topup":
        topup_amount = allowance if rng.random() < 0.5 else amounts.draw(6_000, 15_000, 500)
        accounts.append(
            SynthAccount(
                id=f"{prefix}-CASH-{initials[0]}",
                platform=platform,
                type="Cash Account",
                owners=(holders[0],),
                status="open",
                value=amounts.draw(50_000, 80_000, 500),
                valuation_date=SNAPSHOT_DATE,
                in_scope=False,
                role="cash",
            )
        )
    else:
        stale = amounts.draw(18_000, 36_000, 500)
        live_value = stale + amounts.draw(3_000, 9_000, 500)
        amounts.reserve(live_value)
        stale_date = date(2026, rng.choice([2, 3]), rng.randint(2, 27))
        if rng.random() < 0.4:
            recalled = amounts.draw(10_000, 17_000, 500)
        accounts.append(
            SynthAccount(
                id=f"{prefix}-GIA-{'J' if couple else initials[0]}",
                platform=platform,
                type="General Investment Account",
                owners=holders,
                status="open",
                value=stale,
                valuation_date=stale_date,
                in_scope=True,
                role="gia",
            )
        )

    null_cash = rng.random() < 0.35
    null_cash_blocking = rng.random() < 0.5
    if null_cash:
        accounts.append(
            SynthAccount(
                id=f"{prefix}-DORM-{initials[-1]}",
                platform=platform,
                type="Cash Account",
                owners=(holders[-1],),
                status="open",
                value=None,
                valuation_date=None,
                in_scope=False,
                role="dormant",
            )
        )
    closed_cash = rng.random() < 0.25
    if closed_cash:
        accounts.append(
            SynthAccount(
                id=f"{prefix}-OLD-{initials[0]}",
                platform=platform,
                type="Cash Account",
                owners=(holders[0],),
                status="closed",
                value=Decimal(0),
                valuation_date=date(2025, 11, 30),
                in_scope=False,
                role="closed",
            )
        )

    money: MoneyPlan | None = None
    if rng.random() < 0.25:
        received = amounts.draw(150_000, 350_000, 5_000)
        money = MoneyPlan(
            received=received,
            committed=amounts.draw(20_000, 90_000, 5_000),
            external=amounts.draw(50_000, 120_000, 5_000) if rng.random() < 0.6 else None,
            origin=rng.choice(ORIGINS),
            purpose=rng.choice(PURPOSES),
        )

    return Scenario(
        seed=seed,
        client_id=f"synth_{seed:03d}",
        holders=holders,
        adviser=rng.choice(ADVISERS),
        meeting_date=date(2026, 5, rng.randint(5, 28)),
        risk_profile=rng.choice(RISK_PROFILES),
        initial_charge=rng.choice(INITIAL_CHARGES),
        platform=platform,
        accounts=tuple(accounts),
        advice=advice,
        topup_amount=topup_amount,
        live_gia_value=live_value,
        live_qualifier=qualifier,
        stale_gia_date=stale_date,
        recalled_value=recalled,
        new_account=couple and advice == "gia_sale" and rng.random() < 0.4,
        null_cash=null_cash,
        null_cash_blocking=null_cash_blocking,
        closed_cash=closed_cash,
        money=money,
        tangent=rng.choice(TANGENTS) if rng.random() < 0.7 else None,
        aspiration=rng.choice(ASPIRATIONS) if rng.random() < 0.5 else None,
        distractor_fund=rng.choice(FUNDS),
        distractor_figure=amounts.draw(480_000, 990_000, 1_000),
        variant=rng.randint(0, 99),
    )


# --- the sources ---------------------------------------------------------------------------


def _record(account: SynthAccount, owner: str) -> dict[str, Any]:
    return {
        "account_id": account.id,
        "platform": account.platform,
        "type": account.type,
        "owner": owner,
        "status": account.status,
        "value": float(account.value) if account.value is not None else None,
        "currency": "GBP",
        "valuation_date": account.valuation_date.isoformat() if account.valuation_date else None,
    }


def account_data(scenario: Scenario) -> dict[str, Any]:
    """The account JSON. A joint account is recorded under each of its holders (SCOPING §5)."""
    sections = ("client", "partner")
    holders: dict[str, Any] = {}
    for section, holder in zip(sections, scenario.holders, strict=False):
        records = []
        for account in scenario.accounts:
            if holder not in account.owners:
                continue
            owner = "Joint" if len(account.owners) > 1 else holder
            records.append(_record(account, owner))
        holders[section] = {"name": holder, "accounts": records}
    return {"snapshot_date": SNAPSHOT_DATE.isoformat(), "holders": holders}


def _scope_phrase(scenario: Scenario) -> str:
    couple = len(scenario.holders) == 2
    firsts = " and ".join(h.split()[0] for h in scenario.holders)
    parts = [f"{scenario.platform} ISAs ({firsts})" if couple else f"{scenario.platform} ISA"]
    if scenario.advice == "gia_sale":
        parts.append("the joint GIA" if couple else "the GIA")
    if scenario.new_account:
        parts.append("a new joint account")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def instruction_fields(scenario: Scenario) -> list[tuple[str, str]]:
    couple = len(scenario.holders) == 2
    if scenario.advice == "topup":
        assert scenario.topup_amount is not None
        amount = f"GBP {int(scenario.topup_amount):,}"
        source = f"Cash held on deposit in the {scenario.platform} cash account"
        product = "Top up of existing Stocks & Shares ISA"
        selling = "No"
    else:
        gia = "joint GIA" if couple else "GIA"
        amount = f"Full value of the {gia}"
        source = "Joint General Investment Account" if couple else "General Investment Account"
        product = "Top up of Stocks & Shares ISA" + ("s" if couple else "")
        if scenario.new_account:
            product += " and a new joint investment account"
        selling = "Yes"
    return [
        ("Adviser", scenario.adviser),
        ("Accounts covered", _scope_phrase(scenario)),
        ("Investment amount", amount),
        ("Source of funds", source),
        ("Selling existing investments?", selling),
        ("Product recommended", product),
        ("Held in single or joint name?", "Joint clients, individual ISAs" if couple else "Single"),
        ("Agreed risk profile", scenario.risk_profile),
        ("Initial charge", scenario.initial_charge),
    ]


def distractor_text(scenario: Scenario) -> str:
    """A general document with a platform-wide figure and a fund name: never a source of
    client facts (SCOPING R7), and the eval's `must_not_appear` distractor."""
    return "\n\n".join(
        [
            f"{scenario.platform} Platform: Half-Year Market Review",
            "This bulletin goes to every advised client of the platform. It is general market "
            "commentary and does not relate to any individual client's accounts or "
            "recommendations.",
            f"Our {scenario.distractor_fund}, an illustrative model allocation, rose over the "
            f"period and stood at about {gbp(scenario.distractor_figure)} in aggregate at its "
            "close. This is a platform-wide figure and not a holding of any individual client.",
            "Investments can go down as well as up, and you may not get back the full amount "
            "you put in.",
        ]
    )


def brief(scenario: Scenario) -> str:
    """What the prose model is told: the shape of the meeting and the rules, with no money
    figure or percentage it could copy (the required sentences carry those)."""
    topics = [
        "their objectives and circumstances, unchanged since the last review",
        "their agreed attitude to risk",
    ]
    if scenario.advice == "gia_sale":
        topics.append("what to do with their General Investment Account")
    else:
        topics.append("using this year's ISA allowance")
    if scenario.null_cash:
        topics.append("a cash account with no balance on file")
    return (
        f"Write an adviser's file note of a review meeting with {scenario.names}, who hold "
        f"accounts on the {scenario.platform} platform. Cover: {'; '.join(topics)}. Write "
        "eight to fourteen short paragraphs in a plain, professional voice. Include every "
        "required sentence exactly as given, unchanged. Do not state any other amount of "
        "money, percentage or number written out in words, and do not mention any account "
        "values beyond the required sentences."
    )


# --- the phrases the meeting note must contain ---------------------------------------------


def required_phrases(scenario: Scenario) -> list[RequiredPhrase]:
    v = scenario.variant
    names = scenario.names
    couple = len(scenario.holders) == 2
    phrases: list[RequiredPhrase] = [
        RequiredPhrase(
            "meeting_open",
            render(
                "meeting_open",
                v,
                names=names,
                date=f"{scenario.meeting_date.day} {scenario.meeting_date.strftime('%B %Y')}",
            ),
        )
    ]
    isa_destination = (
        "the Stocks & Shares ISAs of both clients" if couple else "the Stocks & Shares ISA"
    )
    if scenario.advice == "topup":
        assert scenario.topup_amount is not None
        amount = gbp(scenario.topup_amount)
        phrases.append(
            RequiredPhrase(
                "topup",
                render(
                    "topup",
                    v,
                    names=names,
                    amount=amount,
                    source=f"{scenario.platform} cash account",
                    destination=f"{scenario.holders[0]}'s Stocks & Shares ISA",
                ),
                (amount,),
            )
        )
        phrases.append(RequiredPhrase("no_sale", render("no_sale", v)))
    else:
        assert scenario.live_gia_value is not None
        gia = "joint General Investment Account" if couple else "General Investment Account"
        live = gbp(scenario.live_gia_value)
        phrases.append(
            RequiredPhrase(
                "live_view",
                render(
                    "live_view",
                    v,
                    account=gia,
                    names=names,
                    amount_text=f"{scenario.live_qualifier} {live}",
                ),
                (live,),
            )
        )
        if scenario.recalled_value is not None:
            recalled = gbp(scenario.recalled_value)
            phrases.append(
                RequiredPhrase(
                    "recalled",
                    render(
                        "recalled", v, names=names, account=gia, amount_text=f"around {recalled}"
                    ),
                    (recalled,),
                )
            )
        phrases.append(
            RequiredPhrase(
                "sale_full",
                render("sale_full", v, account=gia, names=names, destination=isa_destination),
            )
        )
        phrases.append(RequiredPhrase("part_funded", render("part_funded", v)))
        if scenario.new_account:
            phrases.append(RequiredPhrase("new_account", render("new_account", v, names=names)))
    if scenario.money is not None:
        m = scenario.money
        received, committed = gbp(m.received), gbp(m.committed)
        phrases.append(
            RequiredPhrase(
                "received", render("received", v, amount=received, origin=m.origin), (received,)
            )
        )
        phrases.append(
            RequiredPhrase(
                "committed",
                render("committed", v, amount=committed, purpose=m.purpose),
                (committed,),
            )
        )
        if m.external is not None:
            external = gbp(m.external)
            phrases.append(
                RequiredPhrase("contingent", render("contingent", v, amount=external), (external,))
            )
    if scenario.null_cash:
        dormant = scenario.account("dormant")
        pattern = "precondition_blocking" if scenario.null_cash_blocking else "precondition_soft"
        phrases.append(
            RequiredPhrase(
                pattern,
                render(pattern, v, holder=dormant.owners[0], platform=dormant.platform),
            )
        )
    if scenario.tangent:
        phrases.append(
            RequiredPhrase("tangent", render("tangent", v, names=names, subject=scenario.tangent))
        )
    if scenario.aspiration:
        phrases.append(
            RequiredPhrase(
                "aspiration", render("aspiration", v, names=names, subject=scenario.aspiration)
            )
        )
    return phrases


# --- the expected facts --------------------------------------------------------------------


def _phrase(scenario: Scenario, pattern: str) -> str:
    return next(p.text for p in required_phrases(scenario) if p.pattern == pattern)


def expected_facts(scenario: Scenario) -> ExpectedFacts:
    """The facts a correct run produces for this scenario, derived by the same rules the
    pipeline implements (D4)."""
    couple = len(scenario.holders) == 2
    meeting = scenario.meeting_date
    rows: list[dict[str, Any]] = []
    not_in_table: list[dict[str, str]] = []
    figures: list[dict[str, Any]] = []
    markers: list[dict[str, str]] = []
    review: list[dict[str, Any]] = []
    extraction: dict[str, list[dict[str, Any]]] = {
        "value_observations": [],
        "money_items": [],
        "disposals": [],
        "open_actions": [],
    }

    live = scenario.live_gia_value
    for account in scenario.accounts:
        if not account.in_scope:
            reason = (
                "closed"
                if account.status == "closed"
                else "no_value"
                if account.value is None
                else "out_of_scope"
            )
            not_in_table.append({"account": account.id, "reason": reason})
            continue
        row: dict[str, Any] = {
            "account": account.id,
            "owners": list(account.owners),
            "type": account.type,
        }
        assert account.value is not None
        if account.role == "gia" and live is not None:
            assert scenario.stale_gia_date is not None
            row["value"] = f"c. {gbp(live)}"
            row["footnote"] = (
                f"Meeting note, {render_date(meeting)} {meeting.year}: "
                f'"{scenario.live_qualifier} {gbp(live)}". Last statement value: '
                f"{gbp(account.value)} at {render_date(scenario.stale_gia_date)} "
                f"{scenario.stale_gia_date.year}."
            )
            figures.append({"value": row["value"], "placement": "any"})
            figures.append({"value": gbp(account.value), "placement": "footnote_only"})
        else:
            row["value"] = gbp(account.value)
            figures.append({"value": row["value"], "placement": "any"})
        rows.append(row)
    if scenario.new_account:
        rows.append(
            {
                "account": "new:joint_investment_account",
                "owners": list(scenario.holders),
                "type": "New joint account",
                "value": "To be opened",
            }
        )
    figures.append({"value": scenario.initial_charge, "placement": "any"})

    markers += [
        {
            "key": f"platform_charge_{scenario.platform.lower()}",
            "description": f"ongoing platform charge rate, {scenario.platform}",
        },
        {"key": "advice_charge", "description": "ongoing advice charge rate"},
    ]

    actions: list[dict[str, Any]] = []
    isa_ids = [a.id for a in scenario.accounts if a.role == "isa"]
    if scenario.advice == "topup":
        assert scenario.topup_amount is not None
        cash = scenario.account("cash")
        figures.append({"value": gbp(scenario.topup_amount), "placement": "any"})
        actions.append(
            {
                "description": (
                    f"Move {gbp(scenario.topup_amount)} from the {scenario.platform} cash "
                    f"account into {scenario.holders[0]}'s Stocks & Shares ISA"
                ),
                "kind": "action",
                "accounts": [cash.id, isa_ids[0]],
            }
        )
        if scenario.topup_amount == _isa_allowance():
            review.append(
                {
                    "key": "isa_allowance_prior_use",
                    "kind": "p4_note",
                    "blocking": False,
                    "must_mention": [gbp(scenario.topup_amount), "ISA allowance"],
                }
            )
    else:
        assert live is not None and scenario.stale_gia_date is not None
        gia = scenario.account("gia")
        assert gia.value is not None
        sale = _phrase(scenario, "sale_full")
        live_text = _phrase(scenario, "live_view")
        markers += [
            {
                "key": "cgt",
                "description": (
                    "capital gains tax on the disposal of the joint GIA"
                    if couple
                    else "capital gains tax on the disposal of the GIA"
                ),
            },
            {
                "key": "isa_amounts",
                "description": (
                    "ISA top-up amounts and the resulting balance for the new joint account"
                    if scenario.new_account
                    else "ISA top-up amounts within the remaining allowances, and where any "
                    "excess goes"
                ),
            },
        ]
        review += [
            {
                "key": "gia_superseded_value",
                "kind": "superseded",
                "blocking": False,
                "must_mention": [
                    gbp(gia.value),
                    render_date(scenario.stale_gia_date),
                    f"c. {gbp(live)}",
                    render_date(meeting),
                ],
            },
            {
                "key": "isa_excess_destination",
                "kind": "p4_note",
                "blocking": False,
                "must_mention": ["ISA allowance", "excess"],
            },
        ]
        destination = "top up the ISAs" if couple else "top up the ISA"
        actions.append(
            {
                "description": (
                    f"Sell the {'joint ' if couple else ''}GIA in full and use the proceeds to "
                    f"{destination}"
                    + (
                        ", with the balance into a new joint account"
                        if scenario.new_account
                        else ""
                    )
                ),
                "kind": "action",
                "accounts": [gia.id, *isa_ids],
            }
        )
        extraction["value_observations"].append(
            {
                "account": gia.id,
                "amount_quote": f"{scenario.live_qualifier} {gbp(live)}",
                "basis": "viewed_in_meeting",
                "evidence_quote": live_text,
            }
        )
        if scenario.recalled_value is not None:
            extraction["value_observations"].append(
                {
                    "account": gia.id,
                    "amount_quote": f"around {gbp(scenario.recalled_value)}",
                    "basis": "recalled",
                    "evidence_quote": _phrase(scenario, "recalled"),
                }
            )
        extraction["disposals"].append(
            {"account": gia.id, "extent": "full", "evidence_quote": sale}
        )
        extraction["money_items"].append({"class": "proceeds", "evidence_quote": sale})

    if scenario.new_account:
        markers.append(
            {"key": "new_account_charges", "description": "charges on the new joint account"}
        )
        review.append(
            {
                "key": "new_account_type_platform",
                "kind": "scope_flag",
                "blocking": False,
                "must_mention": ["new", "joint", "account"],
            }
        )

    if scenario.null_cash:
        dormant = scenario.account("dormant")
        holder_first = dormant.owners[0].split()[0]
        pattern = "precondition_blocking" if scenario.null_cash_blocking else "precondition_soft"
        text = _phrase(scenario, pattern)
        review.append(
            {
                "key": "dormant_cash_account",
                "kind": "open_action",
                "blocking": scenario.null_cash_blocking,
                "must_mention": [holder_first, "cash"],
            }
        )
        review.append(
            {
                "key": "dormant_cash_no_value",
                "kind": "out_of_scope_no_value",
                "blocking": False,
                "must_mention": ["Cash Account"],
            }
        )
        extraction["open_actions"].append(
            {
                "description": f"Check {holder_first}'s cash account",
                "blocking": scenario.null_cash_blocking,
                "evidence_quote": text,
            }
        )

    if scenario.money is not None:
        m = scenario.money
        received, committed = gbp(m.received), gbp(m.committed)
        available = m.received - m.committed
        # Money context, not an instruction to invest it: figures may appear or not.
        figures += [
            {"value": received, "placement": "any", "optional": True},
            {"value": committed, "placement": "any", "optional": True},
            {
                "value": gbp(available),
                "placement": "any",
                "optional": True,
                "derived_from": [received, committed],
            },
        ]
        extraction["money_items"] += [
            {
                "class": "received",
                "amount_quote": received,
                "evidence_quote": _phrase(scenario, "received"),
            },
            {
                "class": "committed",
                "amount_quote": committed,
                "evidence_quote": _phrase(scenario, "committed"),
            },
        ]
        if m.external is not None:
            external = f"up to {gbp(m.external)}"
            figures.append({"value": external, "placement": "any", "optional": True})
            extraction["money_items"].append(
                {
                    "class": "external",
                    "amount_quote": gbp(m.external),
                    "evidence_quote": _phrase(scenario, "contingent"),
                }
            )

    excluded: list[dict[str, str]] = []
    if scenario.tangent:
        excluded.append({"class": "tangent", "subject": scenario.tangent})
    if scenario.aspiration:
        excluded.append({"class": "aspiration", "subject": scenario.aspiration})

    return ExpectedFacts.model_validate(
        {
            "client": scenario.client_id,
            "meeting_date": scenario.meeting_date.isoformat(),
            "risk_profile": scenario.risk_profile,
            "initial_charge": scenario.initial_charge,
            "release": {"state": "draft"},
            "table_rows": rows,
            "not_in_table": not_in_table,
            "reportable_figures": figures,
            "markers": markers,
            "review_items": review,
            "sections": {"tax_implications": scenario.advice == "gia_sale"},
            "actions": actions,
            "excluded_items": excluded,
            "must_not_appear": [scenario.distractor_fund, gbp(scenario.distractor_figure)],
            "extraction": extraction,
        }
    )
