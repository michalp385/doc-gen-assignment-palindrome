# Scoping: advice report pipeline

What a correct report is, which source to trust for what, how edge cases are handled, and the
evidence from the baseline. The design (`DESIGN.md`) is built against this document.

Revised after an independent fact-check and review (`notes/scoping_review.md`).

---

## 1. The product

An adviser meets a client and agrees what to do with their money. The pipeline drafts the advice
report from the client's files. A person (adviser or paraplanner) reviews it, fills in the figures
only they can supply, and sends it. The report is a regulated document the adviser signs and must be
able to defend.

So the pipeline has two outputs, for two readers:

- **The report** (`outputs/<client>.md`), for the client: correct, complete, readable, with clearly
  marked gaps where a person must add a figure.
- **The review sheet** (`outputs/<client>.review.md`), for the person finalising it: every gap to
  fill, every conflict between sources and how it was resolved, and every open item from the meeting.

---

## 2. Success criteria

### Two layers of truth

- **Expected facts** decide correctness: hand-derived for the four clients in `data/` (§7), and
  generated alongside each synthetic client (§9). A gate that checks correctness compares the report
  with these, never with the pipeline's own output, because a pipeline that picks the wrong value
  would record the wrong value in its ledger too.
- **The facts ledger** is the pipeline's own record of every fact, its source, date and selecting rule.
  It gives traceability (S5), and on a client with no expected facts (i.e. in production) it is the
  only *correctness* check available: every figure in the report must be a ledger entry marked
  *reportable*. Gates checked against the sources themselves rather than expected facts (G3, G4, G8,
  G10–G13) run the same way on every client.

On a client without expected facts, each fact-dependent gate falls back to a ledger check (the "else"
in the table). Those checks prove the report is consistent with what the pipeline decided, not that
the decision was right. Whether the decisions are right is measured on the clients that do have
expected facts: the four in `data/`, the synthetic clients and the hand-written cases (§9).

### 2.1 Hard gates: any failure means the report cannot go to a client

