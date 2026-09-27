# Design: advice report pipeline

Built against `SCOPING.md` (the requirements: gates G1–G16, quality Q1–Q6, system S1–S6, trust rules
R1–R10, policies P1–P12). This document says **how**; SCOPING says **what**. Where the two could
disagree, SCOPING wins and this document is wrong. Decision numbers (D1…) refer to `DECISIONS.md`.

Cost figures here are **pre-build estimates** from token guesses and the published price list
(retrieved 2026-09-27). They are replaced by measured values from run summaries (S3) once the pipeline
runs; no estimate is quoted as a result.

---

## 1. Principles

1. **Code decides, models read and write.** Every decision with a right answer (which value wins, what
   is in scope, what is available, which sections appear, what gets a marker) is a function in code
   with a unit test. Models do four narrow jobs: read unstructured sources into typed facts, gather
   quoted evidence for an open question (the investigation agent, §5.2), write prose around the facts,
   and judge prose that code cannot judge. In every one, code verifies what the model returns.
2. **A model never types a figure.** Extraction returns a verbatim quote and code parses the number
   from it. The writer sees fact IDs, never numbers, and writes tokens that code fills from the ledger
   (D1). A digit in writer output is a validation failure.
3. **One ledger, one truth per run.** Every stage writes to a typed facts ledger. The table, the
   tokens, the markers, the review sheet and the production gates all read from it, so the report
   cannot contradict itself (the baseline's client 03 GIA contradiction becomes impossible).
4. **Bounded loops, never unbounded agents** (D5). A model can retry against a code check, or call
   tools, a fixed number of times. Hitting the limit never produces a guess: an unverified fact is
   dropped to the review sheet, an open question stays unresolved, and a section still failing a hard
   gate makes the run a failed generation.
5. **Generic by construction.** No client value in `src/` or `config/` (`check_repo.py`). Prompts
   describe patterns, and the eval scores unseen clients (hand-written and synthetic).
6. **Degrade visibly; stop only when unsafe** (D13, D16). An odd or missing input becomes a marker, a
   review item or a conservative default, never a silent guess. The run stops only when there is no safe
   basis for a draft (§8.4).

---

## 2. The pipeline

```
client folder
   │
   ▼
[1] classify ────────── code (schema checks) + model (text documents)       → sources[]
   │
   ▼
[2] extract ⟲ verify ── model per source role incl. scope mapping and image;
                        quotes, dates and labels checked in code (≤3)        → verified raw facts
   │
   ▼
[3] reconcile ───────── code only: R1–R10, P2–P12                           → ledger + open questions
   │  ⟲ investigate ─── model agent, read-only tools, per open question (≤5 × ≤6 tool calls);
   │                    returns quoted evidence; code verifies it and re-runs the rules → ledger
   │
   ▼
[4] plan ────────────── code: section inclusion, fact slices, table, markers → section plans
   │
   ▼
[5] write ⟲ repair ──── model per slot; section gates in code (≤2)          → slot drafts
   │
   ▼
[6] assemble draft ──── code: tokens filled, table built, formatting.py      → draft report
   │
   ▼
[7] gate ⟲ repair ───── code: report-level gates; model: release judge (≤1)  → pass | fail
   │
   ▼
[8] write outputs ───── code: report or failure file, review sheet, ledger, run summary
```

| # | Stage | Code or model | Model (default, config) | Calls per report | Est. cost (Luna) |
|---|---|---|---|---|---|
| 1 | Classify | Code for JSON; model for text documents; images are candidates until stage 2 | gpt-6-luna, reasoning `none` | 1 per text document (≈5) | ≈$0.001 |
| 2 | Extract | Model + code verification loop | gpt-6-luna, reasoning `medium` | meeting 1–3, instruction + scope 1–2, guidance 1, image 0–1 | ≈$0.004 |
| 3 | Reconcile | Code | none | 0 | 0 |
| 3a | Investigate | Model agent with read-only tools; code verifies and decides | gpt-6-luna, reasoning `medium` | 0 when nothing is open; ≤5 questions × ≤6 tool calls | ≈$0.003 per question (context grows each tool round trip); ≤$0.015 |
| 4 | Plan | Code; a model only for a conditional section with no `predicate` (none in the shipped config) | gpt-6-luna, reasoning `low` | 0 | 0 |
| 5 | Write | Model + code gates loop | gpt-6-luna, reasoning `low` | 1 per generated slot (≈5), +repairs | ≈$0.003 |
| 6 | Assemble draft | Code | none | 0 | 0 |
| 7 | Gate + release judge | Code gates; model judge, quotes verified in code | gpt-6-luna, reasoning `high` | 1–3 (G16 coverage re-ask; one re-run after a repair) | ≈$0.003–0.009 |
| 8 | Write outputs | Code | none | 0 | 0 |
| | **Total** | | | ≈15 | **≈$0.011** |

Prices per 1M tokens (input / output): gpt-6-luna $0.10 / $0.50; gpt-6-sol $2.00 / $10.00. Sol costs
20× Luna for the same tokens, so Sol extraction is ≈$0.08 and a Sol release judge ≈$0.06; with both on
Sol the estimate is ≈$0.144 per report. The eval judge (Sol) adds ≈$0.07 per scored report. Repair
rounds, verification re-asks and tool round trips add to these; the run summary measures them (S3).

**Model per stage is config, and extraction and the release judge are chosen by measurement (D2).**
Luna is the default everywhere in the pipeline. §10.7 runs both Luna and Sol on the four clients and
the hand-written cases; a stage moves to Sol only if Luna measurably misses (an extraction fact Sol
gets right, a mutation Sol's judge catches, or more false alarms on clean reports). The result and its
results file are recorded as a decision.

---

## 3. Sources: classification and adapters

### 3.1 Roles (SCOPING §3)

`account_data`, `meeting_record`, `report_instruction`, `report_spec`, `internal_guidance`,
`statement_image`, `general_document`, `unknown`. Unknown is excluded and logged; nothing unclassified
reaches a prompt.

### 3.2 Classification (D7)

Relevance is decided by what a document is, not its name.

1. **Structural checks (code):** a JSON file that validates against the account-data schema is
   `account_data`; an image file is a `statement_image` **candidate**. The vision call in stage 2
   confirms it (it returns `is_account_statement` with the table it read); if not, it becomes
   `unknown` and is logged.
2. **Model (text documents):** each document's first ≈2,000 characters go to a classifier with a
   structured output `{role, evidence_quote, confidence}`. Code verifies the evidence quote is in the
   document. The prompt defines each role by its function ("addressed to all clients of a platform, not
   one client" → general document), never by file name. `confidence` below the configured threshold,
   or an unverified evidence quote, makes the document `unknown` (excluded and logged).
3. **Consistency rules (code):** a report needs account data, a report instruction and a meeting
   record. Missing any of them, or two account data sources or two report instructions that disagree,
   means there is no safe basis for the table or the advice: the run stops as a failed generation with
   the reason (§8.4). Two identical copies are deduplicated with a review note. Several meeting records
   are allowed (R10); the latest-dated one governs decisions.

Alternatives: filename mapping (breaks on renamed files); pure heuristics on content (brittle on unseen
phrasing). The model costs ≈$0.001 per report.

### 3.3 Adapters

One adapter per **format**, one extractor per **role** (S6: a new source type is one new adapter or
extractor, registered in one table).

| Adapter | Reads | Produces |
|---|---|---|
| `json_accounts` | account data JSON | typed `AccountRecord`s per holder. Tolerant schema: unknown fields are ignored and logged; optional fields (`platform`, `currency`, `value`, `valuation_date`, `snapshot_date`) may be missing and are handled by the rules (a missing currency is treated as not-GBP under P12; a missing platform makes the charges marker say so). An account missing an identifying field (`account_id`, `type`, `status`) is set aside as a review item, and a conflict if it is in scope. Only unreadable JSON or no holders at all stops the run (§8.4) |
| `docx` | .docx | paragraphs and tables as structured text, with stable paragraph IDs for quoting |
| `markdown` | .md | heading-split sections |
| `image` | .png/.jpg | bytes + sha256 for the vision call |

`src/document_formatter/loading.py` stays for the starter path; adapters replace it in the new
pipeline.

### 3.4 Statement images (P10)

The image extractor sends the image (full resolution) to the vision-capable default model with the
same `ValueObservation` schema the meeting extractor uses, plus the currency symbol as printed. Its
observations enter reconciliation at **low trust**: they confirm or raise a review-sheet discrepancy,
and never select a value. A currency-symbol mismatch is always a review item, labelled "possible read
error" where the account data says GBP.

---

## 4. Extraction

### 4.1 Quote-anchored facts

Every extracted fact carries a verbatim quote and the ID of the paragraph it comes from. Code then:
1. verifies the quote occurs in that paragraph (whitespace-normalised, exact otherwise);
2. **parses every amount and date from quotes itself** (`£45,000`, `GBP 120,000`, `£1.2m`, `up to
   £400,000`; `held 14 May 2026`, `15 Mar 2026`), with the qualifier (`around`, `a little over`, `up
   to`), ignoring any number or date the model put in a field. This includes `meeting_date`, which
   decides R3 recency, R10 and the P4 tax year. If no date can be parsed from a quote, the meeting is
   **undated for R3 and R10**: its values confirm or conflict but never select, and it never governs
   decisions over a dated record (if the only dated record is older, the older one governs and a
   blocking review item says so). A metadata date (docx core properties) is not when a figure was
   seen, so it is used **only** to derive the P4 tax year, labelled as such; without it the tax year is
   unknown and P4 raises its marker. Each fallback is a review item naming what was used;
3. rejects facts whose quote fails either check.

Rejections go back to the model in the verification loop (≤3 rounds) with the exact failure ("quote
not found in paragraph p12"). The model may call one tool, `find_in_source(text) → matching
paragraphs`, to locate wording. Facts still failing after three rounds are dropped and become review
items ("could not verify: …"), never report facts.

### 4.2 Labels that decide outcomes

A verified quote proves the text exists, not that the model's label for it is right. Some labels
decide outcomes: an observation's `basis` (R3 selection), a money item's `class` (P5, G7), `blocking`
(P2), a disposal's `extent` (P5, G5), and tangent vs aspiration (P6). Each of these carries:
1. **a label evidence quote**: the words that justify the label ("I pulled the account up live", "is
   already committed to", "contingent on", "before anything is finalised"), verified like any quote
   and required to be in the same paragraph as the fact it labels;
2. **a conservative default in code** when the label or its evidence is missing or unverified:

| Label | Unclear or unverified → | Why this default is safe |
|---|---|---|
| `basis` = viewed in meeting | treated as `recalled`: confirms or conflicts, never selects | a stale value is flagged, never silently replaced |
| money `class` | not available; review item | money is never allocated on a guess (G7) |
| `blocking` | blocking | an adviser sees it before sign-off |
| disposal `extent` | `unspecified` → amount marker (P5) | no proceeds counted |
| tangent vs aspiration | tangent (never appears) | omitting beats wrongly including |

3. **per-label scoring in the extraction eval** (§10.7), so a wrong label shows up as a measured miss;
4. **visibility on the review sheet**: every label that selected a value or changed available money is
   listed with its evidence quote, so the adviser can check it.

So code decides the outcome from labelled evidence; the model's labels are inputs that are verified,
defaulted conservatively and measured, not trusted.

### 4.3 Extractors and schemas (abridged; full schemas in `extract/schemas.py`)

**Meeting record** → `MeetingExtraction`:
- `meeting_date` (quote), `attendees` (names as written)
- `value_observations[]`: account reference as written, amount quote, `basis`:
  `viewed_in_meeting | recalled | from_paperwork | confirmed_unchanged` with its label evidence (R3).
  `confirmed_unchanged` ("in line with the snapshot") is recorded as a confirmation of the account data
  value on the meeting date: it adds no new value and is shown on the review sheet as confirmed.
- `money_items[]`: `received | committed | proceeds | external`, amount quote or none, what it is for,
  label evidence (P5)
- `agreed_actions[]`: action, accounts referenced, amount quote or "unspecified", quote. Agreed
  non-actions ("leave it as it is") are actions too (G8).
- `disposals[]`: account referenced, `full | portion | unspecified` with label evidence
- `limit_signals[]`: e.g. "already part-funded", "worried about over-contributing", quote (P4)
- `open_actions[]`: text, `blocking` (true only when the source makes it a precondition), quote (P2)
- `excluded_items[]`: `tangent | aspiration | circumstance`, text, quote (P6)
- `objectives_and_circumstances[]`: quote-backed statements for Background
- `accounts_mentioned[]`: for R1 (a new account mentioned only in the meeting is a conflict)

**Report instruction** → the table is parsed **in code** into label/value pairs; a model maps labels
to canonical fields only when a label isn't recognised (unseen instructions may rename fields).
Missing or "TBC" fields are recorded as such (P11).

**Scope mapping** (part of this stage, R8): a model maps each scope phrase in the instruction to
candidate account IDs from the account list, with a reason. Code then checks each mapping
**independently of the model**, from the phrase and the account data (in `resolve_scope`, below):
- every phrase resolves to at least one account, or to a new account the instruction creates;
- **type:** each candidate's wrapper class (§5.1) matches the type word in the phrase ("ISA", "GIA",
  "SIPP", "bond"); a phrase whose type word has no wrapper class is unresolved;
- **holders:** where the phrase names holders ("(David and Susan)"), the candidates are exactly one
  account of that type per named holder; "joint" requires a joint account;
- **platform:** where the phrase names a platform, candidates are on it;
- no account is matched by two phrases in contradictory ways.
These checks are a decision with a right answer, so they run in code in `reconcile/scope.py`
(`resolve_scope`, §5); extraction only proposes the mapping. A mapping that fails any check is never
placed in the table on the model's word alone (§5: marker row and blocking review item).

**Internal guidance** (D8) → the whole document is read, not a heading. Its input also includes the
people list (holder names from the account data, attendees from the meeting record). It returns
`HandlingDirective{sections_affected, instruction, person_name, person_evidence_quote}` for
client-specific handling only, and ignores general processing rules (those live in config). The
person is resolved by name from the evidence ("the client … her mother", with the meeting's "Jean's
mother had passed away"); code checks the name is on the people list. If the person can't be resolved,
the directive names nobody and a review item says so. The directive is in the extractor's own words;
the writer never sees the notes' text.

**General documents** are classified and then **not extracted at all** (R7). Their text is kept only
for the eval's distractor checks.

---

## 5. Reconciliation (code)

One module per concern; one function per rule, named and cited in its docstring; one or more unit tests
per rule, written first (CLAUDE.md "tests are the spec").

| Function | Implements | Notes |
|---|---|---|
| `resolve_ownership` | R1, R9 | dedupe by `account_id`; "Joint" owners = holders whose records contain the ID; ID spelling never used; co-holder missing → Owner marker |
| `resolve_scope` | R1, R2, R8 | runs the scope checks (§4.3) on the model's proposed mapping, in code, here; builds in-scope and out-of-scope sets; a new account mentioned only in the meeting record is a conflict (R1). A phrase that fails a check or matches more accounts than it names is never guessed: the table gets a **marker row** for it ("[ADVISER TO CONFIRM #n: account(s) meant by '<phrase>']") and a **blocking** review item, so G1 can't pass on a silently short table. A scope field that is missing, "TBC", or has no phrase that resolves leaves no basis for the table: the run stops (§8.4) |
| `select_values` | R3, R6, R9, P10, P12 | candidates = account data + `viewed_in_meeting` observations; latest date wins; recalled/paperwork/image values only confirm or conflict; nulls → marker (in scope) or review item (out); closed in scope → conflict; same-date disagreeing joint copies → marker; non-GBP → marker |
| `reconcile_amounts` | R4, R5 | instruction vs meeting: identical stated amount → exact one used; any difference → conflict |
| `reconcile_decisions` | R4 | compares the instruction's structured fields with the meeting's agreed actions, in code: "selling existing investments" vs the disposals found; "source of funds" vs the money items and disposals; "product recommended" vs the wrapper classes (§5.1) of the accounts the actions touch; "investment amount" via `reconcile_amounts`. Any mismatch is a conflict for the review sheet, never settled silently; a selling mismatch is G5 case b |
| `classify_money` | P5 | available = received − committed (Decimal); proceeds counted only when amount and destination known, and then rendered by code with P5's qualifiers ("gross sale proceeds of around £45,000, before any CGT and not yet realised"); a portion sold → amount marker; an unclear destination → amount marker plus a destination review item; external named as excluded; commitment without amount → available becomes a marker. A derived value is approximate if any input is, rendered with "c." and never rounded (c. £158,000 = £120,000 + c. £38,000) |
| `check_limits` | P4 | tax year from meeting date (6 April boundary); `config/tax_rules.json` keyed by tax year; trigger per P4 → marker or review note; pension contribution amounts always markers; missing year → marker |
| `decide_sections` | G5, P7, P2 | disposal from a `taxable` account, or a conflict about one → Tax section, whose fact slice holds only those disposals (a bond encashment in the same advice is never given to it); `tax_exempt` switches never; `bond` encashment → Recommendations marker; a disposal from an `unknown` wrapper → Tax section as a possible taxable disposal pending confirmation (G5 case b) plus a review item |
| `required_markers` | P2, P3, P11 | always: CGT (per taxable disposal), platform charge per platform in scope, ongoing advice charge; for each new account, its charges; unspecified amounts; request fields TBC. A new account's unstated platform is a review item, not a marker (P9) |
| `build_review_items` | P2, G15 | conflicts, superseded values, out-of-scope nulls, open actions (blocking flag), P4 notes, scope flags, currency items, unverified extractions |

Markers get stable IDs `#1…#n` in order of first appearance in the report; each maps to one review
sheet row (P1). Marker text is built in code from the ledger ("ongoing platform charge rate,
<platform>"), never by a model.

### 5.1 Wrapper classes

G5, P4, P7 and the scope checks need to know what kind of wrapper an account is, from free-text types
("Stocks & Shares ISA", "SIPP", "Offshore Investment Bond", or a new account's "joint investment
account"). `config/account_types.json` maps type wording to a class: `tax_exempt` (ISA variants,
pensions), `taxable` (GIA, investment account, direct holdings), `bond` (onshore and offshore),
`cash`, with the allowance family each belongs to (ISA, pension) for P4. The mapping is general
vocabulary, not client data. A type it doesn't recognise ("Junior ISA" if unlisted) is `unknown`:
never guessed, always a review item, and treated conservatively (a disposal from it triggers the Tax
section as pending confirmation; it gets no allowance check and says so).

### 5.2 Conflict investigation (stage 3a, D14)

Extraction reads each source in one pass. Some conflicts can only be settled, or explained, by looking
across sources for evidence that pass didn't collect. Examples from the data: which account "another
small cash account from some years ago" refers to; whether a meeting figure was viewed or recalled
("the figure on the last statement they had to hand"); a scope phrase whose check failed.

**What opens a question.** Reconciliation emits an `OpenQuestion` only where more evidence could
change the outcome **under the rules**:
- a decisive label with no verified evidence (§4.2), which would otherwise get its conservative default;
- a meeting mention of an account that maps to no account, or to several (R1, R6);
- a scope phrase that failed a check (R8);
- an instruction-vs-meeting conflict (R4, R5) or a request field marked "TBC" (P11), where the agent can
  only add context for the adviser: these stay conflicts whatever it finds.

Conflicts the rules already settle (a stale value vs a later live one under R3) open no question.

**The agent.** For each question, a bounded loop (≤6 tool calls, ≤5 questions per report, stage model
from config) with **read-only tools only**:
- `list_sources()`: roles, paragraph counts;
- `read_paragraphs(source, from, to)`;
- `find_in_source(text, source?)`;
- `get_accounts(filter)`: account data records as parsed;
- `get_ledger_entry(id)`: the current ledger fact, with provenance.

It has no tool that writes, selects a value or changes a rule. It returns
`Finding{question_id, answer: supports|contradicts|inconclusive, proposed: {label|account_id|none},
evidence: [{source, paragraph, quote}], explanation}`.

**Code decides.**
1. Every quote is verified (§4.1). A finding with no verified evidence counts as inconclusive.
2. A proposed label is accepted only as label evidence for §4.2's rule, and only if the evidence quote
   is in **the same paragraph as the fact it labels** (a quote elsewhere in the document can't label
   this observation). The rule then runs as usual.
3. A proposed account link is accepted only if code confirms it: all of §4.3's scope checks (type,
   named holders, platform, no contradictory mapping), plus status, and **exactly one account passes**.
   Where several accounts pass, the mention stays unresolved whatever the agent proposes: R8 says
   flagged, not guessed.
4. Reconciliation re-runs with the accepted evidence. Nothing the agent says reaches the report directly.
   Accepted evidence may make an outcome **less** conservative than the default (a newer value selects,
   money becomes available, a sale counts as full), because it has passed exactly the checks extraction
   must pass (D14). Every such change is marked on the review sheet as **"changed by investigation"**,
   showing the conservative default that applied, the new value, and the quote, so the adviser can see
   it was a fallback that got overridden, not an original read.
5. Every finding, accepted or not, is attached to its review item with the quotes, so the adviser sees
   the evidence ("possibly the Holloway cash account: same holder and type; balance still unknown").
6. `inconclusive`, a spent budget, a model-call failure or a rejected finding leaves the conservative
   default and the review item in place. Investigation can never make a run fail (§8.4: optional
   stage).

**Order and rounds.** Questions are taken in order of what they could change: the table and account
values first (G1, G6), then available money (G7), then disposal extent (G5, P5), then everything else;
ties by order of appearance. Beyond 5, the rest stay unresolved with their review items. Reconciliation
re-runs once after investigation; any question it newly opens is recorded unresolved, not investigated,
so there is exactly one investigation round.

**Measured, like the other model stages.** The hand-written cases include deliberately ambiguous
references and labels with expected answers. Investigation is scored on accepted-and-correct,
accepted-and-wrong and inconclusive, and is part of the Luna-vs-Sol experiment (§10.7).
**Accepted-and-wrong** (a finding code accepted that contradicts the expected facts) is the costly
error: it is a headline metric in every results file, reported on its own and not folded into general
accuracy.

---

## 6. The facts ledger

The ledger is a pydantic model, written to `outputs/<client>.ledger.json` (committed with the final
outputs: it is the traceability record, S5).

```text
Ledger
  run          client, meeting_date, tax_year, report_type, config_hash, run_id
  sources[]    id, path, role, classified_by (code|model), evidence_quote, sha256
  people[]     id, name, db_role (client|partner)
  accounts[]   id, owners[person], type, platform, status, in_scope, scope_reason,
               is_new, value: Value|null, superseded[]: Value, value_marker: marker_id|null
  money[]      id, class (received|committed|proceeds|external), amount: Value|null,
               counted: bool, reason, quote, source
  derived[]    id, formula ("received − committed"), inputs[fact_id], value: Value
  actions[]    id, description, accounts[], amount: fact_id|marker_id|null, quote, source
  excluded[]   kind (tangent|aspiration|circumstance), description, allowed_in[section], quote
  directives[] sections[], instruction, person
  sections[]   id, included: bool, rule, evidence[fact_id]
  markers[]    id (#n), key, text, reason, section, fact_ref
  review[]     id, kind, blocking: bool, detail, refs[fact_id|marker_id], findings[]
  questions[]  id, kind, subject_ref, status (resolved|unresolved), finding: Finding|null,
               accepted: bool, reason
  facts{}      fact_id → Fact

Value   amount: Decimal, currency, precision (exact|approximate), qualifier ("a little over"),
        date, source_id, quote, selected_by (rule id)
Fact    id, kind, description (no digits), render_prose ("a little over £45,000"),
        render_table ("c. £45,000"), reportable: bool, transaction: bool (a top-up, proceeds,
        new money or tax figure: never in Background, G9), role (account value | available to
        invest | sale proceeds | excluded | initial charge | …),
        placement (any|table|footnote_only|never), provenance (source, date, rule)
```

**Fact IDs** are generic and stable: `account.<id>.value`, `money.available`, `money.<id>.amount`,
`meeting.date`, `instruction.initial_charge`, `instruction.risk_profile`. They never contain a client
value (account IDs appear only in the ledger file, not in `src/` or `config/`).

**Who writes what:** stage 1 writes `sources`; stage 2 writes nothing to the ledger directly (it
produces verified raw facts, kept in the run record); stage 3 writes everything else, including open
questions; stage 3a writes nothing itself (its findings are recorded under `questions`, and whatever
code accepts re-enters only when stage 3 re-runs); stage 4 adds section inclusion and the per-section
slices; stages 5–6 write nothing (drafts live beside the ledger); stage 7 records gate and judge
results in the run summary.

**How sections get only their own facts:** each section in config declares selectors
(`"facts": ["account.*.value", "money.*"]`, `"markers": ["cgt.*"]`, `"excluded": ["aspiration"]`).
The planner resolves them against the ledger into a `SectionPlan` holding only those facts (with
descriptions and precision, never numbers), the markers for that section, the directives that name it,
and the section's spec text. The writer prompt is built only from the plan.

**Every writer input is digit-free.** Action descriptions, excluded-item descriptions, objectives and
directives come from extraction as text that may contain figures ("move £20,000 from the cash
account"). The planner rewrites each such text in code: a span matching a fact's quote becomes that
fact's token; a text with any other money or percentage (in digits or words) is withheld from the
writer, logged as a planner defect, and listed as a review item ("not used in drafting: …"). So the
writer can't copy a number it was never given, and a planner gap costs a detail, not the report.

**Facts carry the role they may be used in.** Each fact in a plan has an allowed role
(`account value`, `available to invest`, `excluded`, `sale proceeds`), and the writer prompt states it.
Where a marker governs how an amount is used, the plan gives the writer the marker for that use, not
the amount: when a P4 limit marker applies to ISA top-ups funded by sale proceeds, the proceeds fact is
offered only as "value of the sale", and the top-up amount only as the marker. External money
(contingent, not received) is offered only in the `excluded` role, and only to Recommendations. The
initial charge is offered only in the `initial charge` role and only to the charge sections, so the one
percentage the report may state can only appear in a charge context (G3). G2's role check (judge) is
the backstop, not the only guard.

**Excluded items by class (P6).** Tangents are never put in any plan, so no writer can mention them.
Aspirations are put only in Background's plan, as "not covered by this advice"; the deterministic gates
check that each aspiration's subject appears at most once and only in Background.

---

## 7. Writing, tokens and repair

### 7.1 Sections and slots

The config keeps the starter's contract (`template` with `<<slot>>`s, `use_if`, `placeholders`), with
three slot kinds:
- `generated`: written by the model from the section plan;
- `computed`: built by code (the account table and its footnote, the list of excluded money). In the
  table, a new account's Type is the report instruction's wording for it, falling back to the meeting
  record's, and its Value is "To be opened" (P9);
- static text lives in the template itself (the FCA line, the risk warning: never a slot).

Every slot, whatever its kind, is listed in `placeholders` (with `"kind"`), so the committed smoke test
(`slots == placeholder specs`) keeps checking something real. Sections stay inline in
`template_config.json`; sharing across report types is by `extends` (§11), not by section references,
so the test keeps reading a complete section list.

**Inclusion extends the contract rather than replacing it (D11).** `use_if` stays plain language, as
PROJECT_GUIDANCE describes, and a section may add an optional `predicate` naming a ledger decision:

```json
{ "id": "tax_implications",
  "use_if": "Include when the advice sells or disposes of investments that may create a taxable gain.",
  "predicate": "taxable_disposal" }
```

- **Predicate present:** inclusion is decided in code by that function, deterministically, and G5
  checks it. The shipped config sets a predicate for every conditional section.
- **No predicate:** a model decides from **ledger facts only** (never raw sources), given the plain
  `use_if` text; its answer, reasoning and the facts it used are logged in the run record and flagged
  on the review sheet ("section included by model judgement: check"). This keeps a new report type
  usable from config alone before anyone writes a predicate.
- **Unknown predicate name:** config loading fails with a clear error, never a silent fallback.

Predicates are a registry of small named functions over the ledger (`reconcile/predicates.py`).

### 7.2 Writer contract (D1)

The writer returns `{"paragraphs": [str]}`. Allowed tokens: `{fact:<id>}` and `{marker:<key>}` for
IDs in its plan. Code then checks, before substituting:
1. every token exists in the plan (no invented IDs);
2. **no digits anywhere** outside tokens (numbers in words that are money or percentages also fail;
   durations and counts in words are allowed per G2);
3. every required marker of the section appears exactly once;
4. deterministic section gates: G3, G4 (no FCA/risk-warning paraphrase outside static slots), G9
   (Background), G10 screen, G11 (no tables or headings), G12 (the slot's text fits its template
   sentence: starts lower-case when mid-sentence, no trailing full stop when the template supplies one).

A failure goes back to the writer with the exact findings (≤2 repair rounds). Substitution uses
`render_prose` for prose and `render_table` in the table; footnote-only facts are only accepted in the
computed footnote (G2). G12 runs again **after** substitution, on the filled sentence in its template,
because rendering can break grammar a token didn't (a rendered value opening a sentence, a doubled
"around around").

One writer call per generated slot (D6): isolation per section (G11), independent repair, small
prompts, and §10's "only its own facts". Cross-section consistency comes from the shared ledger, not
from one long prompt.

### 7.3 Prompts

Each prompt is a markdown file in `config/prompts/` with a fixed structure (role; inputs it receives;
numbered rules; output format; what to do when information is missing: use a marker token, never
invent). The prompt version is the sha256 of its text plus its output schema, computed automatically,
so a changed prompt can't keep an old version label. Prompts describe patterns only; no example uses a
real client value or a real client's wording. `check_repo.py` enforces names, IDs, platforms and
amounts today; the plan extends it to adviser names, fund names from general documents, and any run
of six or more words shared between a prompt and a source document in `data/` (so a prompt can't
quote "pulling it up live" from a real meeting note).

---

## 8. Validation, release and outputs

### 8.1 Gates in the pipeline

The gates live once, in `src/agent_pipeline/gates/`, and run in two modes (SCOPING §2 "two layers"):
- **pipeline mode:** truth = the ledger (the "else" column);
- **eval mode:** truth = expected facts (`eval/expected/<client>.json`).

Stage 5 runs the section-level deterministic gates on each slot. Stage 7 runs every deterministic gate
on the assembled draft: G1, G2 (list check), G3, G4 (exact match and exactly once each; fuzzy
paraphrase screen), G5, G6, G7 (deterministic part), G9 (no fact with `transaction: true` in
Background), G10 (n-gram screen), G11, G12 (after substitution), G13, G14, G15, and P6's
at-most-once check.

- **G4 paraphrase screen:** `difflib` similarity between each report sentence (outside the static slots)
  and the FCA line and risk warning. The threshold is **calibrated** on known positives (the
  paraphrased warnings in the general documents, and the G4 paraphrase mutations) and known negatives
  (every sentence of the clean reference bundles): the lowest threshold that catches every positive
  with no negative flagged. It is recorded in config with the results file that set it.
- **G10 n-gram screen:** word 6-grams shared between the report and the internal guidance, **excluding**
  any 6-gram that also occurs in the meeting record or the spec (legitimate shared facts and
  vocabulary). Anything left is a finding; the judge checks paraphrase.

### 8.2 Release judge (stage 7)

One structured call per report covering the judge parts of the hard gates:
- **G8:** for each ledger action (including agreed non-actions), is it in Recommendations (quote from
  the report)? For each recommendation in the report, which ledger action does it implement (or none)?
- **G16:** list every material claim (money, accounts, tax position, agreed actions); for each, a
  supporting source quote. **Code verifies every source quote**; a claim with no verified quote is
  unsupported. **Coverage is enforced in code:** the report is split into sentences, and every sentence
  containing a filled fact token, an account name or type, a money word or a tax term must map to at
  least one claim ID. Uncovered sentences go back to the judge once (the coverage re-ask, part of this
  call's budget); still uncovered fails the gate, so a lenient judge can't pass by listing few claims.
- **G7 (judge part):** is any contingent, committed or not-yet-received money described as available or
  allocated?
- **G12 (judge part):** does each generated slot read grammatically in its template sentence?
- G2's role check, G4 paraphrase and G10 paraphrase as findings with quotes.
- P6: is any aspiration presented as a recommendation or action?

If the judge finds a problem in one section, that section gets one repair round with the finding,
then the gates and judge re-run once. Otherwise the run is a failed generation.

### 8.3 Release states (SCOPING §2)

| State | Written | Meaning |
|---|---|---|
| Draft for adviser review | `outputs/<client>.md`, `.review.md`, `.ledger.json`, `.run.json` | every hard gate passed; markers and blocking items may remain; any previous `outputs/<client>.failed.md` is removed |
| Failed generation | `outputs/<client>.failed.md` (banner "NOT ISSUED", the reason, and the draft and failing gates with offending text where a draft exists), `.review.md` (status FAILED, with whatever review items exist), `.run.json`, and `.ledger.json` only if reconciliation ran. An input stop before stage 3 writes the reason and the classification result, with no draft and no ledger | a hard gate failed or a stop condition hit (§8.4); any previous `outputs/<client>.md` is removed so a stale draft can't be mistaken for this run's |

The pipeline never marks anything client-ready (SCOPING §2).

### 8.4 Failure policy: stop only where continuing is unsafe (D13, D16)

A missing or odd input degrades the draft (a marker, a review item, a conservative default) unless
continuing would put an unsafe draft in front of an adviser. Only these stop the run, as a failed
generation with the reason (no draft is issued):

| Stops the run | Why continuing is unsafe |
|---|---|
| No readable account data (not JSON, or no holders) | no basis for which accounts exist or who owns them |
| No report instruction, or two that disagree; or an instruction whose scope field is missing, "TBC", or has no phrase that resolves | no basis for scope, so the table can't be built (P11's marker rule doesn't apply to scope) |
| Two account data sources that disagree | no basis for which accounts exist or who owns them |
| No meeting record | no record of what the client agreed, so there is nothing to recommend |
| A hard gate still failing after its repair rounds | the draft is wrong in a way SCOPING forbids issuing |
| A model call that still fails (after API retries, or after its one schema re-ask) in a **required** stage: classifying the three required sources, meeting or instruction extraction, writing, the release judge; or the runaway-cost guard | the run is incomplete |

The same failure in an **optional** stage degrades instead: an image read is skipped (review note), a
guidance read yields no directive (review item), an investigation question stays unresolved, a scope
proposal counts as unresolved (marker row), a no-predicate inclusion decision falls back to including
the section with a blocking review item.

Everything else degrades and continues:

| Input problem | Handling |
|---|---|
| Unknown fields in any source | ignored and logged |
| Optional account fields missing (platform, currency, value, valuation date) | handled by the rules: marker or review item (R6, P12, charges marker) |
| An account missing an identifying field | set aside with a review item; a conflict if in scope |
| Meeting date not parseable | undated for R3/R10; metadata date used only for the P4 tax year (§4.1); review item |
| Unknown document | excluded and logged (§3.2) |
| Statement image unreadable or not a statement | ignored with a review note (images never select values) |
| A fact whose quote or label can't be verified | dropped or conservative default (§4.1–4.2); review item |
| Unrecognised account type | `unknown` wrapper class, conservative handling (§5.1); review item |
| Request field missing or "TBC" (other than scope) | marker (P11) |
| One scope phrase unresolved or ambiguous | marker row in the table and a blocking review item (§5) |
| Planner finds a figure in a writer input | text withheld from the writer; review item (§6) |
| Guidance person can't be resolved | directive names nobody; review item (§4.3) |

Every degradation is visible on the review sheet, so "the run finished" never hides "the run guessed".
Degradation is also measured (§10.4), per client group (the four real clients, hand-written,
synthetic), with three numbers that only make sense together:
- **issued rate** = drafts issued ÷ clients whose expected state is "draft". Cases built to fail are
  excluded from the denominator, so the rate measures unnecessary failures;
- **release-state match rate** = clients whose release state equals the expected one ÷ all clients.
  This is where a case built to fail must fail;
- **wrongly issued** = the **count** of clients whose draft passed every pipeline-mode gate but fails any
  hard gate in eval mode (against expected facts). This is the safety number: it should be zero, and
  a higher issued rate never excuses a non-zero one.

### 8.5 The review sheet (`outputs/<client>.review.md`)

Built in code from the ledger. Sections, in order:
1. **Status:** release state, run ID, date, cache replay vs live, gate summary.
2. **Blocking before sign-off:** blocking open actions (e.g. an unconfirmed cash account).
3. **Markers to fill:** `#n`, what is needed, why (the rule), section.
4. **Conflicts and how they were resolved:** both values, both sources and dates, the winning rule,
   and any investigation finding with its quotes and whether code accepted it. A finding that changed
   an outcome is labelled **"changed by investigation"** and shows the default it replaced, the new
   value and the quote.
5. **Superseded values:** value, date, source, replaced by.
6. **Accounts left out:** each account not in the table and why (out of scope, closed, no value).
7. **Section decisions:** each conditional section, included or omitted, with evidence (§8 of SCOPING).
8. **Notes:** P4 notes, scope flags, currency items, image discrepancies, unverified extractions.
9. **How this draft degraded:** every fallback and conservative default the run applied (§8.4), e.g.
   "meeting date taken from document metadata", "basis unverified: treated as recalled".

### 8.6 Run summary (`outputs/<client>.run.json`, printed at the end of every run)

Per stage: calls, **cache hits vs live calls**, tokens (input/cached/output/reasoning), cost, latency,
model and prompt versions; gate results; release state. The console line always says, e.g.,
`14 calls: 14 replayed from cache, 0 live, $0.0000`, so a replay is never mistaken for generation.

**Per-stage inputs and outputs** (SCOPING §8) are recorded for every run in `runs/<run_id>/`: each code
stage's output as JSON (classification, verified extraction, ledger, section plans, slot drafts before
and after substitution, gate results), and each model call's full request and response by reference to
its cache entry. `runs/` is gitignored for development runs; the final submission run's folder for each
client is copied to `outputs/<client>.run/` and committed, so the evidence behind the committed outputs
is inspectable.

---

## 9. The LLM client (`src/agent_pipeline/llm.py`)

The only module that imports `openai` (enforced by a `check_repo.py` rule).

```python
class LLMClient:
    def structured(
        self,
        *,
        stage: str,
        prompt: Prompt,
        inputs: Mapping[str, object],
        schema: type[T],
        images: Sequence[ImageInput] = (),
        tools: Sequence[Tool] = (),
    ) -> LLMResult[T]: ...
```

- **API:** Responses API `responses.parse(..., text_format=schema)` (openai 2.38 installed). Settings
  come from the stage's config: model, `reasoning_effort`, max output tokens, and `temperature: 0`
  only where the model accepts it (checked once per model at implementation; S4).
- **Cache (D3):** key = sha256 of the canonical JSON of {model, stage settings, prompt text, schema
  JSON, rendered inputs, image sha256s, tool definitions}. Any change to model, prompt, schema, the
  stage's config or inputs is a miss, never a stale hit (S4). The key never includes absolute paths,
  run IDs, timestamps or the checkout location (sources are identified by content hash and path
  relative to the client folder), so a reviewer's fresh clone hits the same entries. Entries are committed JSON files under
  `cache/llm/<aa>/<key>.json` holding the stage, model, prompt version, input hash, the response,
  usage and cost; no keys, no headers. `--fresh` bypasses reads and rewrites entries.
- **Retries:** transient errors (429, 5xx, timeouts, connection) retry with exponential backoff and
  jitter, honouring `Retry-After`, up to 4 attempts. A schema-validation failure gets one re-ask with
  the validation error. A refusal or empty output raises (as `generate.py` does now), never returns "".
- **Cost:** price table in `config/models.json` (source URL and retrieval date recorded); cost per call
  from usage, including cached-input and reasoning tokens.
- **Cost reporting, not a cap (D12):** every run records its cost per stage and per report.
  `--estimate` prints uncached calls and an estimated cost without calling the API, run before any
  live batch. A per-run ceiling in config (default well above a normal report) stops a runaway loop;
  it is a fault guard, not a budget.
- **Trace:** every call appends one JSON line to `runs/<run_id>/trace.jsonl` (gitignored): stage,
  model, prompt version, cache hit, tokens, cost, latency, attempt count, outcome. The run summary is
  derived from it.

---

## 10. The eval

`src/report_eval/`, CLI `uv run python -m report_eval.run [--clients all] [--judge] [--fresh]`.

### 10.1 Expected facts

`eval/expected/<client>.json`, one per client, outside `src/` and `config/` (they hold client values).
Schema mirrors SCOPING §7: table rows, not-in-table accounts, reportable figures (with placement and
optional flags), markers (with acceptable alternatives), review items, section inclusion, actions,
excluded items, must-not-appear strings, the **expected release state** (draft or failed generation,
with the reason), plus **extraction expectations** (value observations with basis, money items with
class, disposals, open actions with blocking flag, each with its label) and **investigation
expectations** (for each question the case is built to raise, the right answer, or "should stay
unresolved"), so these stages can be scored on their own (§10.7).

**Build order (SCOPING §9):** the expected facts for the four clients (from SCOPING §7) **and** the
hand-written cases (§10.6) come first, before any pipeline stage is built, because they measure
correctness from the start. The generator (§10.8) follows.

### 10.2 Gates

The same gate functions as the pipeline (§8.1), in eval mode. Each result records pass/fail and the
offending text. Deterministic gates run offline on existing outputs at no cost.

### 10.3 Judge rubric (eval, gpt-6-sol)

One structured call per report per criterion group. Q1 per section against the spec text; Q2 claim by
claim; Q3 per directive; Q4; Q5 per marker; Q6 judge part only where expected facts are missing. Each
criterion scores 1–5 against written anchors (5 = "no issue"; 3 = "minor, a reader would not be
misled"; 1 = "wrong or misleading"), with report quotes as evidence; source quotes are verified in
code. The judge parts of the hard gates (G7, G8, G12, G16, and G2's role check) are also re-scored by
the eval judge against expected facts.

### 10.4 Results files

`eval/results/<UTC-timestamp>_<short-sha>[-dirty].json`, committed: commit, dirty flag, config hash,
prompt versions, models per stage, per-client per-gate results with offending text, extraction scores,
investigation scores with **accepted-and-wrong as its own headline figure**, Q scores, tokens, cost,
cost per report, cache hits vs live, and, separately for
each client group, the **issued rate**, the **release-state match rate** and the **wrongly issued** count
(§8.4). `scripts/progression.py` builds the baseline-to-final table
from these files; no metric is typed by hand.

### 10.5 Broken-report tests (every gate)

`tests/test_gate_mutations.py`. A **reference bundle** per client (report, review sheet, ledger) is
built offline from its expected facts by a deterministic stub writer, and must pass every gate. Each
mutation breaks one thing and asserts that **at least the intended gate fails**. Several mutations
legitimately trip more than one gate (a CGT amount fails G2 and G3; a second table fails G1 and G11),
and requiring exactly one would push toward weakening gates. The clean bundle passing every gate is
what shows the gates don't over-fire.

| Gate | Mutation |
|---|---|
| G1 | add an out-of-scope account; list a joint account twice; show "Joint" as owner; drop an in-scope row |
| G2 | insert a distractor figure; a superseded value outside the footnote; "£45k"; a figure in words |
| G3 | insert a CGT amount, a CGT rate, a platform charge rate |
| G4 | remove the risk warning; duplicate the FCA line; add a paraphrased warning |
| G5 | drop the Tax section when required; add it when not |
| G6 | swap a selected value for the superseded one; drop "c." from an approximate value |
| G7 | allocate the contingent amount; treat received as available without subtracting committed |
| G8 | drop an agreed action (judge); action an aspiration (judge) |
| G9 | put a transaction amount in Background |
| G10 | paste a sentence of internal guidance |
| G11 | add a second table; move the risk warning into Recommendations |
| G12 | start a slot with a capitalised full sentence mid-sentence; double full stop |
| G13 | change the risk-profile label; misspell a name; new account without "To be opened" |
| G14 | remove a required marker; add a marker for a settled value |
| G15 | drop a conflict row; drop a blocking flag; marker without a review row |
| G16 | add an unsupported claim about the client's tax position (judge) |

Deterministic mutations run offline in every `pytest`. Judge mutations (G7 and G12 judge parts, both G8
mutations, G16, G2 role, G4 and G10 paraphrase) are recorded once live and then replay from the
committed cache, so they also run offline.

### 10.6 Hand-written cases

`data/synthetic/handwritten/<case>/` with `eval/expected/<case>.json`, each small (two or three
accounts) and aimed at one rule the scoping is least sure of. 20 cases, one rule each:

| # | Case | Rule | Expected state |
|---|---|---|---|
| 1 | statement image dated after the account data, disagreeing | R3, P10 | draft |
| 2 | meeting figure recalled, not viewed | R3, §4.2 | draft |
| 3 | joint-account copies with different values and dates | R9 | draft |
| 4 | joint-account copies with different values on the same date | R9 | draft |
| 5 | in-scope account closed | R6 | draft |
| 6 | in-scope account with no value | R6 | draft |
| 7 | instruction says nothing is sold, meeting records a sale | R4, G5b | draft |
| 8 | exact instruction amount vs a different approximate meeting amount | R5 | draft |
| 9 | a commitment with no amount | P5 | draft |
| 10 | bond encashment plus an ISA fund switch | G5, P7 | draft |
| 11 | one scope phrase that resolves to nothing | R8 | draft (marker row, blocking item) |
| 12 | a non-GBP account in scope | P12 | draft |
| 13 | an initial-charge field marked "TBC" | P11 | draft |
| 14 | two meeting records, the later one changing a decision | R10 | draft |
| 15 | renamed files plus an extra unknown document | §3.2 | draft |
| 16 | an ambiguous account mention the investigation can link (one candidate) | §5.2 | draft |
| 17 | an ambiguous account mention with two candidates (must stay unresolved) | §5.2, R8 | draft |
| 18 | an undated meeting record and missing optional account fields | §4.1, §8.4 | draft |
| 19 | two report instructions that disagree | §8.4, D16 | failed generation |
| 20 | an instruction whose scope field is "TBC" | §8.4, D16 | failed generation |

### 10.7 Model selection by measurement (D2)

`report_eval.run --stage-models extract=gpt-6-sol,release_judge=gpt-6-sol` runs any stage on another
model through the config override. The protocol, once the four clients and hand-written cases have
expected facts:
1. **Extraction:** run on Luna and on Sol; score both against the extraction expectations (per
   category precision and recall, and **per label**: basis, money class, blocking, disposal extent,
   tangent vs aspiration). Upgrade to Sol only if Luna misses a fact or mislabels one that Sol gets
   right, or produces a wrong fact Sol doesn't, on any case.
2. **Release judge:** run on Luna and on Sol over the clean reference bundles and the judge mutations.
   Upgrade only if Luna misses a mutation Sol catches, or raises more false alarms on clean reports.
3. **Investigation:** run on Luna and on Sol over the hand-written cases that raise questions. Upgrade
   only if Luna has an accepted-and-wrong finding Sol doesn't, or leaves unresolved a question Sol
   answers correctly.
4. Record the outcome with `/decision`, citing both results files and each option's cost per report.

Estimated cost: Sol extraction 24 × ≈$0.08 ≈ $1.92; Sol release judge on 24 clean bundles and ≈12
judge mutations, 36 × ≈$0.06 ≈ $2.16; Sol investigation on the ≈5 question-raising cases at ≈$0.06 per
question ≈ $0.30; the Luna side ≈$0.20. About $4.60 in all (§10.9).

The G16 judge is also **calibrated against the hand-written cases** (SCOPING G16): each case's
expected facts list the material claims a correct report makes, and a judge that marks a supported
claim unsupported, or misses an unsupported one planted by a mutation, counts against it here.

### 10.8 Synthetic clients (D4)

`src/report_eval/synth/`: a seeded scenario sampler varies the SCOPING §5 patterns (names, account
mixes, joint accounts, stale dates, nulls, closed accounts, out-of-scope accounts, new accounts,
received/committed/contingent money, limit breaches, distractors, tangents and aspirations, handling
notes). From the scenario, code writes the account JSON, the report-instruction table (python-docx)
and the statement image (Pillow), and derives `eval/expected/<id>.json`. An LLM writes the meeting
note and general document prose around **required phrases**; code checks every required quote appears
verbatim and no unplanned figure appears, and rejects the file otherwise. Generated once and committed
under `data/synthetic/generated/<id>/`, never regenerated per run. ≈20 clients, ≈$0.01 each, one-off.

**Where the required phrases come from:** a phrase bank written for the generator, with several
wordings per pattern (a live viewing, a recalled figure, a commitment, a contingency, a precondition),
none copied from the four clients. The same six-word overlap check as for prompts (§7.3) runs between
the phrase bank and `data/`'s real documents, so the synthetic clients don't just re-test the real
clients' wording. Name and figure pools are sampled, so generator code holds no fixed client values.

The generator encodes the same rules the pipeline implements, so it catches implementation errors,
not rule errors; the hand-written cases cover the rules (SCOPING §9).

### 10.9 Cost (D12)

There is no budget cap: development and eval runs are funded separately, and **cost is a reported
metric instead**. Every run records its cost per stage; every results file records the run's total and
cost per report; the progression table (§10.4) reports cost per report alongside correctness. The
design constraint that remains is the **default pipeline's** cost: Luna in every stage unless the
experiment proves a stage needs Sol, and the committed cache, so a reviewer's re-run costs cents (a
replay costs nothing; `--fresh` about a cent per report on Luna).

Pre-build estimates of the development spend, for planning only (measured spend replaces them):

| Item | Basis | Est. |
|---|---|---|
| Development pipeline passes (Luna) | 24 cases (4 real + 20 hand-written) × ≈$0.011, ≈10 uncached passes over the build | ≈$2.65 |
| Eval judge (Sol) during development | 24 cases × ≈$0.07, ≈2 full passes (changed cases only in between) | ≈$3.35 |
| Model-selection experiment (§10.7) | Sol extraction ≈$1.92 + Sol release judge ≈$2.16 + Sol investigation ≈$0.30 + Luna side ≈$0.20 | ≈$4.60 |
| Judge mutations recorded once | ≈12 mutated bundles × Luna judge | ≈$0.05 |
| Synthetic clients | generation ≈$0.20 + ≈2 pipeline passes over 20 clients at ≈$0.22 per pass | ≈$0.60 |
| Final `--fresh` run (D3) | 44 × ≈$0.011 pipeline + eval judge on 24 × ≈$0.07 | ≈$2.15 |
| **Total with Luna in the pipeline** | | **≈$13.40** |

If the experiment moves extraction and the release judge to Sol (≈$0.144 per report), each later
pipeline pass costs about 13× more, and so does a reviewer's `--fresh` run; the upgrade decision
records that cost next to the accuracy it buys. This design's own working rules (not a CLAUDE.md
rule since the budget line was removed): every live batch prints its estimate first (`--estimate`)
and asks before spending, as the `run-eval` skill also requires; cached reruns are free, so iteration
costs follow prompt changes, not reruns.

---

## 11. Config: prompts as code, several report types

```
config/
  base.json                shared: global instructions, marker format, static texts, stage models,
                           and the shared sections (introduction, fees & charges, conclusion…)
  template_config.json     investment advice report: "extends": "base.json"; its own sections inline
  prompts/*.md             one file per prompt; version = content hash
  models.json              price table (source URL, retrieval date)
  tax_rules.json           P4 reference figures keyed by tax year (source and date per entry)
  account_types.json       type wording → wrapper class and allowance family (§5.1)
```

- **Report types without duplication:** a report config `extends` a base. Resolution merges sections
  by `id`: a report can take a base section as is, override fields of it (title, selectors, prompt), or
  add its own. The resolved config is a complete inline section list, which is what the committed smoke
  test reads. A second report type (e.g. an annual review) is one new file (S6), plus a predicate
  function only if it needs a new kind of inclusion condition (§7.1).
- **Stage models:** `base.json` holds `"stages": {"extract": {"model": "gpt-6-luna",
  "reasoning_effort": "medium"}, …}`; a report config or the CLI can override per stage (D2).
- `tax_rules.json` holds a figure that also occurs in `data/` (the ISA allowance), so `check_repo.py`
  would flag it. The plan makes the allowlist **file-scoped** (`config/tax_rules.json: 20000  # ISA
  allowance, a general rule`), so the exemption doesn't also allow that amount everywhere else in
  `src/` and `config/`.

---

## 12. Code map (proposed)

```
src/agent_pipeline/
  generate.py            CLI; builds the run and calls pipeline.run
  pipeline.py            stage graph and run context
  llm.py, cache.py       the one LLM client; the response cache
  config.py              load, extends, prompt loading and hashing
  sources/               classify.py; adapters/{json_accounts,docx,markdown,image}.py
  extract/               schemas.py; meeting.py; instruction.py; guidance.py; image.py; quotes.py
  ledger.py              ledger models; rendering (prose/table)
  reconcile/             ownership.py; scope.py; wrappers.py; values.py; amounts.py; money.py;
                         limits.py; sections.py; predicates.py; markers.py; review.py; questions.py
  investigate/           agent.py (bounded loop); tools.py (read-only); accept.py (verification)
  write/                 plan.py (incl. digit-free input rewriting); writer.py; tokens.py; table.py
  gates/                 deterministic.py; judge.py; release.py
  assemble.py            outputs, review sheet, run summary
src/report_eval/         run.py; expected.py; extraction_score.py; judge_rubric.py; results.py;
                         mutations.py; synth/
src/document_formatter/  unchanged (formatting.py protected)
eval/expected/, eval/results/, cache/llm/, data/synthetic/{handwritten,generated}/
```

---

## 13. Testing strategy

- **Unit tests first** for every deterministic piece: adapters, quote verification and amount parsing,
  each reconcile rule (named after the rule: `test_r3_recalled_value_never_selects`), money arithmetic,
  marker numbering, table and footnote rendering, token substitution, each gate.
- **Mutation tests** for every gate (§10.5).
- **Contract tests** for prompts: each prompt file has the required headings; every config slot has a
  prompt; no prompt contains a client value.
- **Offline always:** `pytest` never calls the API; the LLM client is replaced by a cache-only fake in
  tests. Live tests sit behind `-m live`.

---

## 14. Dependencies (to add in the plan)

- `pydantic` (already installed via `openai`): declared explicitly, as ledger and schemas depend on it.
- `Pillow` (eval extra only): rendering statement images for synthetic clients.
No others: fuzzy matching uses `difflib`; config stays JSON (no YAML dependency). `pyproject.toml`'s
hatch `packages` list gains `src/report_eval`.

---

## 15. Engineering rules for CLAUDE.md

1. **A model never types a figure.** Writer output containing a digit fails validation; figures reach
   prose only as `{fact:…}` tokens filled from the ledger, and markers only as `{marker:…}` tokens.
2. **Every extracted fact is quote-anchored.** Code verifies the quote is in the source and parses the
   number from the quote; a number the model typed in a field is never used.
3. **One door to the API.** All model calls go through `llm.LLMClient` with a stage name, a prompt file
   and a pydantic schema; `openai` is imported nowhere else (`check_repo.py`).
4. **One home per rule.** Each trust rule and policy is one function in `reconcile/`, cited in its
   docstring (R3, P5) and tested by name; prompts never restate trust rules.
5. **Every gate has a mutation test, and truth lives only in `eval/expected/`.** No gate, fixture or
   expected fact is edited to make a result pass.

---

## 16. Open points raised against SCOPING (not edited)

1. This design is built against `SCOPING.md` as of commit `0e4468c`.
2. `check_repo.py` builds its denylist from top-level client folders only, so synthetic client values
   under `data/synthetic/` are not denied in `src/`/`config/`. A plain recursion would clash with the
   generator: its sampled name pools in `src/report_eval/synth/` would be denied by the clients they
   produced, and sampled round amounts would clash with ordinary config numbers. The plan instead
   extends the check to synthetic **names and account IDs only**, applied to `config/` and
   `src/agent_pipeline/` (where overfitting matters) and not to `src/report_eval/synth/`.
3. `temperature` support is undocumented for gpt-6 models. If unsupported, S4 reproducibility rests on
   the committed cache, which the run summary makes visible.
4. G8 "every agreed action appears in Recommendations" includes agreed non-actions (client 04: leave the
   offshore bond as it is). The expected-facts files list them as actions so the gate checks them.
5. **Budget and CLAUDE.md:** the $10 cap is replaced by cost reporting (D12). The CLAUDE.md edit that
   removed it also removed "Offline tests never call the API", "Cache LLM calls" and "estimate cost
   before any live batch run". This design still relies on all three (§9, §13, D3); they now live only
   here, in ARCHITECTURE's invariants and in the `run-eval` skill (which still says "$10 budget").
   CLAUDE.md's "Don't edit `data/`" also has no `data/synthetic/` exception, which §10.6 and §10.8 need
   (the guard hook already allows it). Both are for the user to settle in CLAUDE.md.
6. **Committed cache vs "we will re-run the generation ourselves"** (PROJECT_GUIDANCE): D3 makes a
   reviewer's default run a replay. The run summary says so on every run and the README explains
   `--fresh`; the user accepted this with those conditions.
7. **Build order vs the first milestone (resolved):** SCOPING §9 puts the four clients' expected facts
   and the hand-written cases first. The delivery sequence (§17) does that (M0a), then builds the
   deterministic core tests-first (M0b), and only then the client 01 slice (M1). The rules the
   hand-written cases target are exercised by unit tests from M0b and end to end from M2 (D15).

---

## 17. Delivery sequence (D15)

The implementation plan follows this order. Each milestone ends with the quality gate green, a verifier
pass, and (from M1 on) an eval results file committed.

**M0a. Truth first (SCOPING §9 build order).** The expected-facts schema; expected facts for all four
clients from SCOPING §7; the hand-written case folders and their expected facts (§10.6). No pipeline
code. This keeps SCOPING §9's order: correctness is defined before anything is built.

**M0b. Deterministic core, tests first.** Amount and date parsing, quote verification, label-evidence
checks, the ledger models and rendering, and the reconcile rules as pure functions, each with its
failing test written first. The hand-written cases' structured inputs drive the rule tests.

**M1. Thin vertical slice: client 01 correct end to end.** Every stage exists in its real shape, with
only what client 01 needs:
- the LLM client (structured outputs, committed cache, retries, cost, trace), the account-data, docx
  and markdown adapters, classification;
- meeting and instruction extraction with quote, date and label verification, and scope mapping with
  its code checks;
- wiring the M0b rules into the stage graph (all rules exist from M0b; client 01 exercises R1, R2, R3,
  R6, P2, P3, P4's full-allowance review note, P5's transfer from cash, P9 and P11);
- planning with digit-free inputs, the writer with tokens and repair, the table and footnote;
- every deterministic gate that applies to client 01, the release judge, the failure policy (§8.4),
  outputs, the review sheet and the run summary;
- the eval runner in eval mode for client 01, deterministic gates and the Sol judge.

Done when client 01 passes every hard gate against its expected facts, the run summary shows its cost
and cache use, and a replay from the committed cache reproduces it at no cost. Not in M1: images,
guidance directives, investigation, synthetic clients.

**M2. Widen to clients 02–04 and the hand-written cases** (their expected facts exist from M0a): the
extraction and planning paths the slice didn't need (disposals, money classes, excluded items,
several meeting records); images; guidance directives; the conflict investigation agent (§5.2); every
gate with its mutation tests; the issued-rate and release-state metrics on the hand-written cases.

**M3. Model selection by measurement** (§10.7), recorded as a decision with its results files and costs.

**M4. Synthetic clients** (§10.8): the generator, ≈20 frozen clients, and the issued-rate and
release-state metrics extended to them.

**M5. Hardening and submission.** The `check_repo.py` extensions (§7.3, §11, §16), the README (committed
cache, `--fresh`), the final `--fresh` run on all clients, the progression table from results files, and
the DECISIONS summary.
