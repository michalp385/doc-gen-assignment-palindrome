# Decisions

The hardest calls in this pipeline, why I made them, and what I would do next.

## Summary
A fixed, code-driven workflow (D5): sources are classified, facts are extracted with verbatim quotes
that code verifies (D9), and a ledger of reconciled facts and adviser-review markers is built in code
by one function per trust rule. The writer fills each slot from fact IDs and never types a figure (D1),
gate checks (14 per client in the results file) verify the result, and a release judge (a majority of
samples) covers the parts that need reading. Result, from `eval/results/20260930T184615Z_99cef32.json`
(commit `99cef32`, clean tree, judged): 4 of 4 clients are drafts with 0 failing deterministic gates, an
issued rate of 1.0, a release-state match rate of 1.0, 0 wrongly issued, and $0.0345 per report. The
rubric judge scores the adviser markers (Q5) 5 out of 5 on three clients and 4 on client 03; the starter
baseline has no markers, so its Q5 is shown as n/a in `eval/progression.md`. The weak spots are in the same file: the
lowest rubric score is 2 out of 5, and client 04's extraction matched 1 of 3 expected value observations
and 1 of 2 open actions. The decision most worth discussing is D22/D26: the release judge is not
repeatable, because neither model on this key accepts `temperature`, so a fresh run can fail a correct
report (it did on case 08, D22). Everything above replays offline from the committed cache; that is the
state I chose to ship, not the outcome of a resample. The 20 hand-written cases, each aimed at one rule,
are scored on deterministic gates and release state only, with no rubric judge (it was never run on
them): `eval/results/20260930T184620Z_7ad73ee.json` (commit `7ad73ee`, clean tree) shows 20 of 20
matching their expected state, 0 failing deterministic gates, 0 wrongly issued and 0 accepted-and-wrong;
18 are drafts and 2 stop at the input by design.

## Decisions
<!-- Entries added with /decision. Keep the ones that matter; cut the ones that don't. -->

### D1. Fill figures and markers into prose with ledger tokens, never let the writer type them
- **Context:** the baseline invented CGT figures (£3,540; ~£6,600), fee rates (0.5% + 0.5%) and a stale
  GIA value (£40,000 against a live ~£45,000), and client 03's report contradicted its own table
  (£38,000 vs £30,000). CLAUDE.md requires every figure to be a source value or a calculation in code,
  and SCOPING P1 requires markers to be inserted by code.
- **Decision:** the writer sees fact IDs with descriptions, never numbers, and writes `{fact:…}` and
  `{marker:…}` tokens; code fills them from the ledger. Writer output containing any digit fails
  validation.
- **Alternatives:** let the writer copy rendered figures into prose and validate every figure
  afterwards. More natural prose, but a wrong figure is caught after the fact instead of made
  impossible, and rewording drift ("around" vs "c.") needs fuzzy rules.
- **Consequences / how it generalises:** prose can read slightly stiffer; each fact needs a prose and a
  table rendering. Works for any client because no figure passes through a model. Revisit if the judge
  scores Q4 (clarity) low on token-filled sentences.
- **Evidence:** none yet (design stage).

### D2. Set the model per stage in config; default every pipeline stage to Luna, judge with Sol
- **Context:** the key can use gpt-6-luna and gpt-6-sol (prices in `config/models.json`), among
  others; at the time, against a fixed budget (since replaced by cost reporting, D12). The release judge
  (G8, G16) runs on every report, so its model decides both cost and which drafts are issued.
- **Decision:** every stage's model is a config setting. Luna is the default for every pipeline stage;
  Sol is the eval judge. The intended comparison (extraction, the release judge and the investigation
  agent (D14) on both Luna and Sol over the four clients and the hand-written cases, so that a stage
  moves to Sol only if Luna measurably misses) has not been run. Luna is a default, not a measured
  choice.
- **Alternatives:** Luna everywhere including the eval judge (a model grading its own output tends to be
  lenient); Sol for both judges (dearer per report, so two or three full eval runs would have used most of the
  budget).
- **Consequences / how it generalises:** the comparison needs extraction to be scored on its own against
  expected facts (DESIGN §10.7), which the eval does. If it is run, its outcome gets its own entry,
  citing both results files. It is listed under "What I would do with more time".
- **Evidence:** none for the choice of Luna. The results files record Luna for every pipeline stage and
  Sol for the eval judge only (`stage_models`); none records a run with a pipeline stage on Sol.

### D3. Commit the LLM response cache, and make every replay visible
- **Context:** reviewers re-run the pipeline from a clean checkout with their own key; model output can
  vary between runs, and the committed outputs should be reproducible.
- **Decision:** commit `cache/llm/`. The cache key covers the model, stage settings, prompt text, schema
  and inputs, so any change is a miss. Every run reports cache hits vs live calls in its output and
  trace; `--fresh` bypasses the cache; the README says so. Before submitting, one full `--fresh` run on
  all clients refreshes the cache and outputs.
- **Alternatives:** a local, gitignored cache: an honest live demonstration, but not reproducible, and
  every reviewer run costs money.
- **Consequences / how it generalises:** a reader could mistake a replay for generation, hence the
  hit/live counts on every run. Cache entries hold prompts and responses over data already in the repo,
  never keys.
- **Evidence:** none yet.

### D4. Write synthetic clients' prose with an LLM around required phrases, verify it, and freeze it
- **Context:** the held-out set has "the same themes and different specifics". Templated prose would
  let prompts tune themselves to the templates' phrasing.
- **Decision:** code builds each scenario, its structured files and its expected facts. An LLM writes
  the meeting note and general documents around required phrases; code checks every required quote is
  present and no unplanned figure appears. Generated once, committed under `data/synthetic/generated/`.
- **Alternatives:** templates with phrase banks: free and exact, but narrow, which is the overfitting risk
  this exists to catch.
- **Consequences / how it generalises:** synthetic clients test the implementation of the rules, not
  the rules themselves; hand-written cases cover the rules.
- **Evidence:** none yet.

### D5. Run a fixed code workflow with bounded model loops, not an orchestrating agent
- **Context:** SCOPING §8 puts every decision with a right answer in code. The places a model can
  usefully retry are narrow: a quote that doesn't verify, a section that fails a gate.
- **Decision:** a fixed stage graph in code. Models work inside bounded loops with tools: extraction
  corrects failed quotes with `find_in_source` (≤3 rounds); the writer repairs a section from gate
  findings (≤2 rounds); the investigation agent (D14) gets ≤6 read-only tool calls per question.
  Running out of rounds never produces a guess: an unverified fact goes to the review sheet, a question
  stays unresolved, and only a section still failing a hard gate makes a failed generation (D16).
- **Alternatives:** an orchestrator agent choosing tool calls (varies per run, costs more, puts ordering
  decisions in the model); single-shot calls with no loops (one fixable quote fails the whole report).
- **Consequences / how it generalises:** behaviour is reproducible and every step is traceable. Revisit if
  a new source type needs open-ended exploration.
- **Evidence:** none yet.

### D6. Write each generated slot in its own call, from its own fact slice
- **Context:** in the baseline, sections bled into each other (client 02's Tax section held an
  introduction, a table, the recommendation and the risk warning). SCOPING §10 asks how sections receive
  only their own facts.
- **Decision:** one writer call per generated slot, given only its section plan. Consistency across
  sections comes from the shared ledger, not a shared prompt.
- **Alternatives:** one call returning all sections as structured fields: cheaper and more coherent in
  tone, but the whole ledger sits in one prompt and bleed is harder to prevent.
- **Consequences / how it generalises:** several small calls per report; each section can be repaired alone.
- **Evidence:** none yet.

### D7. Classify sources by content: schema checks for structured files, a model for text documents
- **Context:** unseen clients may name files differently or add new ones (SCOPING §3); general
  documents (market updates, portfolio packs) must never feed client facts.
- **Decision:** JSON that validates as account data is classified in code; an image is a candidate until
  the vision read confirms it shows an account table; text documents are classified by Luna with a
  verified evidence quote, and low confidence makes them unknown. Unknown roles are excluded and logged.
- **Alternatives:** filename mapping (breaks on renamed files); content heuristics alone (brittle on
  unseen phrasing).
- **Consequences / how it generalises:** a small per-report cost; a hand-written case with renamed files and
  an extra unknown document tests it.