| # | Gate | How checked |
|---|---|---|
| G1 | Every account in the table is in the report instruction's scope, exists in the account data (or is a new account the instruction creates), and appears once. Joint accounts appear once, owned by both holders by name. | Deterministic: against expected facts; else against the ledger's resolved scope (in scope, deduplicated, existing or new) |
| G2 | Every money amount and percentage in the report (in digits, with "k", or in words) is a reportable figure for this client (§7), or the instruction's initial charge. No figure from a general document and no out-of-scope value ever appears. A superseded value appears only in the table footnote, next to its date (P9). Other numbers are allowed: dates, the tax year, the risk-profile number, durations ("about three years"), counts ("both ISAs") and marker IDs. | Deterministic: against §7's reportable figures; else against ledger entries marked reportable |
| G3 | CGT amounts, CGT rates, platform charge rates and ongoing advice charge rates never appear as figures; each appears as an adviser-review marker. The only charge rate stated is the instruction's initial charge, in a charge context. | Deterministic |
| G4 | The FCA authorisation line and the risk warning appear verbatim, exactly once each, and no paraphrase of either appears elsewhere. | Deterministic (exact match, plus fuzzy match outside the static slots) |
| G5 | The Tax Implications section is present if and only if the advice involves selling or disposing of investments held outside a tax-exempt wrapper (e.g. a GIA). Switches inside an ISA or SIPP don't trigger it; a bond encashment raises a marker instead (P7). | Deterministic: against expected facts; else against the ledger's taxable-disposal flag |
| G6 | Each account shows the value the trust rules select (§3.1 rule 3). Approximate values say so, and the footnote quotes the source's wording. | Deterministic: against expected facts; else against the ledger's selected value per account |
| G7 | Money that is contingent, not yet received, or already committed is never treated as available to invest. | Deterministic (against expected facts; else the ledger's money classes, P5) + judge |
| G8 | Nothing is recommended that the client did not agree to. Aspirations and tangents are never actioned. | Judge |
| G9 | Background contains no transaction amounts: top-ups, proceeds, the size of any new money (e.g. a sale completion payment or an inheritance), tax figures. Values in the account table are not transaction amounts. | Deterministic: against expected facts; else against the ledger's classification of transaction amounts |
| G10 | Internal guidance text never appears in the report. | Deterministic screen (n-gram overlap with internal notes, excluding phrases that also occur in the meeting record or spec) + judge for paraphrase |
| G11 | Each section contains only its own content: no tables, risk warnings, FCA statements or recommendations bleeding into other sections. The account table appears exactly once. | Deterministic |
| G12 | Placeholders produce grammatical text in their template sentence (no "in relation to This report relates to…"). | Deterministic + judge |
| G13 | Risk profile and initial charge match the report instruction verbatim; client names match the account data; new accounts show "To be opened". | Deterministic |
| G14 | Every expected marker is present, and nothing the sources settle carries a marker. Where §7 lists acceptable alternatives for a judgement call, any of them passes. | Deterministic: against expected facts; else every ledger gap classed as a report marker (P2) has a marker, and every marker maps to one |
| G15 | The review sheet contains every review-sheet item in the expected facts (conflicts with both values, sources, dates and the winning rule; superseded values; out-of-scope accounts with no value; open actions marked blocking or not; P4 notes; scope-resolution flags; currency items), and every report marker has a matching row (P1). | Deterministic: against expected facts; else against every review item in the ledger |

### 2.2 Quality: scored, not pass/fail

| # | Criterion | How checked |
|---|---|---|
| Q1 | Each section meets its `template_spec.md` requirements. | Judge, per section, against the spec |
| Q2 | Faithful to the sources: no claim the sources don't support. | Judge, claim by claim against the sources |
| Q3 | Per-client instructions are respected (e.g. sensitivity about a bereavement) without being quoted. | Judge |
| Q4 | Clear, concise, plain English; the client's names used correctly; British spelling. | Judge |
| Q5 | Markers are specific and actionable: they say exactly what is missing ("ongoing platform charge rate, Holloway"), not "TBC". | Judge |
| Q6 | Calibrated flagging: everything genuinely unknown is flagged, and nothing the sources settle is flagged. | Deterministic where expected facts exist (G14); judge only on clients without them |

### 2.3 System criteria

| # | Criterion |
|---|---|
| S1 | Generalises: passes the gates on clients it has never seen (synthetic and hand-written cases, §9). No client-specific values in `src/` or `config/` (enforced by `check_repo.py`). |
| S2 | Runs end to end from a clean checkout. |
| S3 | Cost and latency per report are measured and reported, per stage. |
| S4 | Reproducible: temperature 0 where supported; LLM calls cached on a key covering the model, prompt version, config and inputs, so a re-run on unchanged inputs costs nothing. |
| S5 | Traceable: every figure in the report links to its source, date and the rule that selected it (the facts ledger). |
| S6 | Extensible: a new source type means one new adapter; a new report type means one new config inheriting shared parts. |

---

## 3. Sources: what each is, and what it is trusted for

Relevance is decided by what a document **is**, not by its filename: unseen clients may name files
differently or add new ones. Each file is classified into a role; unknown roles are excluded and
logged, never silently fed to a prompt.

| Role | Current file | Trusted for | Never used for |
|---|---|---|---|
| Account data | `client_data_db.json` | Which accounts exist; owners (from the `owner` field); types, platforms, status; values with their `valuation_date` | Decisions; the scope of this report |
| Meeting record | `meeting_notes.docx` | What was discussed and **decided**; values *viewed during the meeting* (with the meeting date); money received, committed or contingent; open actions | Account existence (it may mention accounts loosely) |
| Report instruction | `report_request.docx` | Accounts in scope; the headline instruction; whether anything is being sold; risk profile; initial charge | Account values |
| Report spec | `template_spec.md` | What each section must contain | Client facts |
| Internal guidance | `fde_notes.md` | Per-client handling (the "This client" section). General processing rules (what a person finalises, the FCA line) appear in only some clients' notes, so they live in config, not here | Report text: never quoted. Its "the client" is not necessarily the account data's `client` role: identify people by name |
| Statement image | `statement_summary.png` | Confirming account values; raising conflicts | Selecting a value (low trust, P10) |
| General document | market updates, portfolio packs | Nothing | Client facts or figures (they contain platform-wide figures and paraphrased risk warnings) |

### 3.1 Trust rules

1. **Existence and ownership**: the account data wins, from the `owner` field only, never inferred
   from an account ID. A new account comes only from the report instruction or meeting record, and is
   shown as "To be opened".
2. **Scope**: the report instruction wins. Accounts outside it don't appear in the table, even if
   they exist and have values.
3. **Values**: the most recent dated figure wins, among the account data and figures the meeting
   record says were viewed during the meeting (e.g. "pulled it up live"). A figure recalled from memory
   or old paperwork, and any statement-image value, never selects a value: it confirms or raises a
   conflict. Approximate language ("around", "a little over") is kept, and the footnote quotes it. The
   superseded value and both dates go to the review sheet.
4. **Decisions and amounts**: the meeting record wins on what was decided; the report instruction
   confirms. If they disagree (e.g. on whether anything is sold), that is a conflict: flag it, don't
   pick silently.
5. **Exact vs approximate**: where the report instruction gives an exact figure and the meeting an
   approximate one for the same amount, use the exact one, provided the approximate figure is
   consistent with it. **Consistent** means the exact figure lies within the approximate figure's
   precision, taken as the unit of its last non-zero digit (£120,000 → £10,000; £45,000 → £1,000),
   with the tolerance capped at 5% of X so that round figures stay tight: "around X" allows X ± the
   smaller of half a unit and 5% of X; "a little over X" allows X up to X + the smaller of one unit and
   5% of X; "a little under X" mirrors it below X. So "around £120,000" is consistent with £124,000 but
   not £126,000, and "around £100,000" allows £95,000 to £105,000, not £50,000 to £150,000. Outside the
   range, it is a conflict under rule 4.
6. **Missing, null or closed**: never given a value. Closed accounts outside scope are ignored; a
   closed account inside scope is a conflict to flag, never silently dropped. Open accounts with no
   value outside scope go to the review sheet only; inside scope, the value cell is a marker and the
   review sheet records it.
7. **General documents**: never a source of client facts, at any trust level.
8. **Scope resolution**: every account named in the report instruction must resolve to at least one
   account in the account data, or to a new account it creates. An unresolved phrase, or one that
   matches more accounts than it names, is flagged, not guessed.
9. **Joint accounts**: deduplicated by `account_id`. If the copies differ in value or date, that is a
   conflict for the review sheet, and rule 3 chooses. A joint account whose co-holder isn't in the
   account data shows a marker in the Owner cell.
10. **Several meeting records**: the latest-dated one governs decisions; earlier ones contribute dated
    values only, under rule 3.

---

## 4. Policy decisions

All settled; revised after the independent review in `notes/scoping_review.md`.

**P1. Marker format**
`[ADVISER TO CONFIRM #n: <exactly what is needed>]`, e.g.
`[ADVISER TO CONFIRM #3: ongoing platform charge rate, Holloway]`. Markers are inserted by code from
the ledger, never typed by the model, so the prefix can't be malformed or invented. Each ID matches a
row in the review sheet, which gives its reason.

**P2. What gets a marker in the report, and what goes to the review sheet**
- Always a marker: CGT amount on any disposal; platform charge rates; the ongoing advice charge rate.
- A marker: amounts the sources leave unspecified but the report needs (e.g. "a portion" of an account
  to be sold); amounts where the plan may breach a limit (P4).
- If the sources conflict on whether anything is sold, the Tax Implications section is included with a
  marker, and the conflict goes to the review sheet: flagging a possible disposal is safer than
  omitting one.
- Review sheet only: open actions that don't change the report text (e.g. confirming an out-of-scope
  cash balance, the timing of a loan repayment). Each is marked **blocking** when the sources make it a
  precondition ("confirm it before anything is finalised"), otherwise informational.

