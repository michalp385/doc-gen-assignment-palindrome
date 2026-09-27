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
   with a unit test. Models do three narrow jobs: read unstructured sources into typed facts, write
   prose around those facts, and judge prose that code cannot judge.
2. **A model never types a figure.** Extraction returns a verbatim quote and code parses the number
   from it. The writer sees fact IDs, never numbers, and writes tokens that code fills from the ledger
   (D1). A digit in writer output is a validation failure.
3. **One ledger, one truth per run.** Every stage writes to a typed facts ledger. The table, the
   tokens, the markers, the review sheet and the production gates all read from it, so the report
   cannot contradict itself (the baseline's client 03 GIA contradiction becomes impossible).
4. **Bounded loops, never unbounded agents** (D5). A model can retry against a code check a fixed
   number of times; hitting the limit is a failed generation, never a guess.
5. **Generic by construction.** No client value in `src/` or `config/` (`check_repo.py`). Prompts
   describe patterns, and the eval scores unseen clients (hand-written and synthetic).

---

## 2. The pipeline

```
client folder
   │
   ▼
[1] classify ────────── code (schema checks) + model (text documents)       → sources[]
   │
   ▼
[2] extract ⟲ verify ── model per source role, quote check in code (≤3)     → raw facts
   │
   ▼
[3] reconcile ───────── code: R1–R10, P2–P12                                → ledger
   │
   ▼
[4] plan ────────────── code: section inclusion, fact slices, table, markers → section plans
   │
   ▼
[5] write ⟲ repair ──── model per section, deterministic gates in code (≤2) → section drafts
   │
   ▼
[6] release judge ───── model: G8 actions, G16 claims (quotes verified)     → verdicts
   │
   ▼
[7] assemble ────────── code: tokens filled, formatting.py, review sheet    → outputs + run summary
```

| # | Stage | Code or model | Model (default, config) | Calls per report | Est. cost (Luna) |
|---|---|---|---|---|---|
| 1 | Classify | Code for JSON and images; model for text documents | gpt-6-luna, reasoning `none` | 1 per text document (≈5) | ≈$0.001 |
| 2 | Extract | Model + code verification loop | gpt-6-luna, reasoning `medium` | meeting 1–3, instruction 1, guidance 1, image 0–1 | ≈$0.004 |
| 3 | Reconcile | Code | none | 0 | 0 |
| 4 | Plan | Code | none | 0 | 0 |
| 5 | Write | Model + code gates loop | gpt-6-luna, reasoning `low` | 1 per generated slot (≈5), +repairs | ≈$0.003 |
| 6 | Release judge | Model, quotes verified in code | gpt-6-luna, reasoning `high` | 1 | ≈$0.003 |
| 7 | Assemble | Code | none | 0 | 0 |
| | **Total** | | | ≈15 | **≈$0.01** |

Prices per 1M tokens (input / output): gpt-6-luna $0.10 / $0.50; gpt-6-sol $2.00 / $10.00. With Sol for
extraction and the release judge the estimate is ≈$0.12 per report. The eval judge (Sol) adds ≈$0.07
per scored report.

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
   `account_data`; an image file is a `statement_image` candidate (confirmed by the image adapter
   finding an account-value table; otherwise `unknown`).
2. **Model (text documents):** each document's first ≈2,000 characters go to a classifier with a
   structured output `{role, evidence_quote, confidence}`. Code verifies the evidence quote is in the
   document. The prompt defines each role by its function ("addressed to all clients of a platform, not
   one client" → general document), never by file name.
3. **Consistency rules (code):** exactly one account data source and at least one report instruction
   and meeting record are required, or the run fails with a clear error. Several meeting records are
   allowed (R10); the latest-dated one governs decisions.

Alternatives: filename mapping (breaks on renamed files); pure heuristics on content (brittle on unseen
phrasing). The model costs ≈$0.001 per report.

### 3.3 Adapters

One adapter per **format**, one extractor per **role** (S6: a new source type is one new adapter or
extractor, registered in one table).

| Adapter | Reads | Produces |
|---|---|---|
| `json_accounts` | account data JSON | typed `AccountRecord`s per holder (pydantic; schema errors fail the run) |
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
2. **parses the amount from the quote itself** (`£45,000`, `GBP 120,000`, `£1.2m`, `up to £400,000`)
   and the qualifier (`around`, `a little over`, `up to`), ignoring any number the model put in a field;
3. rejects facts whose quote fails either check.

Rejections go back to the model in the verification loop (≤3 rounds) with the exact failure ("quote
not found in paragraph p12"). The model may call one tool, `find_in_source(text) → matching
paragraphs`, to locate wording. Facts still failing after three rounds are dropped and become review
items ("could not verify: …"), never report facts.

### 4.2 Extractors and schemas (abridged; full schemas in `extract/schemas.py`)

**Meeting record** → `MeetingExtraction`:
- `meeting_date`, `attendees` (names as written)
- `value_observations[]`: account reference as written, amount quote, `basis`:
  `viewed_in_meeting | recalled | from_paperwork | confirmed_unchanged` (R3 needs the distinction), quote
- `money_items[]`: `received | committed | proceeds | external`, amount quote or none, what it is for, quote (P5)
- `agreed_actions[]`: action, accounts referenced, amount quote or "unspecified", quote
- `disposals[]`: account referenced, `full | portion | unspecified`, quote
- `limit_signals[]`: e.g. "already part-funded", "worried about over-contributing", quote (P4)
- `open_actions[]`: text, `blocking` (true only when the source makes it a precondition), quote (P2)
- `excluded_items[]`: `tangent | aspiration | circumstance`, text, quote (P6)
- `objectives_and_circumstances[]`: quote-backed statements for Background
- `accounts_mentioned[]`: for R1 (a new account mentioned only in the meeting is a conflict)

**Report instruction** → the table is parsed **in code** into label/value pairs; a model maps labels
to canonical fields only when a label isn't recognised (unseen instructions may rename fields). Scope
phrases go to a small scope-resolution call (§5, R8). Missing or "TBC" fields are recorded as such
(P11).

**Internal guidance** → only the "This client" section (heading split in code) is read, into
`HandlingDirective{sections_affected, instruction, subject_person_name}` (D8). The directive is
written in the extractor's own words and names the person by name (P8). The writer never sees fde text.

**General documents** are classified and then **not extracted at all** (R7). Their text is kept only
for the eval's distractor checks.

---

## 5. Reconciliation (code)

One module per concern; one function per rule, named and cited in its docstring; one or more unit tests
per rule, written first (CLAUDE.md "tests are the spec").

| Function | Implements | Notes |
|---|---|---|
| `resolve_ownership` | R1, R9 | dedupe by `account_id`; "Joint" owners = holders whose records contain the ID; ID spelling never used; co-holder missing → Owner marker |
| `resolve_scope` | R2, R8 | model maps each instruction phrase to candidate account IDs (structured, with reasons); **code** checks every phrase resolves, counts match the phrase (plural/named holders), new accounts are in the instruction; any failure → review flag, never a guess |
| `select_values` | R3, R6, R9, P10, P12 | candidates = account data + `viewed_in_meeting` observations; latest date wins; recalled/paperwork/image values only confirm or conflict; nulls → marker (in scope) or review item (out); closed in scope → conflict; same-date disagreeing joint copies → marker; non-GBP → marker |
| `reconcile_amounts` | R4, R5 | instruction vs meeting: identical stated amount → exact one used; any difference → conflict |
| `classify_money` | P5 | available = received − committed (Decimal); proceeds counted only when amount and destination known; external named as excluded; commitment without amount → available becomes a marker |
| `check_limits` | P4 | tax year from meeting date (6 April boundary); `config/tax_rules.json` keyed by tax year; trigger per P4 → marker or review note; pension contribution amounts always markers; missing year → marker |
| `decide_sections` | G5, P7, P2 | taxable disposal / conflicting disposal → Tax section; ISA/SIPP switches never; bond encashment → Recommendations marker |
| `required_markers` | P2, P3, P11 | always: CGT (per taxable disposal), platform charge per platform in scope, ongoing advice charge; unspecified amounts; request fields TBC |
| `build_review_items` | P2, G15 | conflicts, superseded values, out-of-scope nulls, open actions (blocking flag), P4 notes, scope flags, currency items, unverified extractions |

Markers get stable IDs `#1…#n` in order of first appearance in the report; each maps to one review
sheet row (P1). Marker text is built in code from the ledger ("ongoing platform charge rate,
<platform>"), never by a model.

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
  review[]     id, kind, blocking: bool, detail, refs[fact_id|marker_id]
  facts{}      fact_id → Fact

Value   amount: Decimal, currency, precision (exact|approximate), qualifier ("a little over"),
        date, source_id, quote, selected_by (rule id)
Fact    id, kind, description (no digits), render_prose ("a little over £45,000"),
        render_table ("c. £45,000"), reportable: bool,
        placement (any|table|footnote_only|never), provenance (source, date, rule)
```

**Fact IDs** are generic and stable: `account.<id>.value`, `money.available`, `money.<id>.amount`,
`meeting.date`, `instruction.initial_charge`, `instruction.risk_profile`. They never contain a client
value (account IDs appear only in the ledger file, not in `src/` or `config/`).

**Who writes what:** stage 1 writes `sources`; stage 2 writes nothing to the ledger directly (it
produces verified raw facts); stage 3 writes everything else; stage 4 adds section inclusion and the
per-section slices; stage 5 writes nothing (drafts live beside the ledger); stage 6 appends judge
verdicts to the run summary.

**How sections get only their own facts:** each section in config declares selectors
(`"facts": ["account.*.value", "money.*"]`, `"markers": ["cgt.*"]`, `"excluded": ["aspiration"]`).
The planner resolves them against the ledger into a `SectionPlan` holding only those facts (with
descriptions and precision, never numbers), the markers for that section, the directives that name it,
and the section's spec text. The writer prompt is built only from the plan.

---

## 7. Writing, tokens and repair

### 7.1 Sections and slots

The config keeps the starter's contract (`template` with `<<slot>>`s, `use_if`, `placeholders`), with
three slot kinds:
- `generated`: written by the model from the section plan;
- `computed`: built by code (the account table and its footnote, the list of excluded money);
- static text lives in the template itself (the FCA line, the risk warning: never a slot).

`use_if` becomes a ledger predicate (`"always"` or `{"ledger": "sections.tax_implications"}`) rather
than plain language: G5 is deterministic, so inclusion is decided in code (D11).

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
computed footnote (G2).

One writer call per generated slot (D6): isolation per section (G11), independent repair, small
prompts, and §10's "only its own facts". Cross-section consistency comes from the shared ledger, not
from one long prompt.

### 7.3 Prompts

Each prompt is a markdown file in `config/prompts/` with a fixed structure (role; inputs it receives;
numbered rules; output format; what to do when information is missing: use a marker token, never
invent). The prompt version is the sha256 of its text plus its output schema, computed automatically,
so a changed prompt can't keep an old version label. Prompts describe patterns only; no example uses a
real client value (`check_repo.py` enforces names, IDs, platforms and amounts).

---

## 8. Validation, release and outputs

### 8.1 Gates in the pipeline

The gates live once, in `src/agent_pipeline/gates/`, and run in two modes (SCOPING §2 "two layers"):
- **pipeline mode:** truth = the ledger (the "else" column);
- **eval mode:** truth = expected facts (`eval/expected/<client>.json`).

Stage 5 runs the section-level deterministic gates. After assembly, the report-level deterministic
gates run: G1, G2, G5, G6, G7 (deterministic part), G9, G11, G13, G14, G15.

### 8.2 Release judge (stage 6)

One structured call per report covering the hard judge gates:
- **G8:** for each ledger action, is it in Recommendations (quote from the report)? For each
  recommendation in the report, which ledger action does it implement (or none)?
- **G16:** list every material claim (money, accounts, tax position, agreed actions); for each, a
  supporting source quote. **Code verifies every source quote**; a claim with no verified quote is
  unsupported.
- G2's role check, G4 paraphrase and G10 paraphrase as short yes/no findings with quotes.

If the judge finds a problem in one section, that section gets one repair round with the finding,
then the gates and judge re-run once. Otherwise the run is a failed generation.

### 8.3 Release states (SCOPING §2)

| State | Written | Meaning |
|---|---|---|
| Draft for adviser review | `outputs/<client>.md`, `.review.md`, `.ledger.json`, `.run.json` | every hard gate passed; markers and blocking items may remain |
| Failed generation | `outputs/<client>.failed.md` (banner "NOT ISSUED", the draft, the failing gates with offending text), `.review.md` (status FAILED), `.ledger.json`, `.run.json` | a hard gate failed; any previous `outputs/<client>.md` is removed so a stale draft can't be mistaken for this run's |

The pipeline never marks anything client-ready (SCOPING §2).

### 8.4 The review sheet (`outputs/<client>.review.md`)

Built in code from the ledger. Sections, in order:
1. **Status:** release state, run ID, date, cache replay vs live, gate summary.
2. **Blocking before sign-off:** blocking open actions (e.g. an unconfirmed cash account).
3. **Markers to fill:** `#n`, what is needed, why (the rule), section.
4. **Conflicts and how they were resolved:** both values, both sources and dates, the winning rule.
5. **Superseded values:** value, date, source, replaced by.
6. **Accounts left out:** each account not in the table and why (out of scope, closed, no value).
7. **Section decisions:** each conditional section, included or omitted, with evidence (§8 of SCOPING).
8. **Notes:** P4 notes, scope flags, currency items, image discrepancies, unverified extractions.

### 8.5 Run summary (`outputs/<client>.run.json`, printed at the end of every run)

Per stage: calls, **cache hits vs live calls**, tokens (input/cached/output/reasoning), cost, latency,
model and prompt versions; gate results; release state. The console line always says, e.g.,
`14 calls: 14 replayed from cache, 0 live, $0.0000`, so a replay is never mistaken for generation.

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
  stage's config or inputs is a miss, never a stale hit (S4). Entries are committed JSON files under
  `cache/llm/<aa>/<key>.json` holding the stage, model, prompt version, input hash, the response,
  usage and cost; no keys, no headers. `--fresh` bypasses reads and rewrites entries.
- **Retries:** transient errors (429, 5xx, timeouts, connection) retry with exponential backoff and
  jitter, honouring `Retry-After`, up to 4 attempts. A schema-validation failure gets one re-ask with
  the validation error. A refusal or empty output raises (as `generate.py` does now), never returns "".
- **Cost:** price table in `config/models.json` (source URL and retrieval date recorded); cost per call
  from usage, including cached-input and reasoning tokens.
- **Budget guard:** a per-run cost ceiling in config; `--estimate` prints uncached calls and an
  estimated cost without calling the API (CLAUDE.md: estimate before any live batch).
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
excluded items, must-not-appear strings, plus **extraction expectations** (value observations with
basis, money items with class, disposals, open actions with blocking flag) so extraction can be scored
on its own (§10.7). The four clients' files are hand-derived from SCOPING §7 first (build order, §9).

### 10.2 Gates

The same gate functions as the pipeline (§8.1), in eval mode. Each result records pass/fail and the
offending text. Deterministic gates run offline on existing outputs at no cost.

### 10.3 Judge rubric (eval, gpt-6-sol)

One structured call per report per criterion group. Q1 per section against the spec text; Q2 claim by
claim; Q3 per directive; Q4; Q5 per marker; Q6 judge part only where expected facts are missing. Each
criterion scores 1–5 against written anchors (5 = "no issue"; 3 = "minor, a reader would not be
misled"; 1 = "wrong or misleading"), with report quotes as evidence; source quotes are verified in
code. G8 and G16 are also re-scored by the eval judge against expected facts.

### 10.4 Results files

`eval/results/<UTC-timestamp>_<short-sha>[-dirty].json`, committed: commit, dirty flag, config hash,
prompt versions, models per stage, per-client per-gate results with offending text, extraction scores,
Q scores, tokens, cost, cache hits vs live. `scripts/progression.py` builds the baseline-to-final table
from these files; no metric is typed by hand.

### 10.5 Broken-report tests (every gate)

`tests/test_gate_mutations.py`. A **reference bundle** per client (report, review sheet, ledger) is
built offline from its expected facts by a deterministic stub writer, and must pass every gate. Each
mutation breaks one thing and asserts that exactly the intended gate fails:

| Gate | Mutation |
|---|---|
| G1 | add an out-of-scope account; list a joint account twice; show "Joint" as owner; drop an in-scope row |
| G2 | insert a distractor figure; a superseded value outside the footnote; "£45k"; a figure in words |
| G3 | insert a CGT amount, a CGT rate, a platform charge rate |
| G4 | remove the risk warning; duplicate the FCA line; add a paraphrased warning |
| G5 | drop the Tax section when required; add it when not |
| G6 | swap a selected value for the superseded one; drop "c." from an approximate value |
| G7 | allocate the contingent amount; treat received as available without subtracting committed |
| G8 | drop an agreed action; action an aspiration (judge) |
| G9 | put a transaction amount in Background |
| G10 | paste a sentence of internal guidance |
| G11 | add a second table; move the risk warning into Recommendations |
| G12 | start a slot with a capitalised full sentence mid-sentence; double full stop |
| G13 | change the risk-profile label; misspell a name; new account without "To be opened" |
| G14 | remove a required marker; add a marker for a settled value |
| G15 | drop a conflict row; drop a blocking flag; marker without a review row |
| G16 | add an unsupported claim about the client's tax position (judge) |

Deterministic mutations run offline in every `pytest`. Judge mutations (G8 aspiration, G16, paraphrase)
are recorded once live and then replay from the committed cache, so they also run offline.

### 10.6 Hand-written cases

`data/synthetic/handwritten/<case>/` with `eval/expected/<case>.json`, each small (two or three
accounts) and aimed at one rule the scoping is least sure of: image dated after the account data (R3,
P10); recalled vs viewed figure (R3); joint copies disagreeing, and on the same date (R9); in-scope
closed account and in-scope null (R6); request vs meeting conflict on selling (G5b); exact vs different
approximate amount (R5); commitment with no amount (P5); bond encashment plus ISA switch (G5, P7);
unresolved scope phrase (R8); non-GBP account (P12); request field "TBC" (P11); two meeting records
(R10); renamed files and an extra unknown document (classification). ≈14 cases.

### 10.7 Model selection by measurement (D2)

`report_eval.run --stage-models extract=gpt-6-sol,release_judge=gpt-6-sol` runs any stage on another
model through the config override. The protocol, once the four clients and hand-written cases have
expected facts:
1. **Extraction:** run on Luna and on Sol; score both against the extraction expectations (per
   category precision and recall). Upgrade to Sol only if Luna misses a fact Sol gets, or produces a
   wrong fact Sol doesn't, on any case.
2. **Release judge:** run on Luna and on Sol over the clean reference bundles and the judge mutations.
   Upgrade only if Luna misses a mutation Sol catches, or raises more false alarms on clean reports.
3. Record the outcome with `/decision`, citing both results files.

Estimated cost of the experiment: ≈18 cases × (Sol extraction ≈$0.06 + Sol judge on ≈3 bundles
≈$0.18) ≈ $4.30; Luna runs ≈$0.20.

### 10.8 Synthetic clients (D4)

`src/report_eval/synth/`: a seeded scenario sampler varies the SCOPING §5 patterns (names, account
mixes, joint accounts, stale dates, nulls, closed accounts, out-of-scope accounts, new accounts,
received/committed/contingent money, limit breaches, distractors, tangents and aspirations, handling
notes). From the scenario, code writes the account JSON, the report-instruction table (python-docx)
and the statement image (Pillow), and derives `eval/expected/<id>.json`. An LLM writes the meeting
note and general document prose around **required phrases**; code checks every required quote appears
verbatim and no unplanned figure appears, and rejects the file otherwise. Generated once and committed
under `data/synthetic/generated/<id>/`, never regenerated per run. ≈20 clients, ≈$0.01 each, one-off.

The generator encodes the same rules the pipeline implements, so it catches implementation errors,
not rule errors; the hand-written cases cover the rules (SCOPING §9).

### 10.9 Budget

Against the $10 key, estimated: pipeline on all ≈38 clients ≈$0.40 per uncached run; eval judge ≈$2.70
per uncached full run; model-selection experiment ≈$4.30; synthetic generation ≈$0.20. That is ≈$7.60
for one pass of everything, so the eval judge runs on changed clients by default and on all clients
before recording a result, and the experiment runs once. Cached reruns are
free, so iteration is bounded by prompt changes, not reruns. Every live batch prints its estimate first
(`--estimate`) and asks before spending.

---

## 11. Config: prompts as code, several report types

```
config/
  base.json                shared: global instructions, marker format, static texts, stage models
  template_config.json     investment advice report: "extends": "base.json", sections
  sections/                reusable section definitions (introduction, fees_charges, conclusion…)
  prompts/*.md             one file per prompt; version = content hash
  models.json              price table (source URL, retrieval date)
  tax_rules.json           P4 reference figures keyed by tax year (source and date per entry)
```

- **Report types without duplication:** a report config `extends` a base and lists sections by
  reference (`{"use": "sections/fees_charges.json"}`) with optional overrides (title, selectors,
  prompt). A second report type (e.g. an annual review) is one new file reusing shared sections,
  prompts and static texts (S6).
- **Stage models:** `base.json` holds `"stages": {"extract": {"model": "gpt-6-luna",
  "reasoning_effort": "medium"}, …}`; a report config or the CLI can override per stage (D2).
- `tax_rules.json` holds figures that also occur in `data/` (the ISA allowance), so they need
  `scripts/overfit_allowlist.txt` entries with a reason, as `check_repo.py` intends.

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
  reconcile/             ownership.py; scope.py; values.py; amounts.py; money.py; limits.py;
                         sections.py; markers.py; review.py
  write/                 plan.py; writer.py; tokens.py; table.py
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
No others: fuzzy matching uses `difflib`; config stays JSON (no YAML dependency).

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

1. `SCOPING.md` has uncommitted changes in the working tree (P5 proceeds, G5 case b). This design is
   built against the working-tree version; commit it so the design has a fixed reference.
2. `check_repo.py` builds its denylist from top-level client folders only, so synthetic client values
   under `data/synthetic/` are not denied in `src/`/`config/`. The plan should extend it to recurse, so
   prompts can't overfit synthetic cases either.
3. `temperature` support is undocumented for gpt-6 models. If unsupported, S4 reproducibility rests on
   the committed cache, which the run summary makes visible.
4. G8 "every agreed action appears in Recommendations" includes agreed non-actions (client 04: leave the
   offshore bond as it is). The expected-facts files list them as actions so the gate checks them.
