# Decisions

The hardest calls in this pipeline, why I made them, and what I would do next.

## Summary
<!-- 5–8 lines, written last: the approach in brief, the headline eval result (quoted from the
     eval output file), and the one decision you would most want to discuss. -->

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

### D2. Set the model per stage in config; choose the decisive model stages by measurement
- **Context:** the key can use gpt-6-luna ($0.10 / $0.50 per 1M tokens) and gpt-6-sol ($2 / $10), among
  others; at the time, against a $10 budget (since replaced by cost reporting, D12). The release judge
  (G8, G16) runs on every report, so its model decides both cost and which drafts are issued.
- **Decision:** every stage's model is a config setting. Luna is the default for all pipeline stages;
  Sol is the eval judge. Extraction, the release judge and the investigation agent (D14) run on both
  Luna and Sol over the four clients and the hand-written cases; a stage moves to Sol only if Luna
  measurably misses.
- **Alternatives:** Luna everywhere including the eval judge (a model grading its own output tends to be
  lenient); Sol for both judges (≈$0.14 per report, so two or three full eval runs would use most of the
  budget).
- **Consequences / how it generalises:** needs extraction to be scored on its own against expected facts
  (DESIGN §10.7). The measured outcome gets its own entry, citing both results files.
- **Evidence:** pending the §10.7 experiment.

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
  the rules themselves; hand-written cases cover the rules. ≈$0.01 per client, one-off.
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
- **Consequences / how it generalises:** ≈5 small calls per report; each section can be repaired alone.
- **Evidence:** none yet.

### D7. Classify sources by content: schema checks for structured files, a model for text documents
- **Context:** unseen clients may name files differently or add new ones (SCOPING §3); general
  documents (market updates, portfolio packs) must never feed client facts.
- **Decision:** JSON that validates as account data is classified in code; an image is a candidate until
  the vision read confirms it shows an account table; text documents are classified by Luna with a
  verified evidence quote, and low confidence makes them unknown. Unknown roles are excluded and logged.
- **Alternatives:** filename mapping (breaks on renamed files); content heuristics alone (brittle on
  unseen phrasing).
- **Consequences / how it generalises:** ≈$0.001 per report; a hand-written case with renamed files and
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
- **Evidence:** none yet.

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
  to ≈$10.25 against the $10 key: the Sol eval judge, the full Luna-vs-Sol experiment over the four clients and 14 hand-written
  cases, synthetic clients and the final `--fresh` run. A Sol result from the experiment couldn't have
  been acted on within the cap.
- **Decision:** I fund development and eval runs separately, and nothing in the plan is cut. Every run
  records its cost per stage and per report, and cost per report is a reported metric in every results
  file. The default pipeline stays cheap (Luna unless the experiment proves otherwise, plus the
  committed cache), so a reviewer's re-run costs cents.
- **Alternatives:** a Luna eval judge while iterating and Sol only to confirm, with a reduced experiment
  (≈$5.50, but weaker evidence for D2); dropping the synthetic clients (still tight, no room for a Sol
  upgrade); skipping the experiment and staying on Luna (reverses D2).
- **Consequences / how it generalises:** any Sol upgrade is recorded with its cost next to the accuracy
  it buys. CLAUDE.md is updated to match; the `run-eval` skill's "$10 budget" wording still needs the
  same change. The `--estimate` step before live batches stays.
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
  hand-written ambiguity cases and included in the Luna-vs-Sol experiment; costs nothing when no
  question is open. Accepted-and-wrong (a finding code accepted that contradicts expected facts) is a
  headline metric in every results file, reported apart from general accuracy; a non-zero figure is the
  evidence that would make us restrict the agent to annotating.
- **Evidence:** none yet.

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
- **Evidence:** `bash scripts/check.sh` green (350 tests, all repo checks pass) after the change.

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
- **Evidence:** `tests/test_write_writer.py` (24 tests, all slot-level gate paths), `bash
  scripts/check.sh` green (472 offline tests) after the change.

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
  All three release-judge samples flagged the first sentence under G7 as allocating money that is
  not yet available, so the report failed. SCOPING P5 allows full-disposal proceeds to count as
  funding once amount and destination are known, described as gross, before CGT and not yet
  realised; G7's target is external or contingent money.
- **Decision:** `is_permitted_proceeds_sentence` (`gates/judge.py`) drops a G7 finding whose quoted
  sentence states a "sale proceeds" fact's own rendering and is directly followed by the caveat
  sentence (pattern in `config/standard_wording.json`). Every other G7 finding is kept. The
  sentence is not hidden from the judge: G8 needs it to check the action is covered.
- **Alternatives:** redact the sentence from the judge's input like G16's standard wording: G8
  would then report the disposal action as uncovered, and the judge would see the caveat without
  what it qualifies. Add a rule to the judge prompt: leaves a model to follow it, on the gate whose
  variance D22 spent effort reducing. Change the writer's wording: the sentence already follows
  P5 and the writer prompt; the disagreement is the judge's.
- **Consequences / how it generalises:** narrow by construction: the figure must be a proceeds
  fact's, and the caveat must be the very next sentence, so a real allocation of unrealised money
  elsewhere still fails. It keys on one caveat wording, the writer prompt's fixed sentence; a
  reworded caveat loses the exemption and fails safe. Revisit if the writer's wording changes.
- **Evidence:** `tests/test_g7_permitted_proceeds_sentence.py`.

## What I would do with more time
<!-- For production: what's missing, what you'd change in the pipeline and the agent setup,
     and the risks you know about. Concrete, not a wish list. -->

## How I worked
<!-- Tools used, including AI assistance; roughly how long it took. -->