**P3. Initial charge**
Stated as given in the report instruction: it is the adviser's own instruction, not a figure we
produce. Ongoing charges are markers (P2).

**P4. General UK rules (allowances, exempt amounts)**
The report never quotes a rule figure the sources don't give (ISA allowance, pension annual allowance,
CGT annual exempt amount): rules change by tax year, and the baseline quoted a CGT exempt amount years
out of date. Rule figures live in one reference file keyed by tax year, and are used only to detect
possible breaches and raise a marker. The tax year comes from the meeting date (6 April boundary). If
the file has no entry for that year, raise a marker rather than skip detection.
**Trigger:** a marker when the sources show prior use of an allowance (e.g. "already part-funded") or
the planned total exceeds the rule figure. A full-allowance subscription with prior use unknown gets a
review-sheet note, not a report marker, so flagging stays calibrated (Q6).

**P5. Money: received, committed, contingent, expected**
Every money item is classified, with its source quote, as received, committed, contingent, or expected
but not received. Only received minus committed is available, calculated in code. Contingent and
expected money is named in Recommendations as excluded from this plan, with the reason, and never
allocated. If a commitment has no stated amount, "available to invest" becomes a marker: a guessed
amount is never subtracted.

**P6. Aspirations and tangents**
Each item is classified. **Tangents** (holidays, trips, properties not pursued, family news that "has no
bearing") never appear. **Future financial aspirations** the client said not to action (gifting, school
fees, charity) appear at most once, in Background, as not covered by this advice, and never in
Recommendations.

