# client_02_medium: findings

Written independently of SCOPING.md §5–§7. Trust rules applied are SCOPING.md §3.1 (R1–R7) and
policies §4 (P1–P10). "Interpretation:" marks anything that is not a direct reading of a source.

Sources read: `client_data_db.json`, `meeting_notes.docx`, `report_request.docx`, `fde_notes.md`,
`platform_market_update.docx`, `template_spec.md`, `statement_summary.png` (882×366, read in full).

Key dates: `snapshot_date` "2026-04-30"; meeting "held 14 May 2026".
Holders: `client` "David Clarke", `partner` "Susan Clarke". Adviser "Daniel Reeves".

## Accounts (deduplicated)

| Account | Owner | Type | Value | Value date | Source | In scope? | Notes |
|---|---|---|---|---|---|---|---|
| H-ISA-D (Holloway) | David Clarke | Stocks & Shares ISA | £61,000 | 2026-04-30 | db `"value": 61000.0`; image "Holloway ISA (David) … £61,000 … 30 Apr 2026" | Yes: "Holloway ISAs (David and Susan)" | db and image agree. |
| H-ISA-S (Holloway) | Susan Clarke | Stocks & Shares ISA | £58,500 | 2026-04-30 | db `"value": 58500.0`; image "£58,500 … 30 Apr 2026" | Yes | db and image agree. |
| H-GIA-J (Holloway) | Joint → David Clarke & Susan Clarke | General Investment Account | **c. £45,000** (live, "a little over") | 14 May 2026 (meeting) | meeting "I pulled the account up live during the meeting. It was showing a little over £45,000" | Yes: "and the joint GIA" | Superseded: £40,000 at 2026-03-15 (db `"value": 40000.0, "valuation_date": "2026-03-15"`; image "£40,000 … 15 Mar 2026"). R3: meeting (14 May) is later than 15 Mar → c. £45,000 wins, approximate; £40,000 and both dates to review sheet. Being sold in full. |

Duplicate: H-GIA-J appears under both `client.accounts` and `partner.accounts` with identical fields
(`"owner": "Joint"`). Count once. The db never names the joint owners; the names come from the two
holder blocks (interpretation: joint = both holders in the file).

The statement image repeats the db exactly (3 accounts, same values and dates); it adds nothing and
contradicts nothing. All values shown in £.

## Conflicts

- GIA value: £40,000 (15 Mar 2026, db + image) vs "a little over £45,000" (live, 14 May 2026, meeting).
  Resolved by R3 → c. £45,000. Stale by ~2 months at snapshot, ~2 months before meeting.
- No conflict on decisions: meeting "We agreed to disinvest the joint GIA in full"; request "Selling
  existing investments? \| Yes", "Investment amount \| Full value of the joint GIA".
- Risk: meeting "the balanced approach to risk we agreed"; request "Agreed risk profile \| 5
  (balanced)". Agree.

## Money available vs not available

- Available: full GIA sale proceeds. Only an approximate figure exists (c. £45,000, "a little over").
  The request deliberately gives no number ("Full value of the joint GIA"). Interpretation: actual
  proceeds are only known at sale; any £ figure in Recommendations must be approximate.
- Split: "split equally between the two ISAs". Interpretation: c. £22,500 each is a calculation over
  an approximate value (half of "a little over £45,000"); should be presented as approximate if at all.
- **ISA allowance problem (unresolved by sources).** Meeting: "Both ISAs are already part-funded for
  the year; this top-up uses the remaining allowance across the two of them." No source says how much
  is already subscribed. Interpretation: the standard allowance is £20,000 per person (not stated in
  any source), so two ISAs can take at most £40,000 in total, *less* the part-funding; proceeds are
  "a little over £45,000". The agreed plan as literally stated (full proceeds into the ISAs, split
  equally) therefore cannot all be sheltered, and the sources don't say where the excess goes. This
  is a P2/P4 "agreed plan may breach a limit" case. The phrase "uses the remaining allowance" could be
  read as "the ISA top-ups are capped at remaining allowance", leaving the surplus undirected.
  Needs an adviser marker; the sources do not settle it.

## Distractors to ignore

- `platform_market_update.docx`: "Our in-house Kestrel Balanced Portfolio … returned 6.4 per cent …
  stood at around £505,000 in aggregate". "Balanced" in the fund name overlaps the client's risk label.
- Same doc: "Capital is at risk and the value of investments may go down as well as up." (paraphrased
  warning)

## Must not be actioned

- Tangent: "We talked briefly about a holiday they are planning for the autumn; this has no bearing on
  the advice".

## Gaps a person must fill

- CGT on the GIA disposal: meeting "selling down the GIA is a disposal and may have a capital gains
  position to consider; I will set that out in the report". Marker (never estimated).
- Platform charge rate (Holloway) and ongoing advice charge rate: meeting "Susan asked what the ongoing
  charges would look like after the change. I said I would confirm the exact figures in the report".
- ISA subscription amounts per person (remaining allowance unknown) and destination of any surplus —
  see above.
- Exact GIA proceeds (only approximate known). Interpretation: an approximate figure with a footnote
  may be acceptable rather than a marker; not settled by §3/§4.
- Initial charge: "Initial charge \| 0%" (request), stated as given (P3).

## Per-client instructions

- `fde_notes.md` has no "This client" section and, unlike client_01, no "Figures a person finalises"
  or "FCA line" sections. Interpretation: the pipeline can't rely on per-client fde notes to carry
  general rules; those must live in config/code.

## Other facts for Background

- "Both are now retired. They confirmed their objectives and circumstances are unchanged since the last
  review".
- "Neither has any income requirement from the portfolio at the moment."
- Motive: "they decided they would rather simplify".
- Request "Held in single or joint name? \| Joint clients, individual ISAs".

## Pipeline risks

- Listing the GIA twice (duplicate in db) or once per holder.
- Using £40,000 (stale) instead of c. £45,000, or stating "£45,000" as exact.
- Promising the full proceeds into ISAs without flagging the allowance problem.
- Quoting an ISA allowance figure or CGT exempt amount.
- Mentioning the holiday.
- Putting GIA proceeds or top-up amounts in Background.