- **Evidence:** none yet.

### D8. Turn the internal guidance into a structured handling directive; the writer never sees its text
- **Context:** G10 forbids internal guidance text in the report; client 03's notes ("the recent death of
  her mother") must shape tone without being quoted, and call Jean "the client" though the account data
  makes Robert the `client`.
- **Decision:** extraction reads the whole notes, with the people list from the account data and the
  meeting record, into directives for client-specific handling only (sections affected, instruction,
  the person by name with evidence, checked against the people list). The writer receives the
  directive, never the notes. An unresolved person is a review item, not a guess.
- **Alternatives:** pass the section to the writer with "never quote this" (leak risk rests on the
  prompt alone).
- **Consequences / how it generalises:** the G10 screen stays as a backstop. General rules that only some
  clients' notes contain live in config instead.
- **Evidence:** built as D29.

### D9. Anchor every extracted fact to a verified quote and parse its amount in code
- **Context:** meeting figures come with wording that matters ("a little over £45,000", "around
  £38,000", "up to £400,000"); a model can mistype or round a number.
- **Decision:** extractors return quotes; code verifies each quote is in the source and parses the amount
  and qualifier from the quote. Numbers the model put in fields are ignored.
- **Alternatives:** trust the model's structured amount fields (no guarantee the number matches the
  source).
- **Consequences / how it generalises:** needs a robust amount parser (formats like "GBP 120,000",
  "£1.2m"), tested first. Unverifiable facts become review items.
- **Evidence:** none yet.

### D10. On a failed hard gate, write a marked failure file and remove the previous draft
- **Context:** SCOPING §2: a failed generation is not issued. Reviewers still need to see what happened,
  and a previous run's draft must not look current.
- **Decision:** a failure writes `outputs/<client>.failed.md` (banner, draft, failing gates with the
  offending text) and a review sheet with status FAILED, and removes any previous `outputs/<client>.md`.
- **Alternatives:** write nothing (the failure is invisible to a reviewer); keep the previous draft
  (stale output mistaken for current).
- **Consequences / how it generalises:** a failure is always explicit in `outputs/`.
- **Evidence:** none yet.

### D11. Extend the `use_if` contract with an optional code predicate, rather than replacing it
- **Context:** the baseline asked a model whether each conditional section applies. G5 is deterministic
  (taxable disposal, or a conflict about one), so inclusion has a right answer. PROJECT_GUIDANCE
  describes `use_if` as a plain-language condition, and new report types should work from config.
- **Decision:** `use_if` stays plain language, and a section may add an optional `predicate` naming a
  ledger decision. With a predicate, inclusion is decided in code and checked by G5; our shipped config
  sets one for every conditional section. Without one, a model decides from ledger facts only, with its
  reasoning logged and flagged on the review sheet. An unknown predicate name fails at load. Report
  configs `extends` a base, with sections merged by id.
- **Alternatives:** predicates only, with plain `use_if` removed (fully deterministic, but breaks the
  documented contract and makes every new condition a code change); plain language decided by a model
  everywhere (the baseline: non-deterministic inclusion, unexplainable when wrong).
- **Consequences / how it generalises:** we extend the contract rather than replace it. Shipped reports
  are fully deterministic; a new report type works from config alone, visibly flagged until someone
  adds a predicate. Every inclusion decision is explained in the review sheet (SCOPING §8).
- **Evidence:** none yet.

### D12. Report cost as a metric instead of working to a budget cap; keep the default pipeline cheap
- **Context:** costed in full at the time (the estimate has since grown with the added cases and the
  investigation agent; DESIGN §10.9 holds the current one), the design's development and eval plan came
  to more than the $10 key allowed: the Sol eval judge, the full Luna-vs-Sol experiment over the four clients and the hand-written
  cases, synthetic clients and the final `--fresh` run. A Sol result from the experiment couldn't have
  been acted on within the cap.
- **Decision:** I fund development and eval runs separately, and nothing in the plan is cut. Every run
  records its cost per stage and per report, and cost per report is a reported metric in every results
  file. The default pipeline stays cheap (Luna unless the experiment proves otherwise, plus the
  committed cache), so a reviewer's re-run costs cents.
- **Alternatives:** a Luna eval judge while iterating and Sol only to confirm, with a reduced experiment
  (cheaper, but weaker evidence for D2); dropping the synthetic clients (still tight, no room for a Sol
  upgrade); skipping the experiment and staying on Luna (reverses D2).
- **Consequences / how it generalises:** any Sol upgrade is recorded with its cost next to the accuracy
  it buys. CLAUDE.md and the `run-eval` skill are updated to match. The cost estimate
  before a live batch stays, made by hand from the model prices and the number of cache misses.
- **Evidence:** none yet; spend is read from run summaries and results files.

### D13. Degrade gracefully on odd or missing inputs, and measure it with an issued rate
- **Context:** unseen clients will bring sources with extra or missing fields, undated notes and
  unfamiliar account types. The first draft of the design failed the run on several of these (schema
  errors, an unparseable meeting date, a figure in a writer input), which would leave an adviser with
  nothing where a flagged draft is useful.
- **Decision:** everything that isn't unsafe (D16) degrades: unknown fields are ignored and logged,
  missing optional fields go through the rules, an unparseable meeting date makes the meeting undated
  for value selection (a metadata date may only set the tax year), unverifiable facts are dropped or get conservative defaults, each with a review
  item. The review sheet has a "how this draft degraded" section listing every one.
- **Alternatives:** fail fast on any schema or parse problem (safe, but brittle on exactly the variation
  the held-out set brings); degrade silently (a finished run could hide a guess).
- **Consequences / how it generalises:** on hand-written and synthetic clients the eval reports the
  issued rate (share reaching "draft for adviser review") next to the release-state match rate, and
  some hand-written cases are built to fail, so a high issued rate can't hide wrong drafts. Revisit if a
  degradation turns out to let a wrong figure through.
- **Evidence:** none yet.

### D14. Add a bounded conflict investigation agent that gathers evidence; code still decides
- **Context:** single-pass extraction can't settle some questions that need a look across sources:
  which account client 03's "another small cash account from some years ago" is; whether a meeting
  figure was viewed or recalled; a scope phrase that failed its checks. Without more evidence these
  fall back to conservative defaults, which is safe but can over-flag (Q6).
- **Decision:** reconciliation emits open questions only where more evidence could change the outcome
  under the rules. For each, an agent with read-only tools (read and search sources, read account data
  and ledger entries), up to 6 tool calls and 5 questions per report, returns a finding with quotes.
  Code verifies the quotes, accepts a proposed label only with evidence in the same paragraph as the
  fact, accepts an account link only if every scope check passes and exactly one account qualifies
  (several candidates stay flagged, per R8), and re-runs reconciliation once. Accepted evidence may make
  an outcome less conservative, since it passed the same checks as extraction; each such change is shown
  on the review sheet as "changed by investigation", with the default it replaced, the new value and the
  quote. Findings are always shown; the agent itself never selects a value, and investigation can never
  fail a run.
- **Alternatives:** none, relying on conservative defaults (simpler, but more markers where the sources
  do hold the answer); an agent allowed to resolve conflicts itself (puts decisions SCOPING §8 assigns to
  code into a model).
- **Consequences / how it generalises:** one more model stage to measure. It is scored on the
  hand-written ambiguity cases; it is one of the stages the unrun Luna-vs-Sol comparison (D2) would cover; costs nothing when no
  question is open. Accepted-and-wrong (a finding code accepted that contradicts expected facts) is a
  headline metric in every results file, reported apart from general accuracy; a non-zero figure is the
  evidence that would make us restrict the agent to annotating.
- **Evidence:** `tests/test_investigate_*.py`, `tests/test_reconcile_questions.py`,
  `tests/test_report_eval_investigation_score.py`; D27 for what opens a question.

### D15. Define truth and the deterministic core first, then a thin client 01 slice, then widen
- **Context:** the design has eight stages, an agent and an eval. Building each stage fully across all
  clients before anything runs end to end risks late integration surprises. SCOPING §9's build order
  puts the four clients' expected facts and the hand-written cases first.
