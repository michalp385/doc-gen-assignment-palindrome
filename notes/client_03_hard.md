# client_03_hard: findings

Written independently of SCOPING.md §5–§7. Trust rules applied are SCOPING.md §3.1 (R1–R7) and
policies §4 (P1–P10). "Interpretation:" marks anything that is not a direct reading of a source.

Sources read: `client_data_db.json`, `meeting_notes.docx`, `report_request.docx`, `fde_notes.md`,
`platform_market_update.docx`, `portfolio_pack.docx`, `template_spec.md`, `statement_summary.png`
(882×366, read in full).

Key dates: `snapshot_date` "2026-04-30"; meeting "held 16 May 2026".
Holders: `client` "Robert Fletcher", `partner` "Jean Fletcher". Adviser "Daniel Reeves".

## Accounts (deduplicated)

| Account | Owner | Type | Value | Value date | Source | In scope? | Notes |
|---|---|---|---|---|---|---|---|
| H-ISA-R (Holloway) | Robert Fletcher | Stocks & Shares ISA | £70,000 | 2026-04-30 | db `"value": 70000.0`; image "Holloway ISA (Robert) … £70,000 … 30 Apr 2026" | Yes: "Holloway ISAs (Robert and Jean)" | Agree. |
| H-ISA-JE (Holloway) | Jean Fletcher | Stocks & Shares ISA | £66,000 | 2026-04-30 | db `"value": 66000.0`; image "£66,000 … 30 Apr 2026" | Yes | Agree. |
| H-GIA-JF (Holloway) | Joint → Robert Fletcher & Jean Fletcher | General Investment Account | **c. £38,000** (live, "around") | 16 May 2026 (meeting) | meeting "Pulling it up during the meeting, it was showing around £38,000, a little higher than the figure on the last statement they had to hand." | Yes: "the joint GIA" | Superseded: £30,000 at 2026-03-10 (db; image "£30,000 … 10 Mar 2026"). R3 → c. £38,000. Being sold ("disinvest the joint GIA"). |
| New joint investment account | Robert Fletcher & Jean Fletcher | Not specified beyond "joint investment account" | To be opened | — | request "a new joint account"; meeting "open a new jointly-held investment account for the balance" | Yes | R1: new account from request/meeting → "To be opened". Account type/wrapper not named (interpretation: a GIA, but unstated). |
| H-CASH-JE (Holloway) | Jean Fletcher | Cash Account | **null** | null | db `"value": null, "valuation_date": null, "status": "open"` | No | R6: out-of-scope open account with no value → review sheet only. Probably the account in meeting: "another small cash account from some years ago … could not recall the balance and was not even sure it was still active" (interpretation: meeting names no platform or ID; db says open, meeting says maybe not). |

Duplicate: H-GIA-JF listed under both holders with identical fields. Count once.

Statement image: 3 rows (both ISAs, GIA at £30,000 / 10 Mar 2026), identical to db; omits the cash
account. All values in £.

## Conflicts

- GIA value: £30,000 (10 Mar 2026, db + image) vs "around £38,000" (16 May 2026, meeting) → R3 → c.
  £38,000. **Internal inconsistency in the meeting:** it calls £38,000 "a little higher than the figure
  on the last statement", but £38,000 is ~27% above £30,000. Fact: both numbers are as quoted.
  Interpretation: either the client's "last statement they had to hand" wasn't the 10 Mar one, or
  "a little" is loose. R3 still selects £38,000; the review sheet should show both and the size of the
  jump. A rule that sanity-checks large live-vs-statement jumps doesn't exist in §3.
- Inheritance amount: meeting "an inheritance of around £120,000"; request "Investment amount \| GBP
  120,000 inheritance plus the full joint GIA value". R5 → exact £120,000 from the request.
- Jean's cash account status: db `"status": "open"` vs meeting "not even sure it was still active".
  R1 (db wins on existence/status) → open, value unknown. Out of scope, so review sheet only.
- Decisions agree: meeting "disinvest the joint GIA" / request "Selling existing investments? \| Yes".
- Risk: meeting "Both remain at a moderate risk level"; request "4 (moderate)". Agree.

## Money available vs not available

- Inheritance: £120,000 (R5), received: "which has now cleared".
- GIA proceeds: c. £38,000 (approximate; request "the full joint GIA value").
- Total to invest: c. £158,000 (calculation £120,000 + c. £38,000; approximate because one term is).
- Allocation: "fund both Robert's and Jean's ISAs for the new tax year and open a new jointly-held
  investment account for the balance". **No ISA amounts are given**, per person or in total; no split.
  Interpretation: "fund … for the new tax year" suggests full allowance each, but no source states an
  amount, and no source says whether either ISA already has subscriptions this tax year. The new
  joint account's amount ("the balance") is therefore also not computable. Both are gaps.
- Jean's cash account: balance unknown; not part of the plan.

## Distractors to ignore

- Market update: "Our in-house Marlow Multi-Asset Fund … returned 6.4 per cent … around £515,000 in
  aggregate".
- Portfolio pack: "We added the Tavener Income Fund … around £525,000 of assets under management."
- Paraphrased warnings: market update "the value of investments may go down as well as up"; pack
  "the value of investments, and any income from them, may fall as well as recover".
- Pack "Costs" paragraph mentions "Platform and advice charges are separate" — no figures; still not a
  source of charges.

## Must not be actioned

- "We talked about their grandchildren and a trip they have planned later in the year; nothing there
  changes the advice."
- Personal detail: "grateful for the flowers the office had sent" — not report content.

## Gaps a person must fill

- CGT on the GIA disposal: "Selling down the GIA is a disposal, so there is a capital gains position
  to set out in the report."
- Platform charge rate(s), including for the new joint account: "Robert asked about the charges on the
  new joint account; I said the report would set those out once verified."
- Ongoing advice charge rate.
- ISA contribution amounts (each) and hence the new joint account amount.
- Jean's cash account balance/status: "She will dig out the paperwork and we will confirm it before
  anything is finalised." Interpretation: "before anything is finalised" could make this a blocker for
  sign-off, not merely a review-sheet note; R6 puts it on the review sheet only. Ambiguous.
- Initial charge: "Initial charge \| 0.5%" (request) — stated as given (P3). The base it applies to is
  not stated; interpretation: don't compute a £ amount.

## Per-client instructions

- `fde_notes.md` "## This client": "The new money being invested is an inheritance the client received
  following the recent death of her mother. Reference its origin with appropriate sensitivity."
- Note: fde_notes calls the inheritor "the client" ("her mother"), but the db makes Robert the
  `client` and Jean the `partner`. Meeting settles who: "Jean has received an inheritance … from her
  late mother's estate". Interpretation: "client" in fde_notes means the household, not the db role;
  any rule keyed on db role "client" would misattribute.
- Meeting next steps: "handle the inheritance sensitively".

## Other facts for Background

- "Their objectives are unchanged from the last review: long-term growth, with no income required from
  the portfolio for the foreseeable future."
- "Jean's mother had passed away earlier in the spring."
- Request "Held in single or joint name? \| Joint clients, individual ISAs plus a joint account".

## Pipeline risks

- Using £30,000 (stale) or stating £38,000 as exact.
- Using "around £120,000" instead of the exact request figure.
- Inventing ISA amounts (e.g. £20,000 each) or a new-account balance.
- Including the null cash account in the table, or giving it £0.
- Quoting fde_notes text ("recent death of her mother") in the report; handling bereavement bluntly.
- Quoting Marlow/Tavener figures.
- GIA listed twice.
