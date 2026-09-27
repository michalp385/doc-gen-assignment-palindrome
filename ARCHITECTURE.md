# Architecture
<!-- A map, not the territory. Readable in ~10 minutes. Details and trade-offs: DESIGN.md.
     Update when module boundaries, data flow or invariants change. -->

## Bird's-eye view
A client folder goes in. Code classifies each file by what it is (a model helps with text documents),
models read the unstructured sources into quote-anchored facts that code verifies, and code reconciles
them under the trust rules into one typed facts ledger. Code decides inclusion, builds the account
table and inserts every marker; a model writes each section's prose using fact tokens, never numbers,
and code fills them from the ledger. Deterministic gates and a release judge decide whether the result
is a draft for adviser review or a failed generation. Out come the report, a review sheet, the ledger
and a run summary.

## Code map
Status: proposed in DESIGN.md §12; modules are created by the implementation plan. Until then the
starter path (`agent_pipeline/generate.py` + `document_formatter/`) is what runs.

- `agent_pipeline/generate.py`: CLI. Parses arguments, builds the run, calls `pipeline.run`. Must not
  hold pipeline logic.
- `agent_pipeline/pipeline.py`: the fixed stage graph and run context. Owns stage order and the
  bounded loops. Must not decide facts.
- `agent_pipeline/llm.py`, `cache.py`: the one LLM client (structured outputs, cache, retries, cost,
  trace). The only module that imports `openai`.
- `agent_pipeline/config.py`: loads report configs (`extends`), prompts and their content-hash
  versions, stage model settings.
- `agent_pipeline/sources/`: role classification and one adapter per file format. Must not extract
  client facts.
- `agent_pipeline/extract/`: one extractor per role (meeting, instruction with scope mapping, guidance,
  image, and a proposed scope mapping), with quote/date/label verification. Returns verified raw facts;
  never selects between sources and never decides scope (the scope checks run in `reconcile/scope.py`).
- `agent_pipeline/ledger.py`: ledger models and value rendering. No I/O beyond (de)serialising.
- `agent_pipeline/reconcile/`: the trust rules and policies, one function per rule. Pure code, no model
  calls. Emits open questions where more evidence could change an outcome.
- `agent_pipeline/investigate/`: the conflict investigation agent. A bounded loop with read-only tools
  that returns quoted findings per open question, and the code that verifies and accepts or rejects
  them. Must not write to the ledger, select a value or change a rule; accepted evidence goes back
  through `reconcile`.