- **Decision:** M0a writes the expected facts for all four clients and the hand-written cases; M0b
  builds the deterministic core tests-first (parsing, quote verification, the reconcile rules); M1 is
  client 01 correct end to end through every real stage, scored against its expected facts. Clients
  02–04, the hand-written cases end to end, the investigation agent, model selection and synthetic
  clients follow.
- **Alternatives:** slice first and write the other clients' and hand-written expected facts later
  (earliest end-to-end run, but breaks SCOPING §9 and leaves the uncertain rules untested for longer);
  build every stage fully before any end-to-end run (late integration).
- **Consequences / how it generalises:** SCOPING §9's order holds, and every rule has a unit test before
  the slice exists. The uncertain rules run end to end only from M2.
- **Evidence:** none yet.

### D16. Keep a failure hard where continuing is unsafe
- **Context:** graceful degradation (D13) keeps a draft coming in most cases, but some gaps leave no
  safe basis for any draft: without account data there is no account table, without a report
  instruction no scope, without a meeting record nothing the client agreed to. A hard gate still
  failing after repair means the draft breaks a rule SCOPING forbids issuing (G1–G16).
- **Decision:** these stop the run as a failed generation with the reason: no readable account data,
  or two account data sources that disagree; no report instruction, two that disagree, or one whose
  scope field is missing, "TBC" or resolves to nothing; no meeting record; a hard gate failing after its repair
  rounds; a model call that still fails in a required stage, or the runaway-cost guard (the same failure in an
  optional stage degrades). The failure file shows the draft (if
  any), the failing gate and the offending text (D10).
- **Alternatives:** degrade these too, e.g. build the table from every account when scope is missing
  or issue a draft with a known gate failure flagged (an adviser could sign a draft with out-of-scope
  accounts or an invented figure; the flag would be one item among many).
- **Consequences / how it generalises:** the list is short and explicit (DESIGN §8.4), so adding to it
  is a decision, not a drift. The hand-written cases include one failure by design, and the
  release-state match rate shows whether failures happen where expected and nowhere else.
- **Evidence:** none yet.

### D17. Exempt `src/report_eval/` from the overfitting scan
- **Context:** T9's deterministic stub writer (`src/report_eval/reference.py`, DESIGN §10.5) builds
  client 01's reference bundle by hand-rendering its known report text, so it necessarily hardcodes
  Margaret Hughes's name, her account ID and her account's figures. `check_repo.py`'s overfitting scan
  covered all of `src/`, so it flagged every one of them, even though CLAUDE.md's rule exists to keep
  the *pipeline* generalising to unseen clients, not to forbid test/eval fixtures from encoding known
  facts about known clients (`eval/expected/*.json` already does exactly that, outside the scan).
- **Decision:** `check_overfitting` now skips any path under `src/report_eval/`
  (`OVERFIT_EXCLUDE_PREFIX`), while `src/agent_pipeline/` and `config/` stay fully scanned. Static-text
  and secrets checks are unaffected: they still cover all of `src/`.
