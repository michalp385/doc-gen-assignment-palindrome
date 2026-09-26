# Independent review of SCOPING.md

Scope: every factual claim in SCOPING.md §5–§7, plus factual claims in §2–§4 and §8–§10, checked against
`data/<client>/` and `outputs/baseline/`. Per-client evidence is in `notes/client_0*.md`, written
before §5–§7 were read. Rule references: R1–R7 = §3.1 trust rules; P1–P10 = §4 policies; G/Q/S = §2.

Method: text sources via `scripts/dump_client.py`; all three statement images read in full (882×366);
`.docx` internals checked for headers, footers, comments, tracked changes and hidden text (there are
none; each `report_request.docx` holds one table, which the loader reads); `fde_notes.md` and
`template_spec.md` diffed across clients (spec identical; fde notes differ, see B8).

Verdicts: **correct**; **incorrect** (a source contradicts it); **unsupported** (no source in the repo
backs it); **ambiguous** (true on one reading, false or unclear on another, or inconsistent with
another part of SCOPING.md).

**Totals: 118 claims checked. 4 incorrect, 2 unsupported, 8 ambiguous, 104 correct.**

---

## A. Fact check

### A.1 Mismatches (incorrect / unsupported / ambiguous)

| # | Claim | Where | What the source says | Verdict |
|---|---|---|---|---|
| 1 | "The account table appears two to four times per report." | §6 G11 | `outputs/baseline/`: client_01 has 2 tables (lines 21, 49); clients 02, 03 and 04 have 3 each (02: lines 19, 45, 76; 03: 22, 53, 83; 04: 21, 56, 95). No report has 4. | **incorrect** (two or three) |
| 2 | "**G1, all four:** out-of-scope accounts in the table" | §6 | client_02 baseline table (lines 21–23) lists only H-ISA-D, H-ISA-S, H-GIA-J, all in scope ("Accounts covered \| Holloway ISAs (David and Susan) and the joint GIA"). Client 02 fails G1 only on the "Joint" owner label. | **incorrect** for client 02 |
| 3 | "Values as at the meeting date." | §7 intro | Most in-scope values are the snapshot values: db `"valuation_date": "2026-04-30"` (e.g. client_04 B4-SIPP-J). Only the GIAs have meeting-dated values. | **incorrect** as worded. Values are the latest available on the meeting date |
| 4 | "Cost is small (one image per client)." | P10 | `data/client_01_clean/` has no image (file list: client_data_db.json, fde_notes.md, meeting_notes.docx, platform_market_update.docx, report_request.docx, template_spec.md). | **incorrect**: at most one; client 01 has none |
| 5 | "A separate automated read of these same images reported "€61,000" and "$240,000"" | P10 | No file in the repo records this read (grep for "€" and "$240" finds only SCOPING.md:158). The values match client_02 H-ISA-D (£61,000) and client_04 H4-GIA-HJ (£240,000), so "these same images" means two images. | **unsupported** (plausible, but not traceable) |
| 6 | "half the proceeds is about £22,500 per ISA, above the annual ISA allowance" | §7 client_02 | Arithmetic is right: meeting "a little over £45,000" ÷ 2. But no source gives the allowance; the £20,000 figure is external UK rule knowledge. The meeting says only "this top-up uses the remaining allowance". This expected fact can only be derived if P4's reference file (a [confirm] item) exists. | **unsupported by the sources** (correct under current UK rules). A settled fact rests on a pending decision |
| 7 | "Accounts not being sold are current." | §5.1 | They carry the 30 Apr 2026 snapshot value. Only client_04's meeting confirms any of them: "On the Brightwell platform … These were all in line with the snapshot". Clients 02 and 03 ISAs are never re-checked. | **ambiguous**. True for "latest available", not for "confirmed at meeting" |
| 8 | "**Limits the plan may breach** (02: ISA top-ups; 04: SIPP contributions)." | §5.8 | client_04 meeting also: "use both ISA allowances for the new tax year" (full-allowance subscription, prior use not stated). client_01: "move £20,000 … into the Stocks & Shares ISA", which is a full allowance on 12 May 2026, with no statement on prior subscriptions this tax year. | **ambiguous**. The list may be incomplete; see B4 |
| 9 | Client 04 markers list omits ISA subscription amounts | §7 client_04 "Markers" | meeting "use both ISA allowances for the new tax year": no figure in any source. §7 client_03 *does* list "ISA top-up amounts" as a marker for the analogous "fund both Robert's and Jean's ISAs for the new tax year". | **ambiguous**: inconsistent between clients 03 and 04 |
| 10 | "grandchildren or the trip as actions" / "school fees, charity or the French property as actions" | §7 client_03, client_04 "Must not appear" | P6: "Personal tangents (holidays, trips, properties not pursued) never appear." client_03 meeting: "a trip they have planned later in the year; nothing there changes the advice"; client_04: "a property in France … not being pursued". | **ambiguous**: §7 is weaker than P6 ("as actions" vs "never appear") |
| 11 | "Must not appear: … CGT content" | §7 client_01 | meeting "there is no disposal involved". Unclear whether a sentence such as "no investments are sold, so no CGT arises" is forbidden "CGT content". The baseline has exactly that ("there will be no capital gains tax implications", client_01 baseline line 30). | **ambiguous**: not checkable as written |
| 12 | Internal guidance trusted for "what a person finalises" | §3 table | Only `data/client_01_clean/fde_notes.md` has "## Figures a person finalises" and "## The FCA line"; clients 02–04 notes lack both (diff). | **ambiguous**. True for one client only; general rules can't rely on per-client notes |
| 13 | "**Advice:** sell the joint GIA in full; split the proceeds equally into both ISAs." | §7 client_02 | Matches meeting "disinvest the joint GIA in full … split equally between the two ISAs". But the same §7 entry says this is above the allowance, so the report cannot state it as the recommendation unqualified. | **ambiguous**: correct record of the agreement; wrong if read as the expected report text |
| 14 | "Joint owners shown as "Joint"." | §6 | Baseline 02/03 and 04 tables 1 and 3 use "Joint". The client_04 Tax-section table (lines 60, 63, 64) uses "James & Caroline" (first names, not "Joint"). | **ambiguous**. Mostly correct; one table differs, and it also fails G1 |

