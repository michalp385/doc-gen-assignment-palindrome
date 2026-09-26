# client_01_clean: findings

Written independently of SCOPING.md §5–§7. Trust rules applied are SCOPING.md §3.1 (cited as R1–R7)
and policies §4 (P1–P10). "Interpretation:" marks anything that is not a direct reading of a source.

Sources read: `client_data_db.json`, `meeting_notes.docx`, `report_request.docx`, `fde_notes.md`,
`platform_market_update.docx`, `template_spec.md`. No statement image in this folder.

Key dates: `snapshot_date` "2026-04-30" (db); meeting "held 12 May 2026" (meeting_notes).
Client: "Margaret Hughes" (db `holders.client.name`); single holder, no partner block.
Adviser: "Daniel Reeves" (report_request).

## Accounts (deduplicated)

| Account | Owner | Type | Value | Value date | Source | In scope? | Notes |
|---|---|---|---|---|---|---|---|
| H-ISA-01 (Holloway) | Margaret Hughes | Stocks & Shares ISA | £52,000 | 2026-04-30 | db: `"value": 52000.0`, `"valuation_date": "2026-04-30"`, `"status": "open"` | Yes: request "Accounts covered \| Holloway Stocks & Shares ISA" | Only in-scope account. Receives the top-up. No later-dated figure in any source, so R3 leaves £52,000 (exact, 30 Apr 2026). |
| H-CASH-01 (Holloway) | Margaret Hughes | Cash Account | £25,000 | 2026-04-30 | db: `"value": 25000.0`, `"valuation_date": "2026-04-30"`, `"status": "open"` | No: not named in "Accounts covered" | Is the *source of funds*: request "Source of funds \| Cash held on deposit in the Holloway cash account"; meeting "she has cash sitting on deposit in her Holloway cash account". R2 keeps it out of the table. |

No duplicates, no joint accounts, no null or closed accounts, no new accounts.

## Conflicts

None between sources on values, ownership or decisions:
- Top-up amount: meeting "We agreed she would move £20,000 from the cash account into the Stocks &
  Shares ISA"; request "Investment amount \| GBP 20,000". Agree, both exact.
- Disposal: meeting "No investments are being sold … so there is no disposal involved"; request
  "Selling existing investments? \| No". Agree → no Tax Implications section (G5, spec "If nothing is
  being sold, omit the section entirely").
- Risk: meeting "comfortable with the moderate approach to risk"; request "Agreed risk profile \| 4
  (moderate)". Agree.

Ambiguity (not a conflict): the source-of-funds account is out of scope. R2 settles the table (ISA only),
but no rule says whether the Recommendations may name the cash account and its balance. Interpretation:
naming the cash account as the source ("from your Holloway cash account") is a fact from the request
and meeting; quoting its £25,000 balance or a post-transfer £5,000 is not needed and would be a figure
about an out-of-scope account. Not settled by §3.

## Money available vs not available

- Available and agreed: £20,000 exact (meeting + request, above).
- Held but not being invested: remaining cash-account balance. Interpretation: £25,000 − £20,000 =
  £5,000 stays in cash; no source states this, and the report doesn't need it.
- No contingent or committed money.

## Distractors to ignore

- `platform_market_update.docx`: "Our in-house Aldgate Growth Portfolio … returned 6.4 per cent over
  the quarter and stood at around £312,000 in aggregate at quarter-end. This is an illustrative
  platform figure and is not a holding in any individual client's portfolio." (R7)
- Same document: "Capital is at risk and the value of investments may go down as well as up." A
  paraphrase of a risk warning; must not replace the spec's verbatim warning.
- Meeting: "We spent a little time talking through the market commentary I had sent ahead of the
  meeting; Margaret had read it and had no concerns". Interpretation: this is the market update; its
  mention in the meeting doesn't make its figures client facts.

## Must not be actioned

- Gifting: "She mentioned she may want to discuss gifting to her grandchildren at some point in the
  future, but was clear that is not for today and nothing should be actioned on it now." (meeting)

## Gaps a person must fill

- Platform charge rate (Holloway). No source gives it. fde_notes: "the platform and adviser fee rates,
  are confirmed or inserted by a person".
- Ongoing advice charge rate. Same.
  - Meeting timing detail: "confirm the ongoing charges with her once the report is issued". Taken
    literally the adviser confirms charges *after* issue; interpretation: the draft still needs markers
    because the spec's Fees section requires them.
- CGT: not applicable (no disposal).
- Initial charge: given, "Initial charge \| 0%" (request); P3 states it as given.
- ISA allowance headroom. The meeting says she wants "to use this year's ISA allowance"; no source says
  whether she has already subscribed in the 2026/27 tax year (meeting is 12 May 2026, after 6 April).
  Interpretation: £20,000 equals the full standard allowance, so any earlier subscription this tax year
  would breach it. Under P4 this is a *detection* case; whether it raises a marker depends on the
  reference-file rule and on whether "no evidence of prior subscription" counts as a trigger. Not
  settled by §3/§4.

## Per-client instructions

- `fde_notes.md` has no "This client" section. It is the only client whose notes carry "## Figures a
  person finalises" and "## The FCA line"; those are general processing rules (P8: never quoted).
- fde_notes: "I have already put it into the template config as static text". Checked:
  `config/template_config.json` line 9 contains "This firm is authorised and regulated by the Financial
  Conduct Authority."

## Other facts for Background

- "Margaret is retired and confirmed there have been no changes to her circumstances or objectives
  since last year's review."
- "Margaret has no income requirement from the portfolio at present and does not expect that to change
  in the near term."
- Objectives are not stated beyond "use this year's ISA allowance" and no income need. Interpretation:
  Background must not invent a growth objective.

## Pipeline risks

- Quoting the £312,000 / 6.4% platform figures.
- Putting the cash account (and £25,000) in the table because it is in the db and named as source.
- Including Tax Implications because the word "disposal" appears in the meeting ("no disposal involved").
- Putting "£20,000" in Background (spec: transaction amounts belong in Recommendations).
- Quoting an ISA allowance figure (P4) or estimating fees.
- Mentioning gifting in Recommendations.