- `agent_pipeline/write/` (T14): `plan.py`'s `plan_sections` resolves each included section's
  config-declared `facts`/`markers`/`excluded` glob selectors (`config.Section`) against the ledger
  into a `SectionPlan` (`schemas.py`), rewriting every extraction-derived text digit-free first
  (a matched fact's quote becomes its token; anything else with a figure is withheld and logged).
  `writer.py`'s `write_slot` makes one model call per generated placeholder (D6), checking in
  order -- invented tokens, digit-free, required markers exactly once, then its own slot-scoped
  G4/G9/G10/G11/G12 checks (D19: reuse T9's `gates/deterministic.py` regexes/constants, not a
  faked `ReportBundle`) -- with ≤2 repair rounds before `WriterStopError`. `tokens.py`'s
  `fill_tokens` and `table.py`'s `build_table` (P9) substitute from the ledger afterwards. The
  writer never sees a number.
- `agent_pipeline/gates/`: `truth.py`'s `Truth` protocol (`ExpectedTruth` wraps expected facts,
  `LedgerTruth` wraps a real run's ledger) and `deterministic.py`'s `run_gates(bundle, truth) ->
  list[GateResult]` (T9: G1-G6, G9-G15, P6). The release judge (G7-judge-part, G8, G16, the
  paraphrase/n-gram findings) is not built yet.
- `agent_pipeline/assemble.py`: outputs, review sheet, run summary; release state.
- `document_formatter/formatting.py`: final markdown assembly. Protected, unchanged.
- `report_eval/`: eval runner, expected-facts schema (`expected.py`), the deterministic stub writer
  (`reference.py`, T9: builds a client's reference bundle straight from its expected facts, no LLM),
  extraction scoring, judge rubric, results files, mutations, synthetic client generator (`synth/`).

## Data flow
1. `generate.py` loads the report config and the client folder.
2. `sources` classifies each file into a role; unknown files are logged and excluded.
3. `extract` reads each role's sources into quote-anchored facts and maps scope phrases to accounts;
   code verifies quotes, parses amounts and dates, checks decisive labels' evidence and checks the
   scope mapping (≤3 correction rounds).
4. `reconcile` (code only) applies R1–R10 and P2–P12 and writes the ledger: accounts, selected and
   superseded values, money classes, actions, markers, review items, section decisions, and open
   questions. `investigate` gathers quoted evidence for each open question (≤5 questions, ≤6 tool calls
   each); code verifies it, and `reconcile` re-runs with what it accepts.
5. `write.plan` gives each included section only its own facts (with allowed roles), markers and
   directives, with every input rewritten digit-free.
6. `write.writer` produces each generated slot with fact/marker tokens; section gates run; failures go
   back for repair (≤2 rounds).
7. Tokens are filled from the ledger; code builds the table and footnote; `formatting.py` assembles the
   draft.
8. Every deterministic gate runs on the draft, then the release judge; one repair round if a section is
   flagged.
9. `assemble` writes the draft or the failed-generation file (removing the other), the review sheet,
   the ledger, the run summary (cache hits vs live calls, cost per stage) and the per-stage record.

## Invariants
<!-- The verifier checks diffs against these. Promote each to a check where you can. -->
- Static regulatory text (FCA line, risk warning) is never model-generated: it is template text, never a
  slot. [check_repo.py checks it is present verbatim; the config contract keeps it out of slots]
- No client-specific values in `src/agent_pipeline/` or `config/` (the pipeline must generalise to
  unseen clients). `src/report_eval/` is exempt: eval/test tooling exists to encode known facts about
  specific hand-written clients, same category as `eval/expected/*.json` (D17). [check_repo.py]
- `formatting.py` unchanged [check_repo.py]; `data/` read-only except `data/synthetic/`
  [guard_protected.sh].
- CGT and fee figures are never produced by a model; they are adviser-review markers.
- Every figure in a report traces to a source value or a deterministic calculation over source values.
- Offline tests make no network calls; live calls sit behind `-m live`.
- A model never types a figure: writer output with a digit fails validation; figures enter only as
  ledger tokens. [write/tokens.py]
- Every extracted fact has a verified verbatim quote, and its amounts and dates are parsed from the
  quote by code. A label that decides an outcome has its own verified evidence quote, or code applies
  the conservative default. [extract/quotes.py]
- Every input given to the writer is digit-free. [write/plan.py]
- The investigation agent has read-only tools; its findings affect the ledger only through code
  verification and the rules. [investigate/accept.py]
- A run stops only where continuing is unsafe (DESIGN.md §8.4); every other input problem degrades to
  a marker, a review item or a conservative default, and the review sheet lists each one.
- `openai` is imported only in `agent_pipeline/llm.py`. [check_repo.py, to add]
- Every decision with a right answer (selection, reconciliation, arithmetic, inclusion where a
  `predicate` is set, which the shipped config does for every conditional section, markers) is in
  `reconcile/`, one function per rule, not in a prompt.
- Every gate has at least one mutation test. [tests/test_gate_mutations.py]
- Source-trust rules: SCOPING.md §3.1 (R1–R10) and §4 (P1–P12), implemented in `reconcile/`.

## Boundaries & contracts
- **Account data** (JSON, per holder): account existence, ownership, type, platform, status, dated
  values. Read with a tolerant pydantic schema: unknown fields ignored and logged, missing optional
  fields handled by the rules; only unreadable JSON or no holders stops the run (DESIGN.md §8.4).
- **Meeting record** (.docx prose): decisions, live-viewed values, money, open actions, excluded items.
  Model-extracted, quote-verified.
- **Report instruction** (.docx key/value table): scope, headline instruction, selling, risk profile,
  initial charge. Parsed in code; a model maps unknown labels and proposes the scope mapping, which
  code checks against type, named holders and platform.
- **Internal guidance** (.md): the whole document is read for client-specific handling, turned into a
  handling directive naming the person (checked against the people list); never reaches the writer as
  text.
- **Statement image**: vision read, low trust; confirms or raises discrepancies, never selects.
- **General documents**: classified, never extracted.
- **OpenAI API**: Responses API with structured outputs through `llm.LLMClient` only; model per stage
  from config.

## Cross-cutting concerns
- **LLM calls + caching:** `llm.LLMClient.structured(stage, prompt, inputs, schema)`. Cache key covers
  model, stage settings, prompt text, schema, inputs and images; the committed cache lives in
  `cache/llm/`; `--fresh` bypasses it.
- **Structured output validation:** pydantic schemas; one re-ask on a validation error, then the call
  fails. Whether a failed call stops the run depends on the stage: required stages stop, optional
  stages (image, guidance, investigation, scope proposal, no-predicate inclusion) degrade (DESIGN §8.4).
- **Errors/retries:** transient API errors retry with backoff (≤4); empty or refused output raises.
  A bounded loop that runs out never produces a guess: an unverified fact goes to the review sheet, an
  open question stays unresolved, and only a hard gate still failing makes a failed generation.
- **Logging/tracing:** one JSON line per model call in `runs/<run_id>/trace.jsonl`; run summary in
  `outputs/<client>.run.json`.
- **Cost accounting:** price table in `config/models.json`; cost per call from usage, reported per
  stage, per report and in every results file (no budget cap, D12); `--estimate` before live batches; a
  per-run ceiling only as a runaway-loop guard.
- **Config loading:** `config.py` resolves `extends` (sections merged by id, no section references),
  predicates (an unknown name fails at load) and prompt files; prompt version = content hash.

## Where new code goes / don't touch
- New source format → `agent_pipeline/sources/adapters/`; new source role → `agent_pipeline/extract/`
  plus a role in `sources/classify.py`.
- New trust rule or policy → one function in `agent_pipeline/reconcile/`, with its test.
- New gate → `agent_pipeline/gates/`, with a mutation test.
- New report type → a new config in `config/` that `extends` `base.json` (sections merged by id). A new
  kind of inclusion condition works from its plain-language `use_if` (model-decided from ledger facts,
  flagged for review) until a predicate is added in `reconcile/predicates.py`.
- New account type wording → `config/account_types.json`.
- New prompt → `config/prompts/<name>.md`.
- Expected facts → `eval/expected/`; synthetic and hand-written clients → `data/synthetic/`.
- Don't touch: `src/document_formatter/formatting.py`, `data/` (except `data/synthetic/`).