**P7. Tax Implications**
Included per G5. Content: which disposal; that it may create a CGT liability assessed against the
annual exempt amount (the spec's wording); a CGT marker. No gain estimates, rates or exempt-amount
figure. Wrapper switches (inside an ISA or SIPP) create no section. A bond encashment gets a marker
("chargeable-event gain to be assessed") in Recommendations, next to the encashment, not a CGT section.

**P8. Per-client instructions**
The "This client" section of internal guidance becomes a tone or handling directive for the sections it
affects. It is never quoted or paraphrased into the report. People are identified by name, because the
notes' "the client" can be either holder.

**P9. Account table**
Columns `Account | Owner | Type | Value`, one row per in-scope account. Joint owners by name
("David Clarke & Susan Clarke"). A live or approximate value is shown as `c. £45,000`, with a footnote
under the table quoting the source's wording ("a little over £45,000, viewed live on 14 May 2026") and
the last statement value and date. The footnote is the only place a superseded value may appear (G2).
A new account's Type uses the report instruction's wording, falling back to the meeting record's
(e.g. "New joint account"), and its Value is "To be opened"; its platform, if not stated, goes to the review sheet. Built in code from the
facts ledger, not by the model.

**P10. Statement images**
Read with a vision model into the same account-value schema, at **low trust**: an image value can
confirm a value or raise a conflict for the review sheet, but never selects a value. In the current
clients the images only repeat the account data, so the expected effect is none; the point is that an
image that *did* disagree would be caught. Where the account data says GBP, a currency-symbol mismatch
in an image is treated as a likely read error, not a client conflict. Where the account data is not in
GBP, P12 applies. Cost is small: at most one image per client, and client 01 has none.

**P11. Risk profile and request fields**
The risk profile is copied from the report instruction verbatim, number and label ("4 (balanced to
moderate)"); labels are never derived from numbers. A request field that is missing or says "TBC"
becomes a marker, never a default.

**P12. Currency**
Values not in GBP are never converted: the value cell is a marker, and the review sheet records it.

---

## 5. Data patterns

The recurring traps in the data, escalating in difficulty across the clients. Unseen clients will
vary them.

1. **Stale vs live values.** The account being sold has an old statement value; the meeting has a
   fresher, approximate one (02: £40k in March vs ~£45k in May; 03: £30k vs ~£38k; 04: £240k vs
   ~£255k). Accounts not being sold carry the 30 April 2026 snapshot value; only client 04's meeting
   confirms some of them ("in line with the snapshot").
2. **Joint accounts duplicated.** Recorded under each holder (02: one; 03: one; 04: three). A naive
   sum double-counts.
3. **Missing values.** Open accounts with no value (03: Jean's cash; 04: Caroline's cash).
4. **Closed accounts** (04).
5. **Accounts outside scope** that exist and have values (01: the cash account; 04: James's cash).
6. **New accounts** the plan creates that aren't in the account data yet (03, 04).
7. **Money in several forms** (04): received, committed elsewhere, contingent and not received.
8. **Limits the plan may breach** (02: ISA top-ups, where even two full allowances are less than the
   proceeds; 04: SIPP contributions, and full ISA subscriptions with prior use unstated; 01: a
   full-allowance top-up with prior use unstated).
9. **Distractors.** General documents with platform-wide figures, fund names and a paraphrased risk
   warning.
10. **Tangents and aspirations** the client said not to action.
11. **Per-client handling** instructions in internal guidance (03: bereavement).

## 6. Baseline evidence

From the starter pipeline's reports (`outputs/baseline/`). Each maps to a gate.

- **G12, all four clients:** placeholder text breaks its sentence ("in relation to This report relates
  to…"), with double full stops.
- **G11, all four:** sections bleed. Client 02's Tax section contains an introduction, a table, the
  recommendation and the risk warning. The account table appears two or three times per report
  (client 01 twice; clients 02–04 three times).
- **G2 / consistency, client 03:** the Conclusion gives the GIA as about £38,000 while its own table
  says £30,000. Independent slot filling produces contradictions.
- **G3, clients 02, 03, 04:** invented CGT figures (a £5k–7k gain; £3,540; ~£6,600), all using a
  £12,300 annual exempt amount, which is out of date. Client 04's own stated inputs give £6,540, not
  ~£6,600.
- **G3, clients 01, 03, 04:** invented fee rates (0% platform; 0.5% + 0.5%; 0.5% advice).
- **G1, clients 01, 03, 04:** out-of-scope accounts in the table (client 01's cash account; client
  03's unconfirmed cash account; client 04 lists all ten accounts in the data, including James's
  out-of-scope cash, a closed one and one with no value). **Clients 02–04:** joint owners shown as
  "Joint" (one client 04 table uses first names only).
- **G6, client 02:** the recommendation uses the March statement value (£40,000) although the meeting
  shows about £45,000 in May. The Tax section even mentions the £45,000.
- **G7, client 04:** the whole £850,000 treated as available; the bridging loan is not subtracted in
  the recommendation.
- **G8 / P6, client 02:** the holiday appears twice.
- **Also:** G4, client 03: the Tax section paraphrases the FCA line (verbatim-once alone would still
  pass). G9: amounts in Background (01 £20,000; 03 £120,000; 04 £850,000 and £200,000). P4: client 04
  quotes "£20,000 each" for the ISAs. Rule 5: client 03 says "approximately £120,000" instead of the
  exact £120,000. G11: the risk warning twice in 02 and 04; the closing line twice in 01.
- **Correct:** client 01 omits the Tax section.

---

## 7. Expected facts for the four clients in `data/`

Hand-derived from the sources and independently fact-checked (`notes/scoping_review.md`). Seed for the
eval's expected facts. Values are the latest available on the meeting date: the snapshot value unless
the meeting records a later, live-viewed one.

**Reportable figures** is a closed list: G2 fails any other money amount or percentage. Figures marked
*optional* may appear or not. Section notes in parentheses say where a figure is expected; they are
guidance, not rules, except "table footnote only", which G2 enforces. Placement is otherwise judged
(Q1), and G9 keeps transaction amounts out of Background. So the Tax section may say "your GIA, worth
about £45,000". Where an expected fact is a judgement call, it lists the **acceptable
alternatives**, and the eval accepts any of them.

### client_01_clean (meeting 12 May 2026)
- **Table:** Holloway Stocks & Shares ISA, Margaret Hughes, £52,000.
- **Not in table:** Holloway cash account (£25,000): the source of funds, outside scope.
- **Advice:** move £20,000 from the cash account into the ISA. Nothing sold.
- **Tax section:** no. **Initial charge:** 0%. **Risk profile:** 4, moderate.
- **Reportable figures:** £52,000 (table); £20,000 (Recommendations); 0% (initial charge). Not the cash
  account's £25,000: it is out of scope (the source of funds is named, not valued).
- **Markers:** platform charge rate; ongoing advice charge rate.
- **Review sheet:** the £20,000 top-up is a full year's ISA allowance and prior use this tax year is
  unstated: a note, not a marker (P4).
- **Must not appear:** the market update's platform figure or fund name; any gifting action; a Tax
  Implications section or any CGT figure (a statement that nothing is sold is fine).

### client_02_medium (meeting 14 May 2026)
- **Table:** David's ISA £61,000; Susan's ISA £58,500; joint GIA (David & Susan) c. £45,000
  (live 14 May; statement £40,000 at 15 March).
- **Advice (as agreed):** sell the joint GIA in full; split the proceeds equally into both ISAs. The
  report must not state that all the proceeds go into the ISAs: see the ISA marker.
- **Tax section:** yes. **Initial charge:** 0%. **Risk profile:** 5, balanced.
- **Reportable figures:** £61,000; £58,500; c. £45,000 (table and Recommendations); £40,000 (table
  footnote only); 0%. Not a per-ISA amount such as £22,500 (see the ISA marker).
- **Markers:** CGT; platform charge rate; advice charge rate; **ISA top-up amounts**: half the
  proceeds is about £22,500 per ISA, which exceeds one annual allowance, so even two unused allowances
  couldn't take it all, and both ISAs are already part-funded this year. Detected with the P4
  reference file; the allowance figure is not stated in the report. The adviser must confirm how much
  each ISA can take and where any excess goes.
- **Review sheet:** GIA statement value £40,000 (15 March) superseded by the live c. £45,000 (14 May);
  where any proceeds above the ISA allowances go.
- **Must not appear:** the holiday; the market update's figure or fund name; any CGT figure.

### client_03_hard (meeting 16 May 2026)
- **Table:** Robert's ISA £70,000; Jean's ISA £66,000; joint GIA (Robert & Jean) c. £38,000
  (live 16 May; statement £30,000 at 10 March); new joint investment account, to be opened.
- **Not in table:** Jean's cash account (no value; she isn't sure it is active): review sheet.
- **Money:** inheritance £120,000 (exact, from the report instruction) plus GIA proceeds c. £38,000.
- **Advice:** sell the joint GIA; with the inheritance, fund both ISAs for the new tax year; the balance
  into the new joint account.
- **Tax section:** yes. **Initial charge:** 0.5%. **Risk profile:** 4, moderate.
- **Reportable figures:** £70,000; £66,000; c. £38,000; £30,000 (table footnote only); £120,000
  (Recommendations); 0.5%. *Optional:* the combined total, c. £158,000 (a calculation over the two).
- **Markers:** CGT; platform charge rate; advice charge rate; charges on the new joint account; ISA
  top-up amounts and the resulting balance for the new account. The balance marker is required. For
  the ISA amounts: required, no ISA figure in the report; acceptable alternatives: (a) an ISA-amount
  marker (preferred: the meeting says "fund both ISAs", not "use both allowances", so the amount is
  unspecified, P2); (b) wording that both ISAs are funded, with a review-sheet note.
- **Handling:** the inheritance follows a bereavement: reference it with sensitivity.
- **Review sheet:** GIA statement value £30,000 (10 March) superseded by c. £38,000 (16 May); Jean's
  cash account, **blocking** ("confirm it before anything is finalised"); the new joint account's type
  and platform.
- **Must not appear:** the grandchildren or the trip (tangents: not at all, P6); the platform figures
  or fund names from either general document; any CGT figure.

### client_04_stretch (meeting 20 May 2026)
- **Table:** James's ISA £85,000; Caroline's ISA £82,000; James's SIPP £610,000; Caroline's SIPP
  £430,000; Holloway joint GIA c. £255,000 (live 20 May; statement £240,000 at 28 February);
  Brightwell joint GIA £95,000; Meridian joint offshore bond £180,000; new joint investment account,
  to be opened.
- **Not in table:** James's Meridian cash (£30,000, outside scope); Caroline's Meridian cash (no
  value: review sheet); the closed Meridian account (ignored).
- **Money:** completion payment £850,000 received, less £200,000 committed to a bridging loan
  = **£650,000 available** (calculated in code). Earnout of up to £400,000: contingent, not received,
  **excluded**.
- **Advice:** use both ISA allowances; SIPP contributions for both, sized within allowances; add to
  the Holloway joint GIA; sell and rebalance a portion of the Holloway joint GIA; the balance into the
  new joint account; leave the offshore bond as it is. All weighed against replacing James's income in
  about three years.
- **Circumstance, not money:** "James may do some consultancy work but nothing is settled." Not a money
  item under P5 (no amount, nothing agreed) and not a tangent under P6 (it bears on the income
  objective). It may appear in Background as unsettled; never actioned or quantified.
- **Tax section:** yes (the partial GIA sale). **Initial charge:** 0.5%. **Risk profile:** 4,
  balanced to moderate.
- **Reportable figures:** £85,000; £82,000; £610,000; £430,000; c. £255,000; £240,000 (table footnote
  only); £95,000; £180,000; 0.5%. In Recommendations: £850,000 (the completion payment), £200,000 (the
  committed loan repayment), £650,000 (available), and "up to £400,000" (the earnout, named as
  excluded, P5).
- **Markers:** CGT; platform charge rates (three platforms, plus the new account's if on another);
  advice charge rate; SIPP contribution amounts; the amount added to the Holloway GIA; the portion
  sold; the balance for the new account.
- **ISA subscriptions:** "use both ISA allowances", prior use unstated. Required: no ISA figure in the
  report. Acceptable alternatives: (a) wording that both allowances are used, with a review-sheet note
  that prior use is unconfirmed (preferred, P4); (b) an ISA-amount marker.
- **Review sheet:** Caroline's cash balance; bridging-loan repayment timing; Holloway GIA statement
  value £240,000 (28 February) superseded by c. £255,000 (20 May); whether the partial-sale proceeds
  stay in the GIA or join the £650,000; the new account's type and platform.
- **Must not appear:** the earnout as invested; £850,000 as the amount to invest; school fees or
  charity in Recommendations (at most once in Background, as not covered, P6); the French property at
  all; James's Meridian cash account; the closed account; the platform figures or fund names from
  either general document; any CGT figure.

---

## 8. Explainability

The report is a document an adviser must be able to defend, so every output has to be explainable to
two audiences.

**To the adviser and compliance reviewer** (via the review sheet and the facts ledger):
- **Every figure:** its source, the date of that figure, and the rule that selected it (e.g. "live
  meeting value, 14 May, supersedes statement value of 15 March: trust rule 3").
- **Every account:** why it is in the table or left out (in scope, out of scope, closed, no value).
- **Every section decision:** why a conditional section is included or omitted, citing the evidence
  (e.g. "Tax Implications included: the report instruction says investments are being sold, and the
  meeting records a disposal").
- **Every marker:** what is missing and why the pipeline could not supply it.
- **Every conflict:** both values, both sources, and which won.

**To engineers** (via run traces and eval results):
- **Per stage:** inputs, outputs, model, prompt version, tokens, cost and latency, recorded for every run.
- **Per eval failure:** the gate, the client, and the offending text, so a failure points at a stage.
- **Per change:** eval results tied to the commit, so any difference in output can be traced to the
  change that caused it.

This is explainability of the system's decisions, not of model internals: the models are API models.
The design makes the model's role narrow (extracting and writing), and puts every decision that has a
right answer (selection, reconciliation, arithmetic, inclusion) in code, where it can be explained
exactly.

## 9. Evidence the system produces

Claims about correctness are only as good as the evidence for them. The system produces its own:

1. **Unseen clients with known answers.** A generator creates synthetic clients by varying the data
   patterns in section 5: new names, values and account mixes, extra joint accounts, stale dates,
   missing values, new distractor figures, contingent and committed money, limit breaches. Because the
   generator builds them, it knows the right answers. The pipeline is scored on clients it has never
   seen, not only on the four it was developed against. Because the generator encodes the same rules
   the pipeline implements, it can catch a wrong implementation but not a wrong rule. So a small set of
   hand-written cases with hand-derived answers covers the patterns the rules are least sure of: an
   image dated later than the account data, a meeting figure recalled rather than viewed, joint-account
   copies that disagree, an in-scope account that is closed or has no value.
2. **An eval that is itself tested.** Correct reports are deliberately broken, one fault at a time
   (a joint account double-counted, an invented CGT figure, a missing risk warning, a distractor
   figure, a stale value, an actioned aspiration), and the eval must catch every one. Each gate has at
   least one such test.
3. **Results tied to commits.** Every eval run writes a results file with the commit, prompt version,
   models, per-gate results, tokens and cost. The progression from the baseline to the final system is
   generated from these files, never assembled by hand.
4. **The facts ledger and the review sheet** (sections 1 and 8): every figure traceable, every gap
   visible.

## 10. Open questions for the design

- Pipeline stages: classification → extraction → reconciliation (code) → planning of section content →
  section writing → validation → assembly. Which stages need a model, and which model?
- Structured-output schemas for extraction and for each section.
- Where the facts ledger lives, and how sections receive only their own facts.
- Caching, retries and cost accounting in one LLM client wrapper.
- The eval harness: deterministic gates, the judge rubric, expected-facts fixtures, results files.
- The synthetic client generator: which patterns it varies, and how it derives expected facts.
- How `template_config.json` generalises to several report types without duplication.
- Validation after writing: re-check every figure against the ledger; regenerate or flag on failure.