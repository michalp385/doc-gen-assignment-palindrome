# client_04_stretch: findings

Written independently of SCOPING.md §5–§7. Trust rules applied are SCOPING.md §3.1 (R1–R7) and
policies §4 (P1–P10). "Interpretation:" marks anything that is not a direct reading of a source.

Sources read: `client_data_db.json`, `meeting_notes.docx`, `report_request.docx`, `fde_notes.md`,
`platform_market_update.docx`, `portfolio_pack.docx`, `template_spec.md`, `statement_summary.png`
(882×366, read in full).

Key dates: `snapshot_date` "2026-04-30"; meeting "held 20 May 2026".
Holders: `client` "James Whitmore", `partner` "Caroline Whitmore". Adviser "Daniel Reeves".

## Accounts (deduplicated)

Scope (request): "Holloway ISAs (James and Caroline), Brightwell SIPPs (James and Caroline), the joint
GIAs (Holloway and Brightwell), the Meridian offshore bond, plus a new joint account for the proceeds".

| Account | Owner | Type | Value | Value date | Source | In scope? | Notes |
|---|---|---|---|---|---|---|---|
| H4-ISA-J (Holloway) | James Whitmore | Stocks & Shares ISA | £85,000 | 2026-04-30 | db; image "Holloway ISA (James) … £85,000 … 30 Apr 2026" | Yes | Receives ISA subscription. |
| H4-ISA-C (Holloway) | Caroline Whitmore | Stocks & Shares ISA | £82,000 | 2026-04-30 | db; image "£82,000 … 30 Apr 2026" | Yes | Receives ISA subscription. |
| H4-GIA-HJ (Holloway) | Joint → James & Caroline Whitmore | General Investment Account | **c. £255,000** (live, "around") | 20 May 2026 (meeting) | meeting "pulling it up live, it was showing around £255,000. That is noticeably higher than the figure on the snapshot I had, which was struck back in February" | Yes | Superseded £240,000 at 2026-02-28 (db; image "£240,000 … 28 Feb 2026"). R3 → c. £255,000. Partial disposal *and* an addition. |
| B4-SIPP-J (Brightwell) | James Whitmore | SIPP | £610,000 | 2026-04-30 | db | Yes | Meeting: "These were all in line with the snapshot and we did not see any need to revise them." Receives contribution. |
| B4-SIPP-C (Brightwell) | Caroline Whitmore | SIPP | £430,000 | 2026-04-30 | db | Yes | As above. |
| B4-GIA-J (Brightwell) | Joint → James & Caroline Whitmore | General Investment Account | £95,000 | 2026-04-30 | db | Yes | "in line with the snapshot". No action stated. |
| M4-BOND-J (Meridian) | Joint → James & Caroline Whitmore | Offshore Investment Bond | £180,000 | 2026-04-30 | db | Yes | Meeting: "we agreed to leave it as it is for now and revisit at the next review." In table, no action. |
| New joint investment account | James & Caroline Whitmore | Not specified | To be opened | — | request "a new joint account for the proceeds"; meeting "place the remaining balance into a new jointly-held investment account" | Yes | R1 → "To be opened". |
| M4-CASH-J (Meridian) | James Whitmore | Cash Account | £30,000 | 2026-04-30 | db `"owner": "James Whitmore"`; meeting "James holds a cash account there" | **No** (not in request) | R2 → excluded from table despite having a value. ID ends "-J" like the joint accounts, but owner is James alone (R1: db owner field wins, not the ID). |
| M4-CASH-C (Meridian) | Caroline Whitmore | Cash Account | **null** | null | db `"value": null, "valuation_date": null, "status": "open"`; meeting "she could not remember the balance and thought it might be fairly small; she will confirm it" | No | R6 → review sheet only. |
| M4-OLD-C (Meridian) | Caroline Whitmore | Cash Account | £0.00 | 2025-11-30 | db `"status": "closed", "value": 0.0`; meeting "closed last year; that one has nothing in it and can be disregarded" | No | R6: closed → ignored. Note value is `0.0`, not null. |

Duplicates: H4-GIA-HJ, B4-GIA-J and M4-BOND-J each appear under both holders. Count once each.
Interpretation: in-scope table = 7 existing accounts + 1 new = 8 rows.

Statement image: titled "Holloway Account Statement", shows only the three Holloway accounts; all match
the db (incl. GIA £240,000 / 28 Feb 2026). Contains no Brightwell/Meridian data. All values in £.

Totals (interpretation, calculation only, not needed by the spec): in-scope existing accounts =
85,000 + 82,000 + c. 255,000 + 610,000 + 430,000 + 95,000 + 180,000 = c. £1,737,000.

## Conflicts

- Holloway GIA: £240,000 (28 Feb 2026, db + image) vs "around £255,000" (20 May 2026, meeting) → R3.
- Risk: meeting "a balanced-to-moderate risk appetite"; request "Agreed risk profile \| 4 (balanced to
  moderate)". Agree with each other. **Cross-client label drift:** client_01/03 request "4 (moderate)",
  client_02 "5 (balanced)", client_04 "4 (balanced to moderate)". Interpretation: labels are not a
  stable mapping from number; the report should copy the request's wording rather than derive a label.
