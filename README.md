# Advice report pipeline

Turns a client's files (account data, an adviser's meeting note, a report request, other
documents, a statement image) into an investment advice report that an adviser reviews, signs and
sends. These are regulated documents: every figure is a source value or a calculation done in
code, and a draft is either issued *for adviser review* with everything uncertain flagged, or
marked as a failed generation. The exercise is described in `PROJECT_GUIDANCE.md`.

## Setup

```bash
cp .env.example .env          # put your OpenAI key in .env (never commit it)
uv sync
```

## Run

```bash
uv run python -m agent_pipeline.generate --client client_01_clean
```

Options: `--data-dir`, `--config` (default `config/template_config.json`), `--output-dir`
(default `outputs/`), `--fresh`, `--estimate`.

**The committed cache.** Every model call is cached under `cache/llm/`, keyed on the model, stage
settings, prompt text, output schema and inputs, and the cache is committed. So a default run of a
client that already has cache entries is a **replay**: it makes no API call, costs nothing, and
reproduces the committed outputs exactly. Every run prints and records how many calls were cache
hits and how many were live, so a replay is never mistaken for a fresh generation.

**`--fresh`** bypasses the cache, calls the API and rewrites the cache entries. It costs money;
check the model prices in `config/models.json` first and ask before a batch. `--estimate` is
accepted but not implemented yet (it raises `NotImplementedError`); read the printed cost after a
run instead.

Client folders live under `data/`: `client_01_clean` to `client_04_stretch` (the four provided
clients), and `data/synthetic/handwritten/case_01` to `case_20` (hand-written cases, one rule
each). Committed outputs exist for `client_01_clean` and `client_02_medium`; the others have not
been generated yet.

## Checks and tests

```bash
bash scripts/check.sh          # format, lint, types, repo checks, offline tests (same as CI)
uv run pytest -q               # offline tests only: they never call the API
uv run pytest -m live          # live API tests: they cost money, run deliberately
```

`scripts/check_repo.py` (part of `check.sh`) enforces the repo-level rules: no client-specific
name, account ID, adviser, fund or figure in `src/agent_pipeline/` or `config/` (the pipeline must
work for clients it has never seen), no secrets, the FCA line and risk warning present verbatim as
static text, `formatting.py` unchanged, `openai` imported only in `llm.py`, and no run of six or
more words shared between a prompt and a source document.

## Evaluate

```bash
uv run python -m report_eval.run --clients client_01_clean client_02_medium
uv run python -m report_eval.run --clients all --judge
uv run python -m report_eval.run --clients all --outputs-dir outputs/baseline   # the starter pipeline's reports
```

The eval scores the reports already on disk against each client's hand-derived expected facts in
`eval/expected/<client>.json` (the deterministic gates G1-G16 and the quality criteria); it does
not run the pipeline. `--judge` adds a model judge (paid). `--stage-models stage=model,...`
overrides a stage's model for an experiment.

Each run writes `eval/results/<timestamp>_<commit>.json`, which records the commit, config and
prompt versions, models, per-client gate outcomes, judge scores, extraction scores, token usage,
cache hits, live calls, cost per client and the group summaries (issued rate, release-state match
rate, wrongly issued, cost per report). **Any number quoted in the docs is read from a results
file, never typed by hand**, so none is quoted here: run the eval, or read the latest file under
`eval/results/`. The cost of a single report is also `total_cost_usd` in its
`outputs/<client>.run.json`.

Ask before any live eval that could cost more than $1 or that uses `--fresh`.

## What each output file is

For a client `<client>`, `outputs/` holds:

| File | What it is |
|---|---|
| `<client>.md` | The **draft for adviser review**: the report itself, with every open point marked in the text as `[ADVISER TO CONFIRM #n: ...]`. Written only when every hard gate passed. |
| `<client>.failed.md` | A **failed generation**: the reason, the draft if there was one, and the failing gates with the offending text. Never issued. Written *instead of* the draft, and the other file is removed, so a stale draft is never mistaken for the current run. |
| `<client>.review.md` | What the adviser must **fill, check and clear**, section by section: the numbered markers and why each exists, conflicts and superseded values, blocking and informational open actions, and how the draft degraded where an input was missing or odd. Every marker in the report has a row here. |
| `<client>.ledger.json` | The **facts ledger**: every fact with its source, date and the rule that selected it, plus accounts, money items, actions, markers, review items and section decisions. The table, the figures and the markers in the report are all read from it. |
| `<client>.run.json` | The **run summary**: release state, every gate result, per-stage calls, cache hits vs live calls, and cost. |
| `outputs/baseline/` | The starter pipeline's reports, kept as the baseline the eval measures progress against. |

A per-call trace is written to `runs/<run_id>/trace.jsonl` (not committed). The design also calls
for a per-stage record folder next to the outputs; it is not written yet.

## How it fits together

A fixed code workflow with bounded model loops (`DECISIONS.md` D5), not an orchestrating agent:

1. **Classify** each file by what it is, not by its name; unknown roles are excluded and logged.
2. **Extract** quote-anchored facts from the meeting note, the request and images; code verifies
   every quote and parses every amount and date itself.
3. **Reconcile** in code, one function per trust rule (`SCOPING.md` sections 3.1 and 4): which
   source wins, which accounts are in scope, what is a marker and what is only a review note.
4. **Plan and write**: each section gets only its own facts, digit-free; the model writes prose
   with fact and marker tokens and never types a figure; code fills the tokens, builds the table
   and inserts every marker.
5. **Gate and judge**: deterministic gates and a release judge decide whether the result is a
   draft for adviser review or a failed generation.

`ARCHITECTURE.md` is the code map and the invariants; `DESIGN.md` the design; `SCOPING.md` the
requirements and expected facts for the four clients; `DECISIONS.md` the decision log.

## Repo map

| Path | Holds |
|---|---|
| `src/agent_pipeline/` | the pipeline (`generate.py` is the CLI, `pipeline.py` the stage graph) |
| `src/report_eval/` | the eval runner, expected-facts schema, scoring, and the synthetic client generator (`synth/`) |
| `src/document_formatter/` | the final markdown assembly (`formatting.py` is protected, do not edit) |
| `config/` | the report definition, prompts (`config/prompts/`), account-type wording, tax rule figures, model prices |
| `data/` | the client inputs (read-only; `data/synthetic/` holds hand-written and generated cases) |
| `eval/expected/` | the hand-derived expected facts everything is scored against |
| `cache/llm/` | the committed LLM response cache |
| `scripts/` | `check.sh`, `check_repo.py`, `dump_client.py` (print a client's sources), `build_handwritten.py` |