### A.2 Correct claims

| # | Claim | Where | What the source says | Verdict |
|---|---|---|---|---|
| 15 | 02: £40k in March vs ~£45k in May | §5.1 | db H-GIA-J `40000.0`, `"2026-03-15"`; meeting "a little over £45,000", "held 14 May 2026" | correct |
| 16 | 03: £30k vs ~£38k | §5.1 | db H-GIA-JF `30000.0`, `"2026-03-10"`; meeting "around £38,000" | correct |
| 17 | 04: £240k vs ~£255k | §5.1 | db H4-GIA-HJ `240000.0`, `"2026-02-28"`; meeting "around £255,000" | correct |
| 18 | The account being sold has an old statement value | §5.1 | 02/03 GIA sold in full; 04 GIA partially; each dated before 30 Apr snapshot | correct |
| 19 | Joint duplicated: 02 one | §5.2 | H-GIA-J under `client` and `partner` | correct |
| 20 | 03 one | §5.2 | H-GIA-JF under both | correct |
| 21 | 04 three | §5.2 | H4-GIA-HJ, B4-GIA-J, M4-BOND-J under both | correct |
| 22 | Missing values: 03 Jean's cash | §5.3 | H-CASH-JE `"value": null` | correct |
| 23 | 04 Caroline's cash | §5.3 | M4-CASH-C `"value": null` | correct |
| 24 | Closed accounts (04) | §5.4 | M4-OLD-C `"status": "closed"` | correct |
| 25 | Out of scope with values: 01 cash | §5.5 | H-CASH-01 `25000.0`; not in "Accounts covered" | correct |
| 26 | 04 James's cash | §5.5 | M4-CASH-J `30000.0`, owner James; not in request | correct |
| 27 | New accounts (03, 04) | §5.6 | 03 request "a new joint account"; 04 request "a new joint account for the proceeds" | correct |
| 28 | Money in several forms (04) | §5.7 | meeting: completion £850,000 received; £200,000 committed; earnout "up to £400,000" contingent | correct |
| 29 | 02 ISA top-ups may breach | §5.8 | meeting "Both ISAs are already part-funded"; proceeds "a little over £45,000" | correct |
| 30 | 04 SIPP contributions may breach | §5.8 | meeting "worried about over-contributing … would not commit to a figure that breached the limits" | correct |
| 31 | Distractors: platform-wide figures, fund names, paraphrased warning | §5.9 | all four market updates ("around £312,000/£505,000/£515,000/£775,000"); packs 03/04 (£525,000, £785,000); "may go down as well as up"; "may fall as well as recover" | correct |
| 32 | Tangents and aspirations the client said not to action | §5.10 | 01 gifting; 02 holiday; 03 grandchildren/trip; 04 school fees, charity, France | correct |
| 33 | Per-client handling (03: bereavement) | §5.11 | 03 fde "Reference its origin with appropriate sensitivity" | correct |
| 34 | G12 all four: "in relation to This report relates to…" | §6 | baseline line 5 in all four ("in relation to This report relates to/covers…") | correct |
| 35 | double full stops | §6 | 01 "profile..", 02 "platform..", 03 "Account..", 04 "plans.." (line 5 each) | correct |
| 36 | G11 all four: sections bleed | §6 | e.g. 01 Conclusion repeats table and recommendation (lines 43–58); 03 Tax restates FCA and table | correct |
| 37 | Client 02 Tax section has intro, table, recommendation and risk warning | §6 | baseline 02 lines 39, 45–49, 51, 59 | correct |
| 38 | Client 03 Conclusion ~£38,000 vs own table £30,000 | §6 | baseline 03 line 81 "approximate value of £38,000"; line 87 "£30,000" | correct |
| 39 | Invented CGT: 02 "£5k–7k gain" | §6 | baseline 02 line 53 "£5,000 - £7,000" | correct |
| 40 | 03 "£3,540" | §6 | baseline 03 line 64 | correct |
| 41 | 04 "~£6,600" | §6 | baseline 04 line 71 "around £6,600" | correct |
| 42 | All use £12,300 exempt amount | §6 | 02 line 53, 03 line 62, 04 line 71 | correct |
| 43 | £12,300 is out of date | §6 / P4 | External: £12,300 applied 2020/21–2022/23; £3,000 from 2024/25 | correct (external knowledge) |
| 44 | Client 04's inputs give £6,540, not ~£6,600 | §6 | (45,000 − 12,300) × 20% = £6,540 | correct |
| 45 | Invented fee: 01 0% platform | §6 | baseline 01 line 36 "0% for the Holloway platform" | correct |
| 46 | 03 0.5% + 0.5% | §6 | baseline 03 lines 72–73 | correct |
| 47 | 04 0.5% advice | §6 | baseline 04 line 85 | correct |
| 48 | 01's cash account in table | §6 | baseline 01 lines 24, 52 | correct |
| 49 | 03's unconfirmed cash account in table | §6 | baseline 03 lines 27, 58 | correct |
| 50 | Client 04: all ten accounts, incl. closed and no-value | §6 | baseline 04 lines 23–32 (10 rows incl. M4-OLD-C, M4-CASH-C) | correct (wording ambiguous: only 3 of the 10 are out of scope) |
| 51 | G6 client 02: recommendation uses £40,000 | §6 | baseline 02 line 29 "approximate value of £40,000" | correct |
| 52 | Tax section mentions £45,000 | §6 | baseline 02 line 53 | correct |
| 53 | G7 client 04: £850,000 treated as available, loan not subtracted in recommendation | §6 | baseline 04 line 38; the loan is mentioned only in Background (11) and Tax (54) | correct |
| 54 | Client 02: holiday appears twice | §6 | baseline 02 lines 41, 74 | correct |
| 55 | Client 01 omits the Tax section | §6 | baseline 01 headings: no Tax Implications | correct |
| 56 | 01 meeting 12 May 2026 | §7 | "held 12 May 2026" | correct |
| 57 | 01 table: ISA, Margaret Hughes, £52,000 | §7 | db H-ISA-01 `52000.0` | correct |
| 58 | 01 not in table: cash £25,000, source of funds, outside scope | §7 | db `25000.0`; request "Source of funds \| Cash held on deposit in the Holloway cash account" | correct |
| 59 | 01 advice: move £20,000 into ISA; nothing sold | §7 | meeting "move £20,000"; request "Selling existing investments? \| No" | correct |
| 60 | 01 Tax no | §7 | "no disposal involved" | correct |
| 61 | 01 initial 0% | §7 | request "Initial charge \| 0%" | correct |
| 62 | 01 risk 4, moderate | §7 | request "4 (moderate)" | correct |
| 63 | 01 markers: platform; advice charge | §7 | no rate in any source; meeting "confirm the ongoing charges" | correct |
| 64 | 01 must not appear: market figure/fund name; gifting action | §7 | "Aldgate Growth Portfolio … £312,000"; "nothing should be actioned on it now" | correct |
| 65 | 02 meeting 14 May 2026 | §7 | "held 14 May 2026" | correct |
| 66 | 02 David's ISA £61,000 | §7 | db `61000.0`; image "£61,000" | correct |
| 67 | 02 Susan's ISA £58,500 | §7 | db `58500.0`; image "£58,500" | correct |
| 68 | 02 joint GIA (David & Susan) c. £45,000 live 14 May; £40,000 at 15 March | §7 | meeting "pulled the account up live … a little over £45,000"; db/image "15 Mar 2026" | correct |
| 69 | 02 Tax yes | §7 | request "Selling existing investments? \| Yes" | correct |
| 70 | 02 initial 0% | §7 | request "0%" | correct |
| 71 | 02 risk 5, balanced | §7 | request "5 (balanced)" | correct |
| 72 | 02 markers: CGT; platform; advice | §7 | meeting "may have a capital gains position"; "confirm the exact figures in the report" | correct |
| 73 | 02 both ISAs already part-funded | §7 | meeting "Both ISAs are already part-funded for the year" | correct |
| 74 | 02 must not appear: holiday; market figure; CGT figure | §7 | "holiday … no bearing"; "Kestrel Balanced Portfolio … £505,000" | correct |
| 75 | 03 meeting 16 May 2026 | §7 | "held 16 May 2026" | correct |
| 76 | 03 Robert's ISA £70,000 | §7 | db/image | correct |
| 77 | 03 Jean's ISA £66,000 | §7 | db/image | correct |
| 78 | 03 joint GIA c. £38,000 live 16 May; £30,000 at 10 March | §7 | meeting "Pulling it up during the meeting … around £38,000"; db/image "10 Mar 2026" | correct |
| 79 | 03 new joint investment account, to be opened | §7 | meeting "open a new jointly-held investment account" | correct |
| 80 | 03 not in table: Jean's cash (no value; not sure active): review sheet | §7 | db null; meeting "not even sure it was still active" | correct |
| 81 | 03 inheritance £120,000 exact from request | §7 | request "GBP 120,000 inheritance"; meeting "around £120,000" (R5) | correct |
| 82 | 03 plus GIA proceeds c. £38,000 | §7 | request "plus the full joint GIA value" | correct |
| 83 | 03 advice: sell GIA; fund both ISAs; balance to new account | §7 | meeting "disinvest the joint GIA, and together with the inheritance, fund both … ISAs … and open a new jointly-held investment account for the balance" | correct |
| 84 | 03 Tax yes | §7 | "Selling down the GIA is a disposal" | correct |
| 85 | 03 initial 0.5% | §7 | request "0.5%" | correct |
| 86 | 03 risk 4, moderate | §7 | request "4 (moderate)" | correct |
| 87 | 03 markers: CGT; platform; advice; new-account charges; ISA amounts and balance | §7 | meeting "charges on the new joint account … once verified"; no ISA amounts anywhere | correct |
| 88 | 03 inheritance follows a bereavement: sensitivity | §7 | fde "## This client … appropriate sensitivity" | correct |
| 89 | 03 must not appear: platform figures/fund names from either general doc; CGT figure | §7 | "Marlow Multi-Asset Fund … £515,000"; "Tavener Income Fund … £525,000" | correct |
| 90 | 04 meeting 20 May 2026 | §7 | "held 20 May 2026" | correct |
| 91 | 04 James ISA £85,000 | §7 | db/image | correct |
| 92 | 04 Caroline ISA £82,000 | §7 | db/image | correct |
| 93 | 04 James SIPP £610,000 | §7 | db B4-SIPP-J | correct |
| 94 | 04 Caroline SIPP £430,000 | §7 | db B4-SIPP-C | correct |
| 95 | 04 Holloway GIA c. £255,000 live 20 May; £240,000 at 28 Feb | §7 | meeting "pulling it up live … around £255,000"; db/image "28 Feb 2026" | correct |
| 96 | 04 Brightwell joint GIA £95,000 | §7 | db B4-GIA-J `"owner": "Joint"` | correct |
| 97 | 04 Meridian joint bond £180,000 | §7 | db M4-BOND-J | correct |
| 98 | 04 new joint account to be opened | §7 | request/meeting | correct |
| 99 | 04 not in table: James's Meridian cash £30,000 out of scope | §7 | db M4-CASH-J; absent from request | correct |
| 100 | 04 not in table: Caroline's Meridian cash, no value, review sheet | §7 | db null; meeting "she will confirm it" | correct |
| 101 | 04 not in table: closed account ignored | §7 | db closed; meeting "can be disregarded" | correct |
| 102 | 04 £850,000 − £200,000 = £650,000 available | §7 | meeting figures | correct |
| 103 | 04 earnout up to £400,000 contingent, excluded | §7 | meeting "None of the earnout has been received yet … not guaranteed" | correct |
| 104 | 04 advice items (ISAs, SIPPs within allowances, add to GIA, sell/rebalance portion, balance to new account, bond unchanged, three-year goal) | §7 | meeting paragraphs "On the plan …", "As part of tidying up …", "leave it as it is", "weighed against that three-year goal" | correct |
| 105 | 04 Tax yes (partial GIA sale) | §7 | request "Yes (partial rebalance of the Holloway joint GIA)" | correct |
| 106 | 04 initial 0.5% | §7 | request "0.5%" | correct |
| 107 | 04 risk 4, balanced to moderate | §7 | request "4 (balanced to moderate)" | correct |
| 108 | 04 markers: CGT; three platforms' charges; advice; SIPP amounts; GIA addition; portion sold; balance | §7 | meeting "across the three platforms"; no amounts given | correct (but see #9) |
| 109 | 04 review sheet: Caroline's cash; bridging-loan timing | §7 | meeting "To summarise the actions I noted: confirm Caroline's Meridian cash balance, and confirm the timing of the bridging-loan repayment." | correct |
| 110 | 04 must not appear: earnout invested; £850,000 as amount; closed account; general-doc figures | §7 | as above; "Pendle Global Fund … £775,000"; "Sutton Strategic Fund … £785,000" | correct |
| 111 | General documents contain platform-wide figures and a paraphrased risk warning | §3 table | see #31 | correct |
| 112 | Statement image = account values with dates | §3 table | images: "Value", "Valued on" columns | correct |
| 113 | Joint owners by name, e.g. "David Clarke & Susan Clarke" | P9 | db holder names "David Clarke", "Susan Clarke" | correct |
| 114 | Images only repeat the account data | P10 | 02/03/04 images match db rows exactly; no Brightwell/Meridian rows in 04 | correct |
| 115 | At full resolution every image value is in £ | P10 | all 9 value cells show "£" | correct |
| 116 | Open actions like "confirming a small out-of-scope cash balance, the timing of a loan repayment" exist | P2 | 03 "confirm the outstanding cash balance"; 04 "confirm the timing of the bridging-loan repayment" | correct |
| 117 | "a portion" of an account to be sold | P2 | 04 "disinvest a portion of the Holloway joint GIA" | correct |
| 118 | Baseline quoted an out-of-date CGT exempt amount | P4 | see #42–43 | correct |

