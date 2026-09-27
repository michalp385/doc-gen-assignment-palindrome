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

### D2. Set the model per stage in config; choose extraction and the release judge by measurement
- **Context:** the key can use gpt-6-luna ($0.10 / $0.50 per 1M tokens) and gpt-6-sol ($2 / $10), among
  others, against a $10 budget. The release judge (G8, G16) runs on every report, so its model decides
  both cost and which drafts are issued.
- **Decision:** every stage's model is a config setting. Luna is the default for all pipeline stages;
  Sol is the eval judge. Extraction and the release judge run on both Luna and Sol over the four clients
  and the hand-written cases; a stage moves to Sol only if Luna measurably misses.
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
  findings (≤2 rounds). Running out of rounds is a failed generation, never a guess.
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
- **Decision:** JSON that validates as account data and images with an account table are classified in
  code; text documents are classified by Luna with a verified evidence quote. Unknown roles are excluded
  and logged.
- **Alternatives:** filename mapping (breaks on renamed files); content heuristics alone (brittle on
  unseen phrasing).
- **Consequences / how it generalises:** ≈$0.001 per report; a hand-written case with renamed files and
  an extra unknown document tests it.
- **Evidence:** none yet.

### D8. Turn the internal guidance into a structured handling directive; the writer never sees its text
- **Context:** G10 forbids internal guidance text in the report; client 03's notes ("the recent death of
  her mother") must shape tone without being quoted, and call Jean "the client" though the account data
  makes Robert the `client`.
- **Decision:** extraction reads only the "This client" section into a directive (sections affected,
  instruction, the person by name). The writer receives the directive, never the notes.
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

### D11. Decide section inclusion in code: `use_if` becomes a ledger predicate
- **Context:** the baseline asked a model whether each conditional section applies. G5 is deterministic
  (taxable disposal, or a conflict about one), so inclusion has a right answer.
- **Decision:** keep the config contract (`template`, `<<slot>>`, `placeholders`, `use_if`), but `use_if`
  is `"always"` or a reference to a ledger decision. Report configs `extends` a base and reuse section
  files, so a second report type doesn't duplicate shared parts.
- **Alternatives:** keep plain-language `use_if` evaluated by a model (non-deterministic inclusion,
  unexplainable when wrong).
- **Consequences / how it generalises:** every inclusion decision is explained in the review sheet with
  its evidence (SCOPING §8).
- **Evidence:** none yet.

## What I would do with more time
<!-- For production: what's missing, what you'd change in the pipeline and the agent setup,
     and the risks you know about. Concrete, not a wish list. -->

## How I worked
<!-- Tools used, including AI assistance; roughly how long it took. -->
