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
- `agent_pipeline/extract/`: one extractor per role (meeting, instruction, guidance, image) and quote
  verification. Returns verified raw facts; never selects between sources.
- `agent_pipeline/ledger.py`: ledger models and value rendering. No I/O beyond (de)serialising.
- `agent_pipeline/reconcile/`: the trust rules and policies, one function per rule. Pure code, no model
  calls.
- `agent_pipeline/write/`: section plans (fact slices), the writer loop, token substitution, the table.
  The writer never sees a number.
- `agent_pipeline/gates/`: every gate, used by the pipeline (truth = ledger) and the eval (truth =
  expected facts); the release judge.
- `agent_pipeline/assemble.py`: outputs, review sheet, run summary; release state.
- `document_formatter/formatting.py`: final markdown assembly. Protected, unchanged.
- `report_eval/`: eval runner, expected-facts schema, extraction scoring, judge rubric, results files,
  mutations, synthetic client generator (`synth/`).

## Data flow
1. `generate.py` loads the report config and the client folder.
2. `sources` classifies each file into a role; unknown files are logged and excluded.
3. `extract` reads each role's sources into quote-anchored facts; code verifies quotes and parses
   amounts (≤3 correction rounds).
4. `reconcile` applies R1–R10 and P2–P12 and writes the ledger: accounts, selected and superseded
   values, money classes, actions, markers, review items, section decisions.
5. `write.plan` gives each included section only its own facts, markers and directives.
6. `write.writer` produces each generated slot with fact/marker tokens; section gates run; failures go
   back for repair (≤2 rounds).
7. Tokens are filled from the ledger; code builds the table and footnote; `formatting.py` assembles.
8. Report-level gates and the release judge run; one repair round if the judge flags a section.
9. `assemble` writes the draft or the failed-generation file, the review sheet, the ledger and the run
   summary (cache hits vs live calls, cost per stage).

## Invariants
<!-- The verifier checks diffs against these. Promote each to a check where you can. -->
- Static regulatory text (FCA line, risk warning) is never model-generated. [check_repo.py]
- No client-specific values in `src/` or `config/`. [check_repo.py]
- `formatting.py` unchanged; `data/` read-only except `data/synthetic/`. [check_repo.py, guard_protected.sh]
- CGT and fee figures are never produced by a model; they are adviser-review markers.
- Every figure in a report traces to a source value or a deterministic calculation over source values.
- Offline tests make no network calls; live calls sit behind `-m live`.
- A model never types a figure: writer output with a digit fails validation; figures enter only as
  ledger tokens. [write/tokens.py]
- Every extracted fact has a verified verbatim quote, and its amount is parsed from the quote by code.
  [extract/quotes.py]
- `openai` is imported only in `agent_pipeline/llm.py`. [check_repo.py, to add]
- Every decision with a right answer (selection, reconciliation, arithmetic, inclusion, markers) is in
  `reconcile/`, one function per rule, not in a prompt.
- Every gate has at least one mutation test. [tests/test_gate_mutations.py]
- Source-trust rules: SCOPING.md §3.1 (R1–R10) and §4 (P1–P12), implemented in `reconcile/`.

## Boundaries & contracts
- **Account data** (JSON, per holder): account existence, ownership, type, platform, status, dated
  values. Validated against a pydantic schema; a schema error fails the run.
- **Meeting record** (.docx prose): decisions, live-viewed values, money, open actions, excluded items.
  Model-extracted, quote-verified.
- **Report instruction** (.docx key/value table): scope, headline instruction, selling, risk profile,
  initial charge. Parsed in code; a model maps unknown labels and resolves scope phrases, checked in code.
- **Internal guidance** (.md): only the "This client" section, turned into a handling directive; never
  reaches the writer as text.
- **Statement image**: vision read, low trust; confirms or raises discrepancies, never selects.
- **General documents**: classified, never extracted.
- **OpenAI API**: Responses API with structured outputs through `llm.LLMClient` only; model per stage
  from config.

## Cross-cutting concerns
- **LLM calls + caching:** `llm.LLMClient.structured(stage, prompt, inputs, schema)`. Cache key covers
  model, stage settings, prompt text, schema, inputs and images; the committed cache lives in
  `cache/llm/`; `--fresh` bypasses it.
- **Structured output validation:** pydantic schemas; one re-ask on a validation error, then fail.
- **Errors/retries:** transient API errors retry with backoff (≤4); empty or refused output raises.
  A bounded loop that runs out is a failed generation, never a silent default.
- **Logging/tracing:** one JSON line per model call in `runs/<run_id>/trace.jsonl`; run summary in
  `outputs/<client>.run.json`.
- **Cost accounting:** price table in `config/models.json`; cost per call from usage; per-run ceiling;
  `--estimate` before live batches.
- **Config loading:** `config.py` resolves `extends`, section references and prompt files; prompt
  version = content hash.

## Where new code goes / don't touch
- New source format → `agent_pipeline/sources/adapters/`; new source role → `agent_pipeline/extract/`
  plus a role in `sources/classify.py`.
- New trust rule or policy → one function in `agent_pipeline/reconcile/`, with its test.
- New gate → `agent_pipeline/gates/`, with a mutation test.
- New report type → a new config in `config/` that `extends` `base.json` and reuses `config/sections/`.
- New prompt → `config/prompts/<name>.md`.
- Expected facts → `eval/expected/`; synthetic and hand-written clients → `data/synthetic/`.
- Don't touch: `src/document_formatter/formatting.py`, `data/` (except `data/synthetic/`).