- **Alternatives:** allowlist every client-01 value individually (the allowlist header itself says to
  keep that list short and justified; one client's name, account ID and figures is neither); move all
  hand-authored client-01 prose out of `reference.py` into a new per-client data file under `eval/`,
  keeping `reference.py` fully generic (more faithful to the check's current scope, but real extra
  work and duplicates facts `ExpectedFacts` already encodes, for no functional benefit).
- **Consequences / how it generalises:** `src/agent_pipeline/` (the pipeline) still can never carry a
  client-specific value; `src/report_eval/` (eval/test tooling) now explicitly may, matching
  `eval/expected/*.json`'s existing exemption. Revisit if `report_eval/` ever grows a module that
  *is* part of a real run's pipeline path rather than eval/test tooling only.
- **Evidence:** `bash scripts/check.sh` green (all repo checks pass) after the change.

### D18. Extraction's verification loop calls `find_in_source` from code, not as a real model tool
- **Context:** DESIGN §4.1 says the model "may call one tool, `find_in_source(text) → matching
  paragraphs`" while correcting a rejected quote. T11 deliberately left OpenAI function-calling
  unwired in `LLMClient` (tool definitions go into the cache key per DESIGN §9, but nothing threads
  them into the transport call) -- building that now, just for this one loop, is real surface in
  `llm.py` neither T11 nor T13 otherwise needs.
- **Decision:** the verification loop itself calls a deterministic `find_in_source` search function
  when a fact's quote fails `verify_quote`, and folds the candidate paragraphs into the next re-ask
  as plain text. The model never issues a real tool call; it just sees better context on retry.
- **Alternatives:** wire real SDK tool-calling into `LLMClient` now. More implementation surface for
  no behavioural difference DESIGN requires here, and harder to test offline with a scripted fake
  model (T13's own tests-first requirement).
- **Consequences / how it generalises:** this doesn't block or duplicate T22's conflict-investigation
  agent, which needs genuine adaptive multi-tool SDK calling across five tools (`find_in_source(text,
  source?)`, `list_sources()`, `read_paragraphs()`, `get_accounts()`, `get_ledger_entry()`, DESIGN
  §5.2) searching across every source, not one document -- a different signature and a different
  mechanism (the agent chooses which tool to call, not code deciding when to retry). T22 builds real
  tool-calling infrastructure in `llm.py` regardless of what T13 does. Revisit if a future stage needs
  the model itself to decide when to search, rather than code deciding for it.
- **Evidence:** none yet.

### D19. Give the writer its own slot-scoped gate checks in `write/writer.py`, reusing T9's regexes/constants rather than faking a `ReportBundle`
- **Context:** DESIGN §7.2/§8.1 says stage 5 runs "the section-level deterministic gates" on
  each generated slot, and stage 7 re-runs the full gate set on the assembled draft -- two runs,
  but DESIGN gives only one function signature (`_check_g4(bundle: ReportBundle, truth: Truth)`
  etc. in `gates/deterministic.py`, T9), which takes the *whole report* (every section, the
  table, the full ledger) and a `Truth` (expected-facts or ledger truth) -- shapes a single slot
  under repair, mid-writing, doesn't have yet (no assembled `report_text`, no `truth` object, no
  finished `table_rows`).
- **Decision:** `write/writer.py` gets its own small functions (`_check_g4_paraphrase`,
  `_check_g9_no_transaction_facts`, `_check_g10_no_guidance_leak`, `_check_g11_no_structure`,
  `_check_g12_pre`, `_check_g12_post`), each taking just the slot's own text (and `SectionPlan`
  where relevant) -- importing and reusing T9's already-built regex/constant objects directly
  (`PARAPHRASE_THRESHOLD`, `FCA_LINE`, `RISK_WARNING_FULL`, `word_ngrams`, `DOUBLE_STOP_RE`,
  `MIDSENTENCE_CAP_RE`, `TABLE_HEADER`, promoted from private to public in `gates/deterministic.py`
  for this reuse) instead of retyping them. G9/G11 are structurally scoped to the
  `background_objectives` section specifically, matching the existing precedent in
  `gates/deterministic.py`'s own report-level `_check_g9`/`_check_g11` (which already hardcode
  section ids like `"background_objectives"`/`"introduction"`/`"conclusion"`), not a new
  config-driven abstraction.
- **Alternatives:** fake a single-section `ReportBundle` (one section, one table row) and a stub
  `Truth` just to call T9's existing `_check_g4` etc. unchanged. Rejected: a `ReportBundle` bundles
  the *whole report's* shape (`table_rows`, `ledger`, every section) that doesn't exist yet
  mid-writing, so most of it would be empty/fake data threaded through only to satisfy a
  signature, and `Truth` has no natural single-slot meaning (`table_accounts()`,
  `required_markers()`) that isn't already answered by the section's own `SectionPlan`.
- **Consequences / how it generalises:** stage 5 (per-slot) and stage 7 (report-level) gates
  under the same G-number now live in two places by design, not duplication by accident -- each
  checks what's actually available at that stage. A new slot-level gate reuses T9's constants the
  same way; a new report-level gate stays in `gates/deterministic.py` untouched. Revisit only if a
  future gate genuinely needs the same check to run identically pre- and post-assembly (none do
  yet: G4/G9/G10/G11 are meaningfully narrower per-slot, and G12 already runs twice on purpose,
  pre- and post-substitution, per DESIGN §7.2).
- **Evidence:** `tests/test_write_writer.py` (all slot-level gate paths), `bash
  scripts/check.sh` green after the change.

### D20. Treat a missing currency as not-GBP, and don't let a meeting figure rescue it
- **Context:** DESIGN §3.3 says a missing currency is treated as not-GBP (P12), but `select_values`
  labelled it GBP, so a record with no `currency` would have had its value rendered as sterling.
  Every account in the four real clients states GBP, so nothing in `data/` exercised it; a held-out
  client whose records omit the field would have. A dated meeting figure (`£…`) can win under R3
  for the same account.
- **Decision:** a missing or blank `currency`, or an account absent from the currency map, is
  not-GBP: the value is withheld from the ledger, the table's value cell is a marker, and the review
  sheet says the currency is not stated. A meeting figure that would win under R3 does not override
  this: the account's own currency being unstated is what decides.
- **Alternatives:** let the meeting's £ figure rescue the account. Fewer markers, but it takes the
  meeting note's currency on trust for an account whose own data is silent, and I'd rather ask the
  adviser than guess a unit.
- **Consequences / how it generalises:** it can over-withhold, which fails safe: a visible marker and a
  review item, never a wrong figure reaching the client. Under-withholding is the failure that
  matters. Revisit if the held-out or synthetic runs show many accounts withheld for a missing
  currency where the meeting states the figure clearly.
- **Evidence:** commits `04da7a3` and `212bfcd`; `tests/test_missing_currency_p12.py`,
  `tests/test_currency_render_leaks.py`.

### D21. Exempt required standard wording from G16 in code, with a whitelist, not in the judge's prompt
- **Context:** the release judge saw the whole report, and G16's coverage scan in code demanded a
  verified source claim for every clause with a tax term, a figure or an account name. Client 02's
  Tax Implications states, as spec wording (P7), that a disposal may create a CGT liability
  assessed against the annual exempt amount, and a recommendation says the proceeds are gross
  before CGT (P5). Neither has a client source by design, like the FCA line G4 already checks
  exactly, so the judge could only invent a source quote, which failed verification and failed a
  correct report.
- **Decision:** `config/standard_wording.json` lists the standard sentences as patterns.
  `is_standard_wording` matches a sentence in code and never when it has a digit, a figure or an
  account name or type. Such a sentence needs no claim, any claim the judge gives for one is
  ignored, and the judge is shown `[standard wording]` in its place. The prompt only describes this;
  the code enforces it whether or not the judge obeys.
- **Alternatives:** tell the judge in the prompt to ignore the sentences. It is a loose instruction,
  and the code would still send the clause back for an uncovered claim. Exempt every tax sentence:
  it would let an invented client tax claim through.
- **Consequences / how it generalises:** G16 stays strict for anything client-specific. The whitelist
  covers the wording the writer prompts are told to produce; a differently worded standard sentence
  falls back to needing a claim, so the list grows as new wording appears. A sentence with a figure
  is never exempt.
- **Evidence:** `tests/test_g16_standard_wording.py`. Live passes on clients 01 and 02 after this
  did not stabilise (see D22), so no results file is quoted.

### D22. The release judge's verdicts are not repeatable, so a fresh judge run can fail a good report
- **Context:** the judge runs on `gpt-6-luna`, which rejects `temperature` (`config/models.json`), so
  the same input can return different verdicts. Re-running client 02's judge once failed G16 on
  standard CGT wording. After D21 and a revised prompt, two more live passes failed different hard
  gates: client 01 on G16 for an introduction sentence its claim did not verify, and client 02 on G10
  for the table footnote naming `client_data_db.json`, a known defect (`write/table.py`
  `_source_label`). The committed client 02 draft passed only under an earlier verdict, and it does
  not replay offline because its judge cache entry is stale.
- **Decision:** I did not resample until a run passed, and I did not commit a failed draft as the
  client 02 output. The offline replay guarantee (S4) holds for client 01 only until the judge is
  made repeatable.
- **Alternatives:** keep re-running the judge (cherry-picks a verdict and proves nothing); accept
  failed generations as the committed outputs (hides the flaky component).
- **Consequences / how it generalises:** on a held-out client the same flakiness would produce failed
  generations that are not real failures. I am shrinking the judge's surface code-first, since any
  decision with a right answer belongs in code: D21 moved the standard wording; the Introduction's
  scope sentence is now checked against the ledger (`intro_scope_problems`) and needs no claim; and
  G10 rejects an internal file name deterministically. What stays with the model is what has no
  deterministic answer: whether a material claim about the client is supported by a source
  paragraph (G16), which recommendation implements which agreed action (G8), a figure used in the
  wrong role (G2), contingent money described as available (G7), a paraphrase of the static text
  (G4), text that reads as lifted internal notes (G10's subjective half), a passage that does not
  read grammatically (G12) and an aspiration presented as a recommendation (P6).
- **Known gap, and the real fix:** the Introduction is still a model-written slot, and I kept the
  exemption for its figure-free sentences loose (no digit, figure or tax term, checked against the
  ledger for account types). So a qualitative invention such as "your ISA has performed well"
  would pass G16 unsourced. A word-list to catch it would be brittle and bring back the false
  failures this change removed, so I did not build one. The real fix is to build the scope sentence
  from the ledger in code and remove the model-written scope slot, so that sentence cannot arise.
- **Three samples, three different false positives:** after D21 and the code-side fixes (the
  standard-wording whitelist, the introduction-scope check, the footnote wording and the G10
  file-name check), each fresh judge pass failed a different gate on a correct report: CGT wording
  (G16), then a filename in the footnote (G10) and an introduction sentence (G16), then G7 on
  client 02 saying the gross proceeds of a not-yet-completed disposal "are not established as
  available to invest". That last one contradicts SCOPING P5 (full-disposal proceeds count once the
  amount and destination are known, described as gross, before CGT, not yet realised), and the report
  says exactly that. The code fixes held (G16's whitelist and G10 did not recur); the residue is the
  non-repeatable judge. I stopped adding carve-outs: each one fixes the last sample and the next
  sample finds a new one.
- **Model check:** the T11 live probe (`tests/test_llm_live.py`) found that neither model accepts
  `temperature`; `config/models.json` records `temperature_accepted: false` for both `gpt-6-luna` and
  `gpt-6-sol` (checked 2026-09-27), and they are the only two on this key. The release judge runs
  `gpt-6-luna` at high reasoning effort (Sol is the eval judge), so no available model gives a stable
  verdict through `temperature=0`. No new live call was spent on this.
- **Options:** (a) take a majority of an odd number of judge samples per report, which keeps G7, G8
  and G16 hard gates but multiplies the judge's cost; (b) make judge-only findings review-sheet flags
  instead of hard gates, which weakens SCOPING's hard gates; (c) lower the judge's reasoning effort
  or move it to Sol, untested. The user chose (a). The introduction-scope, filename and
  standard-wording checks stay in code either way.
- **Built (a):** `majority_release_judge` runs `stages.release_judge.samples` independent
  `release_judge` passes, each with its own coverage re-ask, and each gate passes or fails by the
  majority, decided in code; a dissent is kept in a passing gate's detail. Each later sample has its
  own cache key. The setting defaults to 1; the shipped config now sets `release_judge.samples`
  to 3, with the parked v2 judge prompt (the standard-wording and stale introduction rules), and
  clients 01 and 02's judge cache was refreshed in one live run each. Both came out as drafts, and
  client 02's replay now needs no live call (`tests/test_pipeline_replay_client_02.py`). A dissent
  was outvoted and is recorded in `outputs/client_02_medium.run.json`. One sample per client is
  thin evidence: the vote shrinks the judge's variance, it does not remove it. Samples run one
  after another, so a report's judge latency grows with the count.
- **Evidence:** `tests/test_g16_intro_scope.py`, `tests/test_g10_internal_filenames.py`; the parked
  run artefacts are in the session scratchpad, not the repo, and no results file exists for this.
- **Root cause, and what would fix it:** the judge is non-repeatable because the only models on this
  key reject `temperature`, so its sampling cannot be pinned. The majority vote lowers the
  variance, it does not remove it: a later fresh run flagged a clause in client 03's
  Recommendations as uncovered by a majority of samples, when it matches the meeting note's
  "together with the inheritance, fund both ISAs" (D26). The real fix is a judge that can run at
  `temperature=0`, which needs a model that accepts it; none is available here, so it is listed
  under "What I would do with more time". Until then a fresh judge run can fail a correct
  report, and the committed outputs are the ones whose judge verdicts are cached.

- **Rebuild record (the once-only rule):** in the live rebuild after D29 to D32, two runs failed the
  release judge in their first pass. Client 03 failed G2 on 2 of 3 samples, for "the gross sale
  proceeds of c. £38,000" (the pattern D25 exempts). I took the one allowed resample, by deleting its
  recommendation-writer cache entry and re-running non-fresh. Its later drafts failed for real writer
  defects (the proceeds sentence carrying extra funding and dropping the disposal, then the proceeds
  attached to the wrong destination, G8), each fixed in rule 2 of the recommendation prompt (D32), not by
  resampling again. Case 08 failed G16 on 2 of 3 samples for "Vera has no income requirement from her
  portfolio.", which matches the meeting note word for word; its one allowed resample failed the same way.
  I did not sample a third time. It stayed a failed generation until the later writer-rule changes altered
  its report text, and the judge then evaluated the new text and it drafted: a fresh evaluation of
  different text, not a third sample of the same input. Case 17 also failed, twice, for real defects
  (D33, then D34: its run stopped on the stricter introduction check until the scope description stated
  the count). The committed state is the offline replay of these outcomes, checked with zero live calls.

### D23. A same-date tie between disagreeing values selects nothing
- **Context:** R3 says the most recent dated figure wins, but the account data's snapshot and a
  figure viewed in the meeting can carry the same date with different amounts (as can two figures
  viewed at once). `select_values` took `max` of the candidates, so the first, the account-data
  figure, won silently. No real client has this shape (the live figures are dated after the
  snapshots), so nothing showed it.
- **Decision:** candidates that share the latest date and disagree on amount or currency select
  nothing, following R9 (same-date, different-value joint copies are unresolved). The value cell
  becomes a marker and the review sheet gets a non-blocking conflict naming both figures. Candidates
  that agree on the amount are one answer, and the exact one is used.
- **Alternatives:** prefer the figure viewed in the meeting on the day: it is fresher in spirit, but
  the spec gives no such tie-break and it would pick silently. Prefer the account data: the old
  behaviour, equally silent.
- **Consequences / how it generalises:** a rare case now costs a marker instead of a possibly wrong
  figure, which fails safe. An undated meeting figure never ties with a dated snapshot (it is
  earlier, so the snapshot wins), and two undated candidates that differ do tie. Revisit if real
  clients hit this often enough that the tie-break is worth specifying.
- **Evidence:** `tests/test_r3_same_date_tie.py`.

### D24. Unspecified-amount markers are derived in code from the ledger, never labelled by the model
- **Context:** four markers were missing on the harder clients: ISA top-up amounts, the amount added
  to a GIA, the portion of a GIA sold, and the balance placed into a new account. Each is an amount
  the sources leave unstated, or that depends on another unstated amount. The meeting extraction
  already gives the agreed actions and disposals with their accounts and stated amounts.
- **Decision:** `reconcile/unspecified_amounts.py` builds them from those (P2, P5) and keys each by
  the account type's own wording. A funding action with no amount is a marker; a portion sold is a
  marker plus a destination review item; a new account's balance folds into the single other
  unspecified marker that feeds it, and is its own marker when several do. The model labels no
  "basis" and types no marker (D1/P1).
- **Alternatives:** an `amount_basis` field the model fills in ("stated", "full allowance",
  "unspecified"): it reads "use both allowances" against "fund both ISAs" more reliably than a word
  list, but it puts a judgement that decides whether a marker exists into the model, adds a live
  refresh, and reintroduces the run-to-run variance D22 spent effort removing.
- **Consequences / how it generalises:** a funding action is recognised by a short word list, so an
  unusual verb ("earmark") yields no marker; the list errs towards a marker, which fails safe. The
  fold-or-separate rule for a new account's balance is a convention, chosen to match the two
  reference clients, not derived from a principle. Revisit if held-out clients show missed or
  spurious markers.
- **Expected file:** client 04's `eval/expected` file gained `new_account_charges`. The basis is
  DESIGN.md `required_markers` ("for each new account, its charges", unconditional) and client
  03's SCOPING entry, not that the pipeline emits it. Client 04's SCOPING wording ("plus the new
  account's if on another") is conditional and about the platform rate, so on its own it does not
  settle the point; the general rule does.
- **Also routed:** `money.*` facts now go to Recommendations (DESIGN's own `"money.*"` example), so
  the received, available and excluded money reaches the writer. Without it client 03's
  "together with the inheritance" action had no inheritance fact to state and failed G8.
- **Evidence:** `tests/test_reconcile_unspecified_amounts.py`.

### D25. A permitted disposal-proceeds sentence is not a G7 finding, decided in code
- **Context:** client 03's Recommendations state the counted proceeds of a full disposal, then the
  P5 timing caveat ("gross before any CGT and becomes available once the disposal completes").
  The release judge flagged the first sentence under G7, in every sample, as allocating money
  that is not yet available, so the report failed. SCOPING P5 allows full-disposal proceeds to count as
  funding once amount and destination are known, described as gross, before CGT and not yet
  realised; G7's target is external or contingent money.
- **Decision:** `is_permitted_proceeds_sentence` (`gates/judge.py`) drops a G7 finding only for the
  writer prompt's fixed form, "[We recommend] using the [gross] proceeds of <a proceeds fact's
  rendering> to <what to do>", where the rest of the sentence names no other figure and no
  contingent money, and every copy of the sentence is directly followed by the caveat sentence
  (pattern in `config/standard_wording.json`). Every other G7 finding is kept. The
  sentence is not hidden from the judge: G8 needs it to check the action is covered.
- **Alternatives:** redact the sentence from the judge's input like G16's standard wording: G8
  would then report the disposal action as uncovered, and the judge would see the caveat without
  what it qualifies. Add a rule to the judge prompt: leaves a model to follow it, on the gate whose
  variance D22 spent effort reducing. Change the writer's wording: the sentence already follows
  P5 and the writer prompt; the disagreement is the judge's.
- **Consequences / how it generalises:** an independent verifier found the first version too
  loose (a sentence adding a bonus or an expected inheritance to the proceeds was exempt); the
  fixed-form and no-other-money conditions closed that. Contingent money is recognised by a short
  word list, so an unlisted phrasing is not caught by the exemption's own check, though it is
  still a G7 finding to any judge sample that flags it once the sentence is not the fixed form.
  It keys on one caveat wording, the writer prompt's fixed sentence; a reworded caveat loses the
  exemption and fails safe. Revisit if the writer's wording changes.
- **Evidence:** `tests/test_g7_permitted_proceeds_sentence.py`,
  `tests/test_g7_proceeds_carveout_narrowing.py`.

### D26. A sequential `--fresh` batch is order-dependent, so the committed cache is built once
- **Context:** for the final fresh run I regenerated the four clients with `--fresh` in one batch.
  Copied back and replayed offline, the release judge missed the cache and went live with a new
  verdict. Clients share cache keys when their inputs are identical (the same general documents
  classified for each), the model is not deterministic, and `--fresh` rewrites every entry. So a
  later client overwrote a shared entry with a different response, and an earlier client's replay
  followed the overwritten one and diverged. Only the downstream judge input showed it. One client
  run fresh and then replayed matched on every call, which located the cause in the sequence.
- **Decision:** the committed state stays the one whose outputs, cache and results file were built
  together and replay offline. I did not commit the fresh batch, and I did not re-run it until four
  drafts came out. Replay tests now cover every client (`tests/test_pipeline_replay*.py`), so a
  missing or stale entry fails offline.
- **Alternatives:** keep the fresh batch as the outputs: it does not replay, so the offline guarantee
  is lost. Run the four clients from an empty cache in one non-fresh batch, so each shared entry is
  generated once and reused: consistent by construction, and I ran it. It flagged a clause in client
  03 that matches the meeting note, so its verdict was a judge false positive (D22), not a wrong
  report. Committing it would have left a failed client 03, and re-running until it passed would have
  been resampling for a verdict, so I did neither.
- **Consequences / how it generalises:** a fresh regeneration can change any client's judge verdict,
  and a report that failed only that way is not a real failure. The safe procedure is an empty cache
  and one non-fresh batch, replay-checked per client before anything is committed. The judge's
  non-repeatability is documented, not hidden: it is D22's residual, and the fix is a deterministic
  judge.
- **Evidence:** `tests/test_pipeline_replay.py`, `tests/test_pipeline_replay_client_02.py`,
  `tests/test_pipeline_replay_client_03.py`, `tests/test_pipeline_replay_client_04.py`.

### D27. Open a question only for a singular mention that names two or more in-scope accounts
- **Context:** the design opens a question for a meeting mention that maps to no account or to several.
  The extraction's `accounts_mentioned` list is loose: it holds new accounts, loans, a solicitor's
  client account, plural references ("both ISAs") and old accounts outside the report. Matching every
  one against the account data would open questions on the real clients, each needing a live model
  call, which their committed cache and replay tests do not contain, and most could not change a
  report.
- **Decision:** `reconcile/questions.py` opens an `account_link` question only when the mention is
  singular (no "both", "all", "their", "and", or a number word) and its wording (type, platform or a
  holder's first name) leaves two or more open, in-scope accounts. A mention that names nothing an
  account has opens nothing, and neither does one with at most one in-scope candidate, since a link to
  an out-of-scope account cannot change the report. The question carries the accounts other mentions
  already pin down; elimination by those is one of the checks in `accept.py`.
- **Alternatives:** open a question for every unmatched or multiply matched mention, as the design
  reads: it fires on the real clients and mostly on things the report never shows. Let the model mark
  which mentions are accounts: that changes the extraction schema and prompt, and so stales every
  client's cache.
- **Consequences / how it generalises:** the four real clients open no question, which their existing
  replay tests enforce (a question would need a live call). The cost is a narrower trigger than the
  design: a mention that maps to no account, or an ambiguity only outside scope, is not investigated,
  and the plural and number-word lists are English wording. Only account links are opened; label
  questions have their acceptance rule but nothing opens them yet.
- **Residual risk, accepted:** a link is accepted by elimination (DESIGN.md section 5.2 step 3, "no
  contradictory mapping"): the one candidate that no other mention already identifies, on a
  verified quote in or next to the mention's paragraph. Elimination can mislink when the note
  never names the account, for example if two mentions in different words are one account. I keep
  it because the case it serves, an "other account on that platform" that the note never names,
  has no other answer, and because the output cannot become a silent fact change: it is a
  non-blocking "changed by investigation" review item that shows the default it replaced and the
  quote, so the adviser sees it and can correct it. Requiring the quote to name the proposed account
  would be safer and would leave that case unresolved. A quote must also be at least three words,
  because an empty string is a substring of every paragraph; a short but real quote from the
  neighbouring paragraph still counts. Revisit if a held-out run reports a non-zero
  accepted-and-wrong.
- **Evidence:** `tests/test_reconcile_questions.py`, `tests/test_investigate_stage.py`.

### D28. Build the rules the hand-written cases expose in code, and record where each stops
- **Context:** the first run of the 17 non-agent hand-written cases (DESIGN 10.6) passed few of
  them. The failures were mostly missing deterministic rules (R3's recalled figure, R4, R5, R8, R9,
  R10, P11, section 8.4 degradation), not model errors, plus two defects in my own earlier rules: D24's portion-sold
  marker fired when the note stated the amount, and its funding-word list read the noun "fund" as a
  verb. A held-out client is exactly a shape like these.
- **Decision:** each is a pure function with tests first (`reconcile/decisions.py`, `meetings.py`,
  `scope_parts.py`, `degradation.py`, the R5 and R9 wiring in `pipeline.py`, P5's stated portion in
  `money.py`). None re-labels anything by model. The four real clients' committed outputs and cache
  are untouched, and their replay tests enforce it: a rule that changed one of them was reworked
  (P10's fuller wording applies only to a statement row that prints a currency code, which was
  previously dropped silently; a leading client name is accepted only after the writer's repair
  rounds, so a first answer that was corrected keeps the wording it always had).
- **Alternatives:** tune the extraction or writer prompts until the cases pass: it fits the cases
  and hides the missing rule. Loosen the eval checks: three eval-side changes were made, each
  approved before it was made and none loosening what a case must contain: a bracketed marker table
  cell is read as "marker" (as the pipeline's own truth names it), an expected review item's terms
  match case-insensitively, and two expected files gained the always-allowed initial charge.
- **Where each rule stops** (found by an independent review, and recorded rather than hidden): R5
  compares the instruction's one exact figure with the one funding action that states an amount, and
  cannot tell a total from one part of it, so it can raise a false blocking conflict; P5 attributes a
  stated proceeds amount only to a sole disposal, in sterling and no larger than the account; R8
  knows account types by the wording in `config/account_types.json`; R10 orders records by their
  extracted date and, on equal dates, by input order; the funding-word and "within" lists are
  English wording and err towards a marker.
- **Consequences / how it generalises:** the cases are a measure, not a target: a pass here means a
  rule exists, not that a client with a different phrasing will pass. The judge's non-repeatability
  (D22) still fails a case that the rules handle correctly.
- **Evidence:** `tests/test_p5_stated_portion_amount.py`, `test_r9_joint_copies.py`,
  `test_r5_instruction_vs_meeting_amount.py`, `test_r4_selling_decision.py`,
  `test_r8_unresolved_scope_part.py`, `test_r10_meeting_records.py`,
  `test_p11_tbc_computed_fields.py`, `test_degradation_missing_fields.py`,
  `test_task_b_review_fixes.py`, `test_eval_checks_approved_fixes.py`.

### D29. Pass handling notes to the writer as verified directives, and drop any that fail a check
- **Context:** D8 was unbuilt: the internal notes were used only to check the report did not leak
  them (G10). Client 03's notes ask that the origin of its new money be treated sensitively, and
  the notes' other lines only describe data sources. So the client-specific line reached no writer.
- **Decision:** one extraction call reads the notes and proposes directives (sections, one
  instruction, the person, the note's own words as evidence). Code keeps a directive only if the
  evidence is a verbatim quote of the notes, the sections exist, a named person resolves to a holder,
  and the instruction shares no six-word run with the notes. The writer gets the instruction line
  only, never the notes. A directive that fails on the person or the wording becomes a non-blocking
  review item; one with no verbatim evidence or no valid section is dropped without one.
- **Alternatives:** pass the notes' client-specific paragraph to the writer with "never quote this"
  (the leak defence would rest on the prompt alone; already rejected in D8); a directive with an
  unresolved person kept without the name (the instruction may only make sense for that person, and
  D8 says an unresolved person is a review item, not a guess).
- **Consequences / how it generalises:** a client with no client-specific notes gets an empty list, and
  its writer inputs carry no `handling` key, so its cache keys do not change for that reason. The six-word
  run is the same length G10 uses, so this is a check one step earlier, not a stricter one: a leak of
  five words gets through both. Revisit if a rebuilt report shows a directive's wording in the text, or
  if a valid directive is dropped as a false leak.
- **What the rebuild showed:** client 03's directive (refer to the origin of the new money with
  care) was extracted, verified and applied. The first build routed it to Background & Objectives only,
  while the inheritance is discussed in Recommendations, and its wording carried a fact from the internal
  notes (a bereavement), which the independent review flagged as a route for a client fact from internal
  guidance into the report. The extraction prompt now asks for every section that mentions the subject,
  and forbids an instruction from stating a circumstance, event, reason or amount, in digits or words
  (the word forms are also refused in code). The directive now reaches both sections and reads "refer to
  the source of the new funds in restrained, sensitive language". The rubric judge's Q3 for client 03 is
  still 2 in the results file, because it wants the report to mention the bereavement, and that fact is
  only in the internal notes: a report that stated it would break the rule that guidance text never
  appears. I treat that score as one the rules prevent me from raising. Routing is still chosen by the
  model, with no code check that the named sections mention the subject ("What I would do with more
  time").
- **Also fixed:** the review sheet printed only some note kinds, so an applied `handling_note`, and every
  `ambiguity` item (several modules produce them; six items across five committed outputs), were in the
  ledger but never shown. `assemble._NOTE_KINDS` now includes both, so a note the run could not apply
  ("check it by hand") is no longer silent. The cost, found by the independent review: the sheet now
  also shows the investigation stage's plural-reference flags ("'Stocks & Shares ISAs' could mean any
  of ..."), which are over-flags and sit on clean cases. I kept them visible and listed the over-flagging
  under "What I would do with more time". A note naming a first name two holders share is no longer
  applied to whichever comes first: it becomes a review item.
- **Evidence:** `eval/results/20260930T184615Z_99cef32.json` (client 03's `q_scores`), the tests for
  guidance extraction, handling plumbing and the review sheet's handling notes; commit `543a507`.

### D30. Build marker descriptions in code from the ledger, naming the account and the holder
- **Context:** the eval judge's Q5 (is each marker actionable) scored client 03 and client 04 low in
  `eval/results/20260930T114259Z_81f0089.json`: the CGT marker did not say which disposal, the SIPP
  marker did not say whose contributions, and the new-account marker said "charges" without saying
  which. The marker text is inserted into the client's report, so it is wording a client can read.
- **Decision:** `reconcile/marker_text.py` builds the text from accounts and holders: the joint account
  as "the joint <type>, <platform>", a single holder's as "Ann's <type>, <platform>", first names unless
  two holders share one, "platform not stated" when the platform is unknown, the SIPP marker as "for
  James and for Caroline, each", and the new-account marker as "platform charge and advice charge rates
  for the new joint account held by A and B". No figure appears. There is still one marker per expected-
  facts key, so the eval's contract does not change.
- **Alternatives:** let the writer describe the marker (it does not type facts, and this text goes to
  the client); one marker per holder (changes the keys and the one-marker-per-key rule).
- **Consequences / how it generalises:** marker text is a writer and judge input, so this changed cache
  keys and needed one rebuild (D26). "in-scope", our own word, is gone from client-facing text. Two
  gaps from the independent review are closed: a disposal that matches no account is no longer dropped
  from the CGT marker (it adds "and on any other disposal in this advice"), and two holders who share a
  first name are named in full. Not closed: a new joint account lists every holder as an owner, so a
  client with three holders reads "held by Ann, Ben and Carl" (an older assumption, now visible).
- **Evidence:** the marker-text tests; the Q5 for each client is in
  `eval/results/20260930T184615Z_99cef32.json` and the before/after in `eval/progression.md`
  (the baseline has no markers, so its Q5 is n/a); commit `46b8166`.

### D31. Match a statement row to a same-type account by owner, then platform, and leave the rest unmatched
- **Context:** two accounts of one type held by the same people on different platforms could not be told
  apart from a statement row's label (P10), so the row stayed unmatched.
- **Decision:** `match_image_row` narrows by owner first. Only if two or more accounts still match does it
  narrow by the platform named in the label, as a whole word, and it matches only a unique result. A label
  that names someone who holds neither account is never matched by platform.
- **Alternatives:** a substring match on the platform ("North" would match "Northgate": a value attached
  to the wrong account, which is a wrong figure); ask a model to choose (the answer has a right value, so
  code decides).
- **Consequences / how it generalises:** an unmatched row is safe, since a report uses a statement value
  only after it matches, so this can only let more rows match. A label that names only a platform both
  accounts share stays unmatched.
- **Evidence:** the image-row platform tests; commit `edab959`.

### D32. Give the recommendation writer rules for money roles, reasons and repeats, and fix what each rebuild broke
- **Context:** the recommendation slot receives received, committed, available and excluded money, and the
  prompt had no rule about which role may be stated how; only G7 and G8 caught a misuse, and a failed
  generation on a correct client is what D22 warns against.
- **Decision:** rule 5 uses each money fact only for its role and never presents a total across actions as
  one action's amount; rule 6 gives a reason only when the note or context states one; rule 7 says each
  recommendation once and never drops an agreed action, a non-action included. Rule 2 (the proceeds
  sentence, D25) gained three lines over the rebuild: state the disposal first in its own sentence, add no
  other funding to the proceeds sentence, and attach the proceeds only to the action whose text they fund.
- **What broke, each found by a live pass and fixed in the prompt rather than by resampling:** a total
  read as one action's amount (client 03); a non-action dropped (cases 12 and 15); extra funding in the
  proceeds sentence and the disposal itself dropped (client 03); the proceeds attached to the new account
  instead of the two ISAs the action text says they fund (client 03, G8). One break no gate caught: the
  rule that other funding goes in a separate sentence made client 03's report say the inheritance "will
  also fund both ISAs" beside the proceeds, which reads as money on top of them. The independent review
  found it; rule 2 now says other money an action text joins to the proceeds is stated as used together
  with them for that same action, and rule 5 allows a link between a sum and an action only where an
  action text gives it. The role line no longer asks for "and why" against rule 6 (a reason only where an
  input states one): the recommendation slot is given no objectives, so a reason could not be met, and
  Q1 stays at 2 to 4 (recorded under "What I would do with more time").
- **Alternatives:** leave it to G7 and G8; render the recommendation sentences from a code template
  (removes the model from the slot, and would also remove D25's dependence on the caveat wording; it is
  under "What I would do with more time").
- **Consequences / how it generalises:** every recommendation cache entry changed, so this was part of
  the one rebuild (D26). Prompt wording is not proof: each rule was checked on the four clients and 20
  cases, not on a held-out client. Rule 7 first used "the holding" as its example, which taught the
  writer a generic noun; it now says what to write when an action names nothing (D33).
- **Evidence:** commit `543a507`; gates and Q scores in `eval/results/20260930T184615Z_99cef32.json` and
  `eval/results/20260930T184620Z_7ad73ee.json`; the first-attempt failures are recorded in D22.

### D33. Leave a non-action's referent to the writer; do not name it from the extracted accounts
- **Context:** on client 04 the report says "We recommend leaving the holding as it is", straight after a
  recommendation about a Holloway GIA, when the note means the offshore bond, and the rubric judge's Q2
  for client 04 fell (`eval/results/20260930T184615Z_99cef32.json`). The ledger action carried
  `accounts: ['offshore bond']`, so I made the plan add "(this concerns: ...)" from that field.
- **What happened:** it fixed client 04 (the report then said "the offshore bond"). Case 17 broke: its
  action "We agreed to leave this for now and revisit if it becomes relevant" carries `accounts: ['one of
  his General Investment Accounts on Holloway']`, the account a paper share certificate relates to, while
  "this" is the certificate. The writer said an account was being left alone, which the meeting note
  never says, and G8 and P6 failed on all three judge samples: a real defect, not judge noise. The two
  actions look the same in the ledger; only what they mean tells them apart.
- **Decision:** withdrawn. `write/plan.py` passes a non-action's text as extracted, and a test keeps the
  annotation out. The independent review then showed that "the holding" really does contradict the
  sentence before it on client 04 (it reads as "do not touch the GIA"), so the prompt changed instead:
  when an action names nothing, rule 7 has the writer say "we recommend making no other changes at
  this time, as agreed", never "it" or a generic noun. Client 04 now reads that way.
- **Alternatives:** keep the annotation where the wording is "it" rather than "this" (a wording guess);
  use the extracted account only when it resolves to exactly one in-scope account (the review's
  suggestion: it fixes client 04 and leaves case 17 alone, but a certificate tied to a client's only
  GIA would again read as that account being left alone, so I did not); have the extractor put the
  referent into the description (the right fix, but it changes every extraction cache entry, so it
  needs its own rebuild: under "What I would do with more time").
- **Consequences / how it generalises:** a held-out client with a pronoun-only non-action gets a
  sentence that names nothing, not a wrong one. The cost is specificity: client 04's report no longer
  says which holding is left alone. The failed case 17 draft was not committed: its outputs were
  replaced by the replay once the change was withdrawn.
- **Evidence:** the non-action referent test; commit `cd88bad`.

### D34. Check how many accounts the Introduction names, in the writer and in code, and state the count
- **Context:** after the first rebuild, case 17's Introduction said "the General Investment Account held
  by Bernard" for a report that covers two. The scope check (`intro_scope_problems`) only asked whether
  each in-scope type was named, so nothing caught it, and all 22 gates passed on a wrong scope sentence.
- **Decision:** the check now also requires a plural, or one mention per account, for a type held more
  than once, and the writer runs it in its repair rounds (`write_slot`) so the model repairs the slot,
  not the release judge finding it late. Stricter alone stopped case 17: the scope writer is told to
  use `context.scope_description` and never invent a number of accounts, and that description listed
  two identical labels, which it collapsed. `_describe_scope` now groups accounts that would read the
  same and states the count ("Bernard's two General Investment Accounts"). No other ledger's
  description changed.
- **Alternatives:** leave it to the release judge (it passed the wrong sentence); build the whole scope
  sentence from the ledger in code (the real fix in D22's "known gap", larger than this change).
- **Consequences / how it generalises:** a count mismatch is repaired or stops the run, never shipped;
  the count word list stops at eight ("several" beyond), and accounts that differ only by an unstated
  detail are still told apart only by owner and platform.
- **Evidence:** the multiplicity and scope-description tests; commits `4b24744` and `8f72ca6`.

### D35. Record what the independent review found, and what I fixed and did not
- **Context:** after the marker, matcher, directive and writer changes were committed with the
  reports rebuilt and all 22 gates green, the opus verifier (run as you asked, before the final commit)
  returned FAIL on three regenerated reports that gates had passed: client 03's funding sentence,
  client 04's "the holding", and case 17's introduction.
- **Fixed, each test-first where it is code:** client 03's funding wording (D32); case 17's scope count
  (D34); the image-row matcher giving a joint row to a sole account (D31: every named holder must hold
  the chosen account, and the earlier platform tests named nobody in the label so could not fail: new
  tests name owners, and the two old ones are left in place because editing a committed test is yours to
  approve); the CGT marker dropping an unmatched disposal and first-name collisions (D30); a handling
  instruction carrying an amount in words, and the prompt letting an instruction state a client
  circumstance (D29); the "and why" contradiction (D32); client 04's "the holding" (D33).
- **Not fixed:** a directive's routing is still chosen by the model; the extractor does not resolve a
  non-action's referent; the recommendation slot receives no reasons, so Q1 stays low; the review
  sheet exposes the investigation stage's over-flags; the review reports four more review-item kinds
  (`joint_value_conflict`, `account_missing_field`, `money`, `account_link`) that are recorded and not
  printed, which I have not verified; a new joint account lists every holder as an owner. Each is under
  "What I would do with more time".
- **Two of the review's three questions I decided rather than asked:** the three regressions were
  already in committed history when the review ran, and the final outputs replace them (I did not keep
  them as they were); for client 04 I used a neutral sentence, not a marker placeholder. The third, whether the recommendation slot should receive the objectives so a
  reason can be given, changes what the writer may say about why and needs a measured pass, so it is
  left open.
- **Consequences / how it generalises:** gates passing is not evidence the report is right: three wrong
  statements passed 22 of 22. The reports were read against their sources after each rebuild from then on.
- **Evidence:** the verifier's findings are not committed (it is read-only and its report lives in the
  session); the fixes are commits `e3a6ebe`, `dc1eef3`, `4b24744`, `6ecf335` and `8f72ca6`.

## What I would do with more time
- **Run the Luna-versus-Sol comparison (D2).** Every pipeline stage runs on Luna and only the eval judge
  on Sol, but that was never compared: no run has a pipeline stage on Sol. Run extraction, the release
  judge and the investigation agent (D14) on both over the four clients and the hand-written cases with
  `--stage-models`, and record each Sol upgrade with its cost next to the accuracy it buys (D12). It
  costs money, so it needs its own go-ahead.
- **Widen the investigation agent (T22, D14, D27).** Built, with one question kind (an ambiguous account mention). On the hand-written cases (`20260929T162142Z_3ce9edb.json`) it raised 4 questions: 2 in the cases built to raise one, both handled as expected, and 2 that no case expects, both left unresolved. 0 were accepted-and-wrong. Not yet opened: label questions (a viewed-versus-recalled basis), whose acceptance rule and tests exist, and a mention that maps to no account. A broader trigger needs the real clients' cache refreshed, since each new question is a model call.
- **Route handling directives by where their subject appears (D29).** The guidance extractor is built, but
  a directive is routed to the sections the model names. Client 03's sensitivity note reached Background
  & Objectives only, while the inheritance is discussed in Recommendations, so Q3 for client 03 is still
  2 in the results file. A check that finds the sections that mention the directive's subject, and sends
  it to each, would fix that.
- **Have the extractor resolve a non-action's referent (D33).** "We agreed to leave it as it is" carries
  no noun, and the extracted `accounts` is the account the action is tied to, not always what it
  concerns. Resolving the referent into the description at extraction would let client 04's report say
  which holding is left alone instead of "no other changes". It changes every extraction cache entry,
  so it needs its own rebuild.
- **Give the recommendation slot the reasons (D32, D35).** It receives no objectives, so it can give a
  reason only from an action text, and Q1 (does the section say what to do and why) is 2 to 4 in the
  results file. Sending it the objectives is a measured change: a reason is also a place to state
  something the sources do not support (P6, an aspiration presented as a recommendation).
- **Stop the investigation stage flagging plural references (D29).** "Stocks & Shares ISAs could mean any
  of ..." means all of them; now that the review sheet prints `ambiguity` items, it shows on clean
  cases. Print the other review-item kinds the independent review reports as recorded and not shown only
  after deciding which of them an adviser needs, since a sheet that lists everything is not read.
- **A deterministic judge (D22).** `config/models.json` records `temperature_accepted: false` for
  both models on this key (`gpt-6-luna` and `gpt-6-sol`), so no available model can give a stable verdict. The fix is a
  judge on a model that accepts `temperature=0`, or a smaller judge surface still: build the
  Introduction's scope sentence from the ledger and remove that model-written slot.
- **The G7 carve-out depends on one caveat wording (D25).** A proceeds sentence is exempt only when the
  writer prompt's fixed timing caveat follows it. A reworded caveat loses the exemption and fails safe
  into a false G7 failure. Rendering that sentence and its caveat from a code template would remove the
  dependence.
- **R4/R5 pair by count, not by meaning.** The instruction-versus-meeting rules are wired (D28). R5 compares the instruction's one exact figure with the one funding action that states an amount, and cannot tell a total from one part of it, so it can raise a false blocking conflict that the adviser then settles. Pairing them by the account the money goes to would fix that.
- **Run the generated synthetic clients.** The 20 hand-written cases are run and scored (D28). The generator and phrase bank (D4) exist and are covered by offline tests, but no generated client has been run through the live pipeline and scored, so behaviour on unseen shapes beyond the hand-written ones is unmeasured: the funding-word list (D24) may over-mark, and the new-account scope check depends on the instruction's wording.

- **PII minimisation before the API boundary.** Not built, because it touches every model input
  and this data is synthetic. Sent today: classify and extract get client and holder names,
  account IDs, values and the full meeting text; the writer gets names and account types but no
  figures (D1); the release judge gets the report and the source paragraphs. First step:
  tokenise names and account IDs at the writer and judge boundary, resolved from the ledger in
  code, extending the D1 fact tokens. The extractor is the hard case, since its job is to quote
  names from prose: it needs a reversible per-run map, with quote verification (D9) run against
  the unmasked source. A local scrubber would strip what the pipeline never uses (addresses,
  phone numbers, dates of birth). Measure it by re-running the four clients and the 20
  hand-written cases before and after and comparing gate results and Q scores, knowing that every
  prompt input changes, so the whole cache rebuilds (and D26's order-dependence applies). A
  data-processing agreement with the provider remains the primary control; this is defence in
  depth.

## How I worked
- **AI assistance.** I built this with Claude Code (Anthropic's CLI) working in the repo under the rules in
  `CLAUDE.md`: plan first, small diffs, tests first for deterministic code, and every decision recorded.
  Hooks enforced the rules mechanically (protected files, committed tests, live API calls, the
  quality gate at the end of each turn). An independent `verifier` subagent reviewed each change that
  touched a prompt or a trust rule, and its findings were fixed or recorded before the commit.
- **Models in the pipeline.** `gpt-6-luna` for classification, extraction, writing and the release judge, and
  `gpt-6-sol` for the eval judge only (D2).
- **Time.** About 12 hours of my time, worked on and off across four days, with Claude Code running long stretches autonomously. My time went mostly to design decisions, the data investigation, reviewing verifier checkpoints and prompt tuning, while the agent did the mechanical build. The commit history records the timeline.