---

## B. Errors and ambiguities in the rules and policies (most serious first)

**B1. The gates check the pipeline against its own ledger, not against the truth.** G2, G5 and G6 are
checked "against the facts ledger", which is the pipeline's own output. If reconciliation picks
£40,000 over c. £45,000, the ledger holds £40,000 and G6 passes. The same happens when the ledger marks
"no disposal" and G5 passes. Gates that verify internal consistency can't show correctness. The eval
must check against independent expected-facts fixtures (§7 for the four clients; generator output for
synthetic ones), and the ledger check is a second, separate layer.

**B2. R3 and P10 contradict each other on statement images.** R3: "the most recent dated figure wins."
The §3 table calls the image "a further dated source". P10: an image value "never overrides the account
data or a later-dated meeting figure". If an image shows a value dated after the db's `valuation_date`
(for example, a statement struck on 10 May for an account whose db value is dated 28 Feb), R3 selects
the image and P10 forbids it. The current clients don't trigger this (every image date equals the db
date), so the conflict would first appear on an unseen client.

**B3. R3 doesn't separate a value seen in the meeting from one only mentioned in it.** It says "a
meeting figure dated after an account's `valuation_date` beats it". All three live values carry
explicit viewing language ("pulled the account up live", "Pulling it up during the meeting", "pulling
it up live"). A meeting note will also quote figures from memory or from old paperwork, as client 03
already does ("the last statement they had to hand"). Under R3 as written, a recalled figure takes the
meeting date and wins.

**B4. Limit detection depends on P4, a [confirm] item, but §7 treats it as settled.** The §7 client_02
marker ("above the annual ISA allowance") needs an allowance figure that no source gives. If P4 is
rejected, nothing in §3/§4 produces that marker, and the pipeline would recommend "split the proceeds
equally into both ISAs" (§7's own Advice line) without qualification. There is also a real gap in the
client_02 plan that §7 understates. Even with no part-funding, two allowances hold at most £40,000,
which is less than "a little over £45,000", so part of the proceeds has nowhere agreed to go. P4
doesn't say whether a full-allowance subscription with unknown prior use (client_01's £20,000;
client_04's "use both ISA allowances") triggers a marker. If it does, Q6's calibration suffers; if it
doesn't, a real breach can pass.

**B5. R4 and R5 disagree on amounts, and their order isn't stated.** R4: "Decisions and amounts: the
meeting record wins." R5: where the request is exact and the meeting approximate, "use the exact one"
(the request). For client_03 (request "GBP 120,000", meeting "around £120,000"), R4 picks the meeting
and R5 picks the request. §7 follows R5. Neither rule says what happens when the two figures are not
consistent (request 120,000, meeting "around £150,000"). That case should be a conflict, but R5 as
written would silently take the request.

**B6. What counts as a disposal is broader in G5/P7 than in the spec.** The spec says to include Tax
Implications "ONLY if the recommendation involves selling or disposing of investments that may create a
taxable capital gain". G5 says "if and only if the advice involves a disposal". A switch inside an ISA
or SIPP, or encashing the offshore bond (client_04 holds one; the meeting says "revisit at the next
review"), is a disposal that creates no CGT (the bond gives a chargeable-event gain taxed as income).
G5 would include a CGT section in both cases.

**B7. The client_04 plan has undefined amounts that §7 doesn't fully mark.** (a) ISA amounts are a
marker for 03 but not for 04 (A#9). (b) Whether the partial-sale proceeds join the £650,000 or stay in
the GIA isn't stated: "disinvest a portion of the Holloway joint GIA and rebalance it" sits alongside
"add to the Holloway joint GIA". (c) The new account's platform and type are stated nowhere, but the
table's Type column and the Fees section both need them.

**B8. Per-client guidance is treated as if it carries general rules.** The §3 table trusts internal
guidance for "what a person finalises", but only client_01's `fde_notes.md` says it. An unseen client's
notes may carry no general rules at all (clients 02–04 don't). Separately, client_03's fde notes call
Jean "the client" ("the client received following the recent death of her mother"), but the db role
`client` is Robert. Any logic that maps fde "the client" to the db `client` role attributes the
inheritance to the wrong person.

**B9. P6 and §7 disagree on tangents and aspirations** (A#10). P6 says tangents "never appear" and
aspirations appear "at most once in Background". §7 says "as actions" for both. The eval will implement
one of them, and the two give different verdicts on a report that says "we noted your planned trip".
Client_03's "grandchildren" isn't classified at all: tangent or aspiration?

**B10. R6 doesn't cover an in-scope account that is closed or doubtful.** "Closed accounts are ignored"
works for M4-OLD-C, which is out of scope. If the request names an account the db marks closed, R6
silently drops an in-scope account and G1 passes. Client_03's meeting doubts whether an open account is
active ("not even sure it was still active"). R1 keeps the db status, and nothing requires the
disagreement to be flagged.

**B11. Nothing says how scope is resolved.** R2 makes the request win on scope, but the request is prose
("the joint GIAs (Holloway and Brightwell)", "Holloway ISAs (David and Susan)"). Matching that prose to
account IDs is its own step, with no rule for a phrase that matches nothing, or more than one account.

**B12. Approximate direction is lost.** P9 renders "a little over £45,000" as "c. £45,000". R3 says the
approximate language "is kept", and G6 says "says it is approximate … where the source says so". "c."
means about; the source gives a floor. That's minor for the client, but the footnote should quote the
source wording.

**B13. Risk-profile labels aren't a stable mapping.** "4 (moderate)" (01, 03), "5 (balanced)" (02),
"4 (balanced to moderate)" (04). §4 has no policy saying to copy the label verbatim. A model or code
path that derives the label from the number gets client_04 wrong.

**B14. Blocking open actions aren't separated from informational ones.** P2 sends "confirming a small
out-of-scope cash balance" to the review sheet only. Client_03's meeting says "we will confirm it before
anything is finalised", which is a sign-off precondition in the adviser's own words. The review sheet
should mark items as blocking or not.

---

## C. Unhandled patterns (grounded in variation the four clients already show)

| # | Pattern | How it could appear | What current rules do | Proposed rule |
|---|---|---|---|---|
| C1 | Statement image dated later than the db, or disagreeing with it | `statement_summary.png` row "Holloway ISA (David) £63,200, 12 May 2026" with db £61,000 at 30 Apr | R3 selects the image; P10 forbids it (B2) | Images never select a value. Any image/db difference (value or date) → review-sheet conflict; the report uses the db or the meeting live value; if the image is the *only* later figure, show the db value and flag it |
| C2 | Meeting quotes a figure from memory or old paperwork, not viewed live | "They thought the ISA was worth around £70,000 on the last statement" | R3 treats it as meeting-dated and lets it win (B3) | A meeting value supersedes only when the note says it was viewed during the meeting; otherwise it goes to the review sheet with its wording and never selects |
| C3 | Live value for an account not being sold | "I also checked Susan's ISA, showing around £60,000" | R3 handles it (latest wins), but §5.1 implies only sold accounts move | Apply R3 to every account; footnote any value that is approximate |
| C4 | Request and meeting disagree on selling or on an amount | Request "Selling existing investments? \| No"; meeting "we agreed to sell part of the GIA" | R4 flags, but G5 still needs a yes/no to decide the section | On a disposal conflict: include Tax Implications with a marker and a review-sheet conflict (flagging a possible disposal is safer than omitting one). On an amount conflict (exact vs inconsistent approximate): marker and review-sheet entry (B5) |
| C5 | Joint account with inconsistent copies | H-GIA-J under David at £40,000 (15 Mar) and under Susan at £41,500 (30 Apr) | Dedup isn't specified beyond "count once" | Dedupe by `account_id`. If the copies differ, it's a conflict → review sheet, and R3 picks between them |
| C6 | Joint account but only one holder block | Single-holder file with `"owner": "Joint"` | P9 can't name the second owner | Joint with an unknown co-owner → owner cell "Margaret Hughes & [ADVISER TO CONFIRM: joint holder]" |
| C7 | Account ID suffix misleading about ownership | Already present: M4-CASH-J owned by James alone, while B4-GIA-J is joint | No rule | Ownership from the `owner` field only; never infer it from the ID (add to R1) |
| C8 | Scope phrase that doesn't resolve | "the Brightwell ISA" when the db has none; "the joint GIAs" when three joint GIAs exist | Not covered (B11) | Every scope phrase must resolve to ≥1 db account or a declared new account; an unresolved or over-broad match is a hard flag, never a guess |
| C9 | In-scope account closed or with a null value | Request covers "Meridian cash" and the db says closed or null | R6 drops closed accounts silently; null gets a marker | In scope + closed → conflict flag, not silent removal. In scope + null → marker (already R6) plus a review-sheet entry |
| C10 | New money not yet received, worded softly | "Inheritance of around £90,000 expected once probate completes" (cf. client_03's "which has now cleared") | P5 covers it if extraction classifies it correctly; nothing defines the classes | Every money item is classified as received / committed / contingent / expected-not-received, with the quote. Only received minus committed is available; the others are named as excluded |
| C11 | Committed amount unspecified | "Some of the proceeds will go to the tax bill" | P5 can't subtract, so available money is overstated | If any commitment lacks an amount, "available to invest" becomes a marker; never subtract a guessed amount |
| C12 | Disposal inside a wrapper, or a bond encashment | "Switch funds within the ISA"; "surrender the offshore bond" | G5 adds a CGT section (B6) | Tax section only for disposals in taxable accounts (GIA, direct holdings); wrapper switches → none; bond → marker "chargeable-event gain to be assessed" |
| C13 | Request field missing or "TBC" | "Initial charge \| TBC", or no risk-profile row | P3 would state whatever is there, or the model defaults to 0% | Missing or TBC request field → marker; never default |
| C14 | Risk label and number drift | as B13 | No rule | Copy the request's risk profile verbatim (number and label); check it with a deterministic gate |
| C15 | Allowance at the limit with unknown prior use | client_01 £20,000; client_04 "use both ISA allowances" | Unspecified (B4) | Decide explicitly: a marker only when the sources show prior use ("part-funded") or the planned total exceeds the rule figure; otherwise a review-sheet note, not a report marker (keeps Q6 calibrated) |
| C16 | Several meeting notes, or files named differently | `meeting_notes_2025.docx` plus `file_note_may.docx` | §3 classifies by role but doesn't say which meeting governs | The latest-dated meeting record governs decisions; older ones contribute dated values only, at R3 precedence |
| C17 | General rules absent from fde notes | as clients 02–04 | Risk that the pipeline needs fde text to know CGT and fees are markers | General processing rules live in config/code; fde notes contribute only "This client" handling |
| C18 | Non-GBP currency | `"currency": "EUR"` (the field exists in every db record) | No rule | Non-GBP value → no conversion; value cell marker; review-sheet entry |
| C19 | Directional approximation | "just under £50,000", "at least £30,000" | Reduced to "c." (B12) | Keep the source phrase in the footnote; table may use "c." |

---

## D. Success criteria: gaps and problems

1. **Correctness is checked against the pipeline's own ledger** (B1). G2, G5 and G6 should check against
   independent expected facts. The ledger comparison stays as a traceability check (S5).
2. **G2 checks only "£ figures".** It misses percentages (the distractor "6.4 per cent", the baseline's
   invented "20%" CGT rate and "0.5%" fee rates), "£45k", and figures in words. It also passes any
   ledger value, including values the report must *not* use: the superseded £40,000, or
   client_04's out-of-scope £30,000 cash if it appears in prose (G1 only covers the table). Proposed:
   every numeric token must match a ledger entry marked *reportable*, or an allowlist (dates, tax year,
   risk-profile number, initial charge).
3. **G3 needs context to separate rates.** "0.5%" is legitimate as the initial charge and forbidden as
   an advice charge. A deterministic check must allow only the request's initial-charge token, and only
   in a charge context.
4. **G4 doesn't catch paraphrases.** Baseline client_03's Tax section says "We are authorised and
   regulated by the Financial Conduct Authority (FCA)" (line 49) in addition to the static line. G4
   passes (the verbatim line appears once), yet a model-written FCA statement reached the report. Both
   general documents also carry paraphrased risk warnings. Add a fuzzy-match ban outside the static slots.
5. **No gate requires the expected markers to be present.** G3 says forbidden figures don't appear, but
   a report that silently omits Fees content has no figure and no marker, and G3 passes. fde_notes:
   "the gaps must not be hidden". Q6 (scored, not a gate) is the only check. Proposed gate: every
   expected marker is present.
6. **No gate for risk profile, initial charge, client names or new-account rows.** These are exact facts
   in §7 with no gate. Add a deterministic one: risk profile and initial charge match the request
   verbatim; names match the db; new accounts show "To be opened".
7. **The review sheet has no criteria.** It is one of the two outputs (§1), yet nothing in §2 checks it
   lists every conflict, superseded value, null out-of-scope account and open action. Add review-sheet
   gates.
8. **G9's definition is loose.** The account table lives in Background (spec), so "no transaction
   amounts" must exclude table values. Client_04's £850,000 is circumstance and also "the size of any
   new money". The spec bans it; G9 should say so explicitly.
9. **G10's n-gram overlap will misfire both ways.** Fde notes share vocabulary with legitimate facts
   ("inheritance", "sold a business") and miss paraphrase ("reference its origin with appropriate
   sensitivity" → "we are mindful of…"). It needs a threshold tuned against phrases also found in the
   meeting or spec, plus a judge check.
10. **G5 can't be checked deterministically if "disposal" is unsettled** (B6).
11. **§7 client_01 "CGT content" isn't operational** (A#11). Say "no Tax Implications section and no CGT
    figure".
12. **§9.1 synthetic clients are generated from the same rules the pipeline implements**, so they can't
    reveal a wrong rule, only a wrong implementation. Some held-out-style cases need hand-written
    expected facts (C1, C2, C5 and C9 are good candidates).
13. **S4 "a re-run on unchanged inputs costs nothing"** is a caching claim. It holds only if the cache key
    includes the model, prompt version and config. Worth stating.
14. **Q6 "deterministic against expected flags"** exists only for clients with fixtures. On unseen
    clients calibration is judge-only, which should be stated.

---

## E. The [confirm] items

**P1 Marker format: agree, with two additions.** A single fixed prefix makes markers countable and
lets the gates in D5 work. Additions: (a) markers are inserted by code from the ledger, never typed by
the model, so the prefix can't be malformed or invented; (b) give each an ID that matches its
review-sheet row (`[ADVISER TO CONFIRM #3: …]`), so the person finalising can reconcile the two outputs.
Risk: markers inside table cells make the table wide. That's acceptable.

**P4 Rule figures in a reference file, detection only: agree, and it can't stay pending.** §7
client_02's key marker depends on it (A#6, B4). Without a reference file, the plan-breaches-a-limit
pattern (§5.8) can't be detected in code. The alternative, always flagging every ISA or pension amount,
over-flags and hurts Q6. Conditions: key the file by tax year, derive the tax year from the meeting
date (6 April boundary), and if the year is missing from the file, raise a marker rather than skip
detection. Settle the trigger rule for "full allowance, prior use unknown" at the same time (C15).

**P6 Aspirations and tangents: agree in substance; fix the inconsistency first.** Mentioning a stated
aspiration once, as not covered, shows the adviser heard it and scoped it out. That's defensible in a
suitability report. Tangents add nothing and should never appear. But §7 must be rewritten to match
(B9), and each item needs a class, because the eval checks the two differently (absent vs at most once,
Background only). Client_03's "grandchildren" as mentioned is a tangent ("nothing there changes the
advice"). If the team prefers simpler, deterministic evaluation, "aspirations never appear" is the
easier rule to check, at a small cost in report completeness.

**P10 Statement images at low trust: agree with low trust; reconsider whether to read them at all yet.**
Low trust is right: a vision read can misread currency or digits, as the unsupported €/$ anecdote
illustrates, and the images currently add nothing. Before confirming: (a) fix the R3 contradiction (B2)
so "low trust" has one meaning; (b) define "disagree": a currency-symbol mismatch should read as a
likely misread, not a client conflict, or the review sheet fills with noise (Q6); (c) cost isn't the
issue (three images), but review-sheet noise and one more model call to cache and evaluate are. A
defensible alternative: log that an image exists and list it on the review sheet as "not machine-read:
check against table". That catches the same disagreement by a person, with zero hallucination risk,
until a vision step is measured by the eval.

---

## F. Proposed edits to SCOPING.md (exact before → after)

**F1. §2.1 G2 "How checked" (line 33)**
- Before: `| Deterministic: every £ figure in the report must be in the facts ledger |`
- After: `| Deterministic: every numeric token in the report (£, %, "k", figures in words) matches an expected fact marked reportable for this client, or an allowlisted non-financial number (dates, tax year, risk-profile number, the request's initial charge) |`

**F2. §2.1 G4 (line 35)**
- Before: `| G4 | The FCA authorisation line and the risk warning appear verbatim, exactly once each. | Deterministic |`
- After: `| G4 | The FCA authorisation line and the risk warning appear verbatim, exactly once each, and no paraphrase of either appears elsewhere. | Deterministic (exact match + fuzzy match outside the static slots) |`

**F3. §2.1 G5 (line 36)**
- Before: `| G5 | The Tax Implications section is present if and only if the advice involves a disposal. | Deterministic, against the facts ledger |`
- After: `| G5 | The Tax Implications section is present if and only if the advice involves selling or disposing of investments held outside a tax-exempt wrapper (e.g. a GIA). Switches inside an ISA or SIPP do not trigger it; a bond encashment raises a marker instead. | Deterministic, against the expected facts |`

**F4. §2.1 G6 (line 37), "How checked" cell**
- Before: `| Deterministic, against the facts ledger |` (the G6 row)
- After: `| Deterministic, against the expected facts |`

**F5. §2.1: add rows after G12**
- After G12 add:
  `| G13 | Risk profile and initial charge match the report instruction verbatim; client names match the account data; new accounts show "To be opened". | Deterministic |`
  `| G14 | Every expected marker is present, and nothing the sources settle carries a marker. | Deterministic, against the expected facts |`
  `| G15 | The review sheet lists every conflict (both values, sources, dates, winning rule), every superseded value, every out-of-scope account with no value, and every open action, each marked blocking or not. | Deterministic, against the expected facts |`

**F6. §3 table, Internal guidance row (line 81)**
- Before: `| Internal guidance | \`fde_notes.md\` | How to process (tone, per-client handling, what a person finalises) | Report text: never quoted |`
- After: `| Internal guidance | \`fde_notes.md\` | Per-client handling (the "This client" section). General processing rules (what a person finalises, the FCA line) appear in only some clients' notes, so they live in config, not here | Report text: never quoted; its "the client" is not necessarily the account data's \`client\` role |`

**F7. §3.1 rule 1**
- Before: `1. **Existence and ownership**: the account data wins. A new account comes only from the report`
- After: `1. **Existence and ownership**: the account data wins, from the \`owner\` field only (never inferred from an account ID). A new account comes only from the report`

**F8. §3.1 rule 3 (line 91 onward)**
- Before:
  ```
  3. **Values**: the most recent dated figure wins. A meeting figure dated after an account's
     `valuation_date` beats it. Approximate language ("around", "a little over") is kept as approximate.
     The superseded value and both dates go to the review sheet.
  ```
- After:
  ```
  3. **Values**: the most recent dated figure wins, among the account data and figures the meeting
     record says were viewed during the meeting (e.g. "pulled it up live"). A figure recalled from
     memory or old paperwork, and any statement-image value, never selects a value: it confirms or
     raises a conflict (P10). Approximate language ("around", "a little over") is kept, and the
     footnote quotes it. The superseded value and both dates go to the review sheet.
  ```

**F9. §3.1 rules 4–5**
- Before: `4. **Decisions and amounts**: the meeting record wins; the report instruction confirms. If they`
- After: `4. **Decisions and amounts**: the meeting record wins on what was decided; the report instruction confirms. If they`
- Before: `   approximate one for the same amount, use the exact one.`
- After: `   approximate one for the same amount, use the exact one, provided the approximate figure is consistent with it (e.g. "around £120,000" and "GBP 120,000"). If it is not, that is a conflict under rule 4.`

**F10. §3.1 rule 6 (line 98)**
- Before: `6. **Missing, null or closed**: never given a value. Closed accounts are ignored. Open accounts with no`
- After: `6. **Missing, null or closed**: never given a value. Closed accounts outside scope are ignored; a closed account inside scope is a conflict to flag, never silently dropped. Open accounts with no`

**F11. §3.1: add rule 8**
- After rule 7 add:
  `8. **Scope resolution**: every account named in the report instruction must resolve to at least one account in the account data, or to a new account it creates. An unresolved phrase, or one that matches more accounts than it names, is flagged, not guessed.`

**F12. §4: add P11**
- Add:
  ```
  **P11. Risk profile and request fields**
  The risk profile is copied from the report instruction verbatim, number and label ("4 (balanced to
  moderate)"); labels are never derived from numbers. A request field that is missing or says "TBC"
  becomes a marker, never a default.
  ```

**F13. P9 (line 149)**
- Before: `under the table giving its basis and date, and the last statement value. New accounts show`
- After: `under the table quoting the source's wording ("a little over £45,000, viewed live on 14 May 2026"), and the last statement value and date. New accounts show`

**F14. P10 (lines 157–159)**
- Before: `disagree would be caught. Low trust is deliberate: a vision read can hallucinate. A separate automated`
  `read of these same images reported "€61,000" and "$240,000"; at full resolution every value is in £.`
  `Cost is small (one image per client).`
- After: `disagree would be caught. Low trust is deliberate: a vision read can hallucinate (a currency misread is treated as a read error, not a client conflict). Cost is small (at most one image per client; client 01 has none).`
  (Either cite where the €/$ read is recorded, or remove it: nothing in the repo supports it.)

**F15. §5.1 (line 170)**
- Before: `   ~£255k). Accounts not being sold are current.`
- After: `   ~£255k). Accounts not being sold carry the 30 April 2026 snapshot value; only client 04's meeting confirms some of them ("in line with the snapshot").`

**F16. §5.8 (line 178)**
- Before: `8. **Limits the plan may breach** (02: ISA top-ups; 04: SIPP contributions).`
- After: `8. **Limits the plan may breach** (02: ISA top-ups: even two full allowances are less than the proceeds; 04: SIPP contributions, and full ISA subscriptions with prior use unstated; 01: a full-allowance top-up with prior use unstated).`

**F17. §6 G11 (line 191)**
- Before: `  recommendation and the risk warning. The account table appears two to four times per report.`
- After: `  recommendation and the risk warning. The account table appears two or three times per report (client 01: twice; clients 02–04: three times).`

**F18. §6 G1 (lines 198–200)**
- Before:
  ```
  - **G1, all four:** out-of-scope accounts in the table (client 01's cash account; client 03's
    unconfirmed cash account; all ten client 04 accounts including a closed one and one with no value).
    Joint owners shown as "Joint".
  ```
- After: `- **G1, clients 01, 03, 04:** out-of-scope accounts in the table (client 01's cash account; client 03's unconfirmed cash account; client 04's table lists all ten accounts in the data, including James's out-of-scope cash, a closed one and one with no value). **G1, clients 02–04:** joint owners shown as "Joint" (client 04's Tax-section table uses first names only).`

**F19. §6: add a bullet** (omissions found in the baseline)
- Add: `- **Also:** G4, client 03: the Tax section paraphrases the FCA line (verbatim-once still passes). G9: amounts in Background (01 £20,000; 03 £120,000; 04 £850,000 and £200,000). P4: client 04 quotes "£20,000 each" for the ISAs. R5: client 03 uses "approximately £120,000" instead of the exact £120,000. G11: risk warning twice in 02 and 04; closing line twice in 01.`

**F20. §7 intro (line 212)**
- Before: `Hand-derived from the sources. Seed for the eval's expected facts. Values as at the meeting date.`
- After: `Hand-derived from the sources. Seed for the eval's expected facts. Values are the latest available on the meeting date: the snapshot value unless the meeting records a later, live-viewed one.`

**F21. §7 client_01 (line 220)**
- Before: `- **Must not appear:** the market update's platform figure or fund name; any gifting action; CGT content.`
- After: `- **Must not appear:** the market update's platform figure or fund name; any gifting action; a Tax Implications section or any CGT figure (a statement that nothing is sold is fine).`

**F22. §7 client_02 (line 225)**
- Before: `- **Advice:** sell the joint GIA in full; split the proceeds equally into both ISAs.`
- After: `- **Advice (as agreed):** sell the joint GIA in full; split the proceeds equally into both ISAs. The report must not state that all the proceeds go into the ISAs: see the ISA marker.`
- Also add after the Markers bullet: `- **Review sheet:** GIA statement value £40,000 (15 March) superseded by the live c. £45,000 (14 May); where any proceeds above the ISA allowances go.`

**F23. §7 client_03 (line 243)**
- Before: `- **Must not appear:** grandchildren or the trip as actions; the platform figures or fund names from`
- After: `- **Must not appear:** the grandchildren or the trip (tangents: not at all, P6); the platform figures or fund names from`
- Also add: `- **Review sheet:** GIA statement value £30,000 (10 March) superseded by c. £38,000 (16 May); Jean's cash account, blocking ("confirm it before anything is finalised"); type and platform of the new joint account.`

**F24. §7 client_04 markers (line 262)**
- Before: `- **Markers:** CGT; platform charge rates (three platforms); advice charge rate; SIPP contribution`
- After: `- **Markers:** CGT; platform charge rates (three platforms, and the new account's if on another); advice charge rate; ISA subscription amounts (or "full allowance" wording with no figure: decide); SIPP contribution`
- And line 264:
  - Before: `- **Review sheet:** Caroline's cash balance; bridging-loan repayment timing.`
  - After: `- **Review sheet:** Caroline's cash balance; bridging-loan repayment timing; Holloway GIA statement value £240,000 (28 February) superseded by c. £255,000 (20 May); whether the partial-sale proceeds stay in the GIA or join the £650,000; the new account's platform.`

**F25. §7 client_04 must-not-appear (lines 265–267)**
- Before:
  ```
  - **Must not appear:** the earnout as invested; £850,000 as the amount to invest; school fees, charity
    or the French property as actions; the closed account; the platform figures or fund names from either
    general document; any CGT figure.
  ```
- After:
  ```
  - **Must not appear:** the earnout as invested; £850,000 as the amount to invest; school fees or
    charity in Recommendations (at most once in Background, as not covered, P6); the French property at
    all; James's Meridian cash account; the closed account; the platform figures or fund names from
    either general document; any CGT figure.
  ```