- Selling: request "Yes (partial rebalance of the Holloway joint GIA)"; meeting "disinvest a portion of
  the Holloway joint GIA and rebalance it; that sale is a disposal". Agree.
- No value conflicts for Brightwell/Meridian (meeting confirms snapshot).

## Money available vs not available

| Item | Amount | Source | Status |
|---|---|---|---|
| Completion payment | £850,000 | meeting "a completion payment of £850,000 was received on completion and is currently sitting in a solicitor's client account ready to be moved" | Received |
| Committed: bridging loan | £200,000 | meeting "£200,000 of the £850,000 is already committed to repaying a bridging loan … That repayment is due shortly." | Committed → subtract (P5) |
| **Available to invest** | **£650,000** | calculation £850,000 − £200,000 | Derived in code |
| Deferred earnout | "up to £400,000" | meeting "contingent on the business hitting agreed revenue targets. None of the earnout has been received yet … not guaranteed" | Contingent → excluded, named as excluded (P5) |
| Consultancy income | none stated | "James may do some consultancy work but nothing is settled" | Not money; not to be relied on |
| GIA partial sale proceeds | unspecified ("a portion") | meeting | Interpretation: "disinvest a portion … and rebalance it" reads as a sale *within* the GIA being rebalanced; the sources don't say whether proceeds join the £650,000 pool. Ambiguous. |

Request: "Investment amount \| Proceeds from the recent business sale (see meeting notes)" — defers to
the meeting; no conflict.

Allocation of the £650,000 (meeting): "use both ISA allowances for the new tax year, make pension
contributions into both SIPPs up to the appropriate level, add to the Holloway joint GIA, and place the
remaining balance into a new jointly-held investment account."
- ISA amounts: "use both ISA allowances" — no figure in any source (P4: allowance figure never quoted).
- SIPP amounts: "up to the appropriate level" — no figure; meeting: "the report would not commit to a
  figure that breached the limits". → marker (P2 breach-risk).
- Holloway GIA addition: no amount.
- New joint account: "the remaining balance" — not computable because the three items above are
  unknown.
Interpretation: only the £650,000 total is a producible figure; every per-destination amount is a gap.

Bridging loan timing: "confirm the timing of the bridging-loan repayment" (meeting actions). Doesn't
change the £650,000; review sheet.

## Distractors to ignore

- Market update: "Pendle Global Fund … returned 6.4 per cent … around £775,000 in aggregate".
- Portfolio pack: "Sutton Strategic Fund … around £785,000 of assets under management". Both figures
  are in the same range as the client's own sums (£650k–£850k), so easy to confuse.
- Paraphrased risk warnings in both general docs (as client_03).
- Image header "Holloway Account Statement": interpretation: an image shouldn't be read as covering all
  platforms; absence of Brightwell/Meridian rows is not evidence of anything.

## Must not be actioned

- "help with school fees for their grandchildren and possibly make a charitable donation. Both were
  clear these are aspirations for the future and nothing should be actioned on them in this report."
- "a property in France they had once considered buying; this is not being pursued and has no bearing
  on the advice."
- Offshore bond: "leave it as it is for now and revisit at the next review" — no recommendation to
  change it.
- Emotional context: "a busy and slightly emotional period for them both". No fde sensitivity directive
  for this client (contrast client_03).

## Gaps a person must fill

- CGT on the partial Holloway GIA disposal (and the size of the portion).
- Platform charges for each of Holloway, Brightwell, Meridian (+ new account's platform, unstated):
  "Caroline asked about the total ongoing cost of all this across the three platforms. I said I would
  set out the charges in the report once I had verified each platform's figures".
- Ongoing advice charge rate.
- ISA subscription amounts; SIPP contribution amounts (annual-allowance risk); Holloway GIA addition;
  new joint account amount.
- Caroline's Meridian cash balance (review sheet; out of scope).
- Bridging-loan repayment timing (review sheet).
- Platform of the new joint account: not stated anywhere.
- Initial charge "0.5%" (request): given, P3.

## Per-client instructions

- `fde_notes.md` "## This client": "The client holds accounts across more than one platform. He
  recently sold a business, and the proceeds arrive in more than one form and on more than one date;
  the meeting note has the detail." Processing guidance only; "He" = James (db `client`, meeting
  "James completed the sale of his company").
- Overriding objective (meeting): "to build a tax-efficient base that can replace James's income when
  he steps back from full-time work in about three years. We agreed everything we recommend should be
  weighed against that three-year goal." Interpretation: Recommendations should reference it.

## Other facts for Background

- "long-term growth with a balanced-to-moderate risk appetite. They have no income requirement from the
  portfolio currently".
- "James completed the sale of his company in April."
- Portfolio "spread across three platforms".

## Pipeline risks

- Treating £850,000 or £1,250,000 (with earnout) as available.
- Including M4-CASH-J (£30,000) in the table; including closed/null Meridian cash accounts.
- Listing joint accounts twice; attributing M4-CASH-J to both holders because of the "-J" suffix.
- Inventing ISA/SIPP amounts or quoting allowance figures; computing a "remaining balance".
- Recommending bond changes; mentioning school fees/charity in Recommendations; France property at all.
- Stale £240,000 for the GIA.
- Pendle/Sutton figures leaking in.
- Only one platform's charges marked.
