# Implementation plan: advice report pipeline

Implements `DESIGN.md` (commit `2ba55ee`) against `SCOPING.md` (`0e4468c`). Order follows DESIGN §17
and D15: truth first (M0a), then only the deterministic core client 01 needs (M0b), a thin client 01
slice (M1), then widening rule by rule as clients 02–04 and the hand-written cases need it (M2–M5).

**Conventions for every task**
- One task = one or more small commits, one concern each, message = what + why, citing decisions.
- Deterministic code: the test is written and run first, and seen failing, then committed together
  with the code that makes it pass (CLAUDE.md "tests are the spec"; a red test is never committed
  alone, because every commit keeps check.sh green), in M2 as much as in M0b. Model behaviour is measured by the eval, not unit tests.
- `bash scripts/check.sh` green before every commit.
- **Prompt or stage-config changes carry their evidence:** a commit that changes a prompt file or a
  stage's config (model, reasoning effort, schema, prompt reference) also includes the refreshed
  `cache/llm/` entries and `outputs/` files for every client whose calls it affects, so the offline
  replay test (T16) stays green and the committed outputs always match the committed code. Superseded
  cache entries are removed in the same commit.
- "Gates moved": the SCOPING gates, rules or policies the task makes checkable or makes pass.
- **Live runs:** every live batch prints its cost estimate first (`--estimate`). I ask before running
  only when the estimate exceeds $1 or it is a `--fresh` batch; otherwise I run it and report the
  measured cost.
- ⛳ **Verifier checkpoint**: run the `verifier` subagent on the stage's diff; fix findings before moving
  on. CLAUDE.md also requires a verifier pass before any prompt, trust-rule or invariant change is
  committed; those tasks are marked ⛳ too.

**Dependencies added** (listed here as CLAUDE.md requires): `pydantic` (T1, runtime; already present
transitively), `Pillow` (T3, `dev` extra, for rendering statement images).

---

## M0a. Truth first

### T1. Expected-facts schema
- **Files:** `src/report_eval/__init__.py`, `src/report_eval/expected.py`; `pyproject.toml` (declare
  `pydantic`; add `src/report_eval` to hatch `packages`).
- **Interfaces:** `ExpectedFacts` (pydantic, `extra="forbid"`): `client`, `meeting_date`,
  `expected_release_state` (+ `reason`), `table_rows[]` (account_id or `new:<slug>`, owners, type,
  value_render, footnote), `not_in_table[]` (account, reason), `reportable_figures[]` (value, placement,
  optional, section_hint), `markers[]` (key, required, `alternatives[]`), `review_items[]` (kind, blocking,
  must_mention), `sections{id: included}`, `actions[]` (incl. agreed non-actions), `excluded_items[]`
  (class, subject), `must_not_appear[]`, `material_claims[]`, `extraction{value_observations,
  money_items, disposals, open_actions, labels}`, `investigation[]` (question, expected answer or
  `stays_unresolved`). `load_expected(client) -> ExpectedFacts`.
- **Tests (first):** `tests/test_expected_schema.py`: round-trip; unknown key rejected; alternatives
  shape; release state enum.
- **Gates moved:** none directly; defines truth for every eval-mode gate (SCOPING §2 "two layers").
- **Done:** schema importable; check.sh green.

### T2. Expected facts for the four clients
- **Files:** `eval/expected/client_01_clean.json` … `client_04_stretch.json`.
- **Content:** transcribed from SCOPING §7 and `notes/`, including extraction labels (e.g. client 02's
  GIA observation `viewed_in_meeting` with evidence "I pulled the account up live"), material claims,
  agreed non-actions (client 04's offshore bond).
- **Tests:** `tests/test_expected_fixtures.py`: every fixture loads; every table `account_id` exists in
  that client's account data or is `new:`; every reportable figure is a source value or listed as a
  derived calculation with its inputs; every `must_not_appear` figure really occurs in a general
  document (so the check is live); every quoted evidence string occurs in its source.
- **Gates moved:** G1, G2, G5–G9, G13–G15 have truth for the real clients.
- **Done:** four fixtures pass the tests. **Human review:** you read the four files before T3 (they are
  the truth everything is scored against).

### T3. Hand-written cases
- **Files:** `eval/handwritten_src/case_NN.md` (hand-written source text and structured inputs per case,
  one file each); `scripts/build_handwritten.py` (renders each case to
  `data/synthetic/handwritten/case_NN/` as account JSON, meeting and instruction .docx, fde .md, and a
  statement .png where the case needs one); `eval/expected/case_NN.json`; `pyproject.toml` (`Pillow` in
  the `dev` extra).
- **Content:** the 20 cases in DESIGN §10.6, each small and aimed at one rule; cases 19–20 expect a
  failed generation.
- **Tests:** `tests/test_handwritten_build.py`: rebuilding from source reproduces the committed folders
  byte-for-byte (docx/png written deterministically); fixtures pass T2's consistency tests.
- **Gates moved:** truth for R3–R10, P5, P7, P10–P12, §5.2 and §8.4 on unseen shapes.
- **Done:** 20 cases built and committed with expected facts. **Human review** of the case list and
  expected states.

⛳ **Verifier checkpoint (end of M0a):** fixtures against SCOPING §7 and the sources; the hand-written
cases against DESIGN §10.6.

---

## M0b. Deterministic core for client 01 only, tests first

Only what client 01 exercises. Every other rule and gate is built in M2, tests-first, when a client or
case first needs it.

### T4. Amount and date parsing
- **Files:** `src/agent_pipeline/extract/parsing.py`.
- **Interfaces:** `parse_amount(quote: str) -> ParsedAmount | None` (`amount: Decimal`, `currency`,
  `qualifier: exact|around|a_little_over|a_little_under|up_to|circa`, `precision`);
  `parse_date(quote: str) -> date | None`.
- **Tests (first):** `tests/test_parsing.py`: `£45,000`, `GBP 120,000`, `£1.2m`, `£45k`, `up to
  £400,000`, `a little over £45,000`, `around £38,000`, `c. £45,000`, `€61,000` (currency kept), no
  amount; dates `12 May 2026`, `15 Mar 2026`, `2026-04-30`, `held 14 May 2026`, ambiguous → None.
  (Parsing is cheap to make general now; the formats are the ones all four clients use.)
- **Gates moved:** G2, G6 (every figure parsed by code, D9).
- **Done:** tests green.

### T5. Quote and label verification
- **Files:** `src/agent_pipeline/extract/quotes.py`.
- **Interfaces:** `verify_quote(doc: SourceDoc, paragraph_id: str, quote: str) -> Verified | Rejected`;
  `verify_label(fact, evidence) -> Accepted | Defaulted(reason)` (same-paragraph rule, DESIGN §4.2);
  `CONSERVATIVE_DEFAULTS` for the labels client 01 uses (`basis`, `excluded class`); the rest in M2.
- **Tests (first):** `tests/test_quotes.py`: whitespace normalisation; quote in another paragraph
  rejected; label evidence in another paragraph → default.
- **Gates moved:** G6, P6 (labels can't silently decide outcomes).
- **Done:** tests green.

### T6. Ledger models and rendering
- **Files:** `src/agent_pipeline/ledger.py`.
- **Interfaces:** `Value`, `Fact` (with `transaction`, `role`, `placement`), `Account`, `MoneyItem`,
  `Action`, `ExcludedItem`, `Marker`, `ReviewItem`, `Question`, `Ledger`; `render_prose(Value)`,
  `render_table(Value)`; `number_markers(ledger, report_order)`.
- **Tests (first):** `tests/test_ledger.py`: exact renders exact; approximate renders "c." in the table
  and the source wording in prose; marker IDs by order of first appearance; JSON round trip.
- **Gates moved:** G6, P1, P9, S5.
- **Done:** tests green.

### T7. Source adapters (account data, docx, markdown)
- **Files:** `src/agent_pipeline/sources/adapters/{json_accounts,docx,markdown}.py`.
- **Interfaces:** `read_accounts(path) -> AccountData` (tolerant: unknown fields logged, optional fields
  may be missing); `read_docx(path) -> SourceDoc` (paragraph IDs, tables, core-properties date);
  `read_markdown(path) -> SourceDoc`.
- **Tests (first):** `tests/test_adapters.py`: client 01's sources read without loss (paragraph count,
  the instruction table); unreadable JSON raises the input-stop error.
- **Gates moved:** §8.4 failure policy (input stops), G1 (accounts as recorded).
- **Done:** tests green.

### T8. Reconcile for client 01: R1–R3, scope, amounts, P2–P6 basics ⛳
- **Files:** `src/agent_pipeline/reconcile/{ownership,wrappers,scope,values,amounts,money,limits,
  sections,predicates,markers,review}.py` (each holding only client 01's rules for now);
  `config/account_types.json` (ISA, cash, GIA entries); `config/tax_rules.json` (ISA allowance for the
  meeting's tax year); `scripts/check_repo.py` + `scripts/overfit_allowlist.txt` (file-scoped allowlist:
  `config/tax_rules.json: 20000  # ISA allowance, a general rule`).
- **Interfaces:** `resolve_ownership` (R1), `classify_wrapper`, `resolve_scope` (R2, R8 checks: type,
  holder, platform; a failed phrase → marker row), `select_values` (R3: account data vs viewed meeting
  values), `reconcile_amounts` (R5 same-amount case), `classify_money` (P5: an agreed transfer between
  the client's own accounts), `check_limits` (P4: full-allowance subscription, prior use unknown →
  review note), `decide_sections` + predicate registry (no disposal → no Tax section),
  `required_markers` (P2/P3: platform charge, ongoing advice charge), `build_review_items`, P6
  (aspiration kept for Background only).
- **Tests (first):** `tests/test_reconcile_client01.py`, named by rule:
  `test_r1_single_owner`, `test_r2_out_of_scope_account_not_in_table`, `test_r3_snapshot_value_when_no_later_figure`,
  `test_r8_phrase_resolves_by_type_and_platform`, `test_r5_same_amount_uses_exact`,
  `test_p4_full_allowance_unknown_prior_use_note`, `test_p2_charge_markers`, `test_g5_no_disposal_no_section`,
  `test_p6_aspiration_background_only`; `tests/test_check_repo.py` (file-scoped allowlist).
- **Gates moved:** G1, G5, G6, G13, G14, G15 (pipeline mode) for client 01; R1–R3, R5, R8, P2–P6 basics.
- **Done:** tests green; check_repo still flags 20000 outside `config/tax_rules.json`; ⛳ verifier
  (trust rules).

### T9. Deterministic gates for client 01, with mutation tests
- **Files:** `src/agent_pipeline/gates/deterministic.py`, `src/agent_pipeline/gates/truth.py`
  (`Truth` protocol; `ExpectedTruth`, `LedgerTruth`), `src/report_eval/reference.py` (stub writer:
  reference bundle from expected facts), `tests/test_gate_mutations.py`.
- **Interfaces:** `run_gates(bundle, truth) -> list[GateResult]` for the gates client 01 exercises:
  G1, G2 (list), G3, G4 (exact and once; the paraphrase screen with a provisional threshold, calibrated
  in T25), G5, G6, G9, G10 (6-gram screen with exclusions), G11, G12 (deterministic), G13, G14, G15, P6
  at-most-once.
- **Tests (first):** client 01's reference bundle passes every gate; each mutation in DESIGN §10.5 for
  these gates makes at least its intended gate fail on client 01's bundle.
- **Gates moved:** those listed, checkable in eval and pipeline mode.
- **Done:** mutation tests green offline.

⛳ **Verifier checkpoint (end of M0b):** the client 01 core against SCOPING §3–§4 and DESIGN §4–§6, §8.1.

---

## M1. Thin vertical slice: client 01 correct end to end

### T10. Config loading and prompts-as-code
- **Files:** `src/agent_pipeline/config.py`; `config/base.json` (global instructions, marker format,
  static texts, stage models, shared sections); `config/template_config.json` (`extends`, sections
  inline, slot kinds, `use_if` + `predicate`); `config/models.json` (prices, source URL, date).
- **Interfaces:** `load_report_config(path) -> ReportConfig` (extends merge by id, predicate names
  validated, prompts loaded with content-hash versions).
- **Tests (first):** `tests/test_config.py`: merge by id; unknown predicate fails at load; static texts
  are template text, never slots; prompt version changes with text. The committed `tests/test_smoke.py`
  passes unchanged.
- **Gates moved:** G4 (static text), G5 (predicates), S6.
- **Done:** tests green; check_repo static-text check passes on the new config.

### T11. LLM client, cache, trace, cost
- **Files:** `src/agent_pipeline/{llm,cache}.py`; `.gitignore` (`runs/`).
- **Interfaces:** `LLMClient.structured(stage, prompt, inputs, schema, images=(), tools=()) ->
  LLMResult[T]`; cache under `cache/llm/`; `--fresh`; `--estimate`; trace JSONL; per-call cost;
  runaway guard.
- **Tests (first):** `tests/test_llm_client.py` with a fake transport: key stable across checkouts (no
  absolute paths, run IDs or timestamps); any change to model, prompt, schema, stage settings or inputs
  misses; 429 and 5xx retried with backoff; one schema re-ask then failure; empty output raises; cost
  from usage incl. cached and reasoning tokens; hit/live counts.
- **Live (est. ≈$0.001):** one `-m live` call per default model to confirm structured outputs, image
  input and whether `temperature` is accepted (DESIGN §16.3); recorded in `config/models.json`.
- **Gates moved:** S3, S4, S5.
- **Done:** tests green; live check recorded.

### T12. Classification ⛳ (prompt)
- **Files:** `src/agent_pipeline/sources/classify.py`; `config/prompts/classify.md`.
- **Interfaces:** `classify(folder) -> list[ClassifiedSource]`; the §3.2 consistency rules and input stops.
- **Tests (first):** structural rules; consistency and stop rules with a stubbed classifier.
- **Live (est. ≈$0.001):** client 01.
- **Gates moved:** R7 (general documents never extracted), §8.4 input stops.
- **Done:** client 01 classified correctly; ⛳ verifier before the prompt is committed.

### T13. Extraction: meeting and instruction, with verification loop ⛳ (prompts)
- **Files:** `src/agent_pipeline/extract/{schemas,meeting,instruction}.py`;
  `config/prompts/{extract_meeting,extract_instruction,scope_mapping}.md`.
- **Interfaces:** `extract_meeting(doc) -> MeetingExtraction` and `extract_instruction(doc, accounts) ->
  InstructionExtraction`, each running the ≤3-round verification loop with `find_in_source`.
- **Tests (first):** loop behaviour with a scripted fake model: bad quote → re-ask → fixed; still bad →
  dropped to review; label evidence elsewhere → default; the instruction table parsed in code.
- **Live (est. ≈$0.005):** client 01; extraction scored against its fixture.
- **Gates moved:** P11 (risk profile verbatim); extraction score (§10.7) for client 01.
- **Done:** client 01 extraction matches its fixture; ⛳ verifier before prompts are committed.

### T14. Plan, writer, tokens, table ⛳ (prompts)
- **Files:** `src/agent_pipeline/write/{plan,writer,tokens,table}.py`;
  `config/prompts/write_<slot>.md` for each generated slot.
- **Interfaces:** `plan_sections(ledger, config) -> list[SectionPlan]` (fact slices with roles,
  digit-free inputs, withheld texts as review items); `write_slot(plan) -> SlotDraft` (≤2 repair rounds
  against the section gates); `fill_tokens(draft, ledger) -> str`; `build_table(ledger) -> str`.
- **Tests (first):** digit in writer output rejected; unknown token rejected; required marker missing
  rejected; plan inputs contain no digits; table for client 01's fixture; G12 after substitution.
- **Live (est. ≈$0.004):** client 01's slots.
- **Gates moved:** G2, G3, G9, G11, G12, P9, D1.
- **Done:** client 01 sections pass the section gates; ⛳ verifier before prompts are committed.

### T15. Release judge, assembly, review sheet, failure policy ⛳ (prompt)
- **Files:** `src/agent_pipeline/gates/{judge,release}.py`, `src/agent_pipeline/assemble.py`;
  `config/prompts/release_judge.md`.
- **Interfaces:** `release_judge(bundle, ledger) -> JudgeVerdict` (G7/G8/G12/G16 parts, G2 role, G4 and
  G10 paraphrase, P6; source quotes verified; G16 coverage enforced with one re-ask);
  `decide_release(results) -> ReleaseState`; `write_outputs(...)` (draft or failure file, removing the
  other; review sheet §8.5; ledger; run summary; per-stage record).
- **Tests (first):** G16 coverage: an uncovered sentence fails after the re-ask; unverified source quote
  = unsupported; release-state files written and the stale counterpart removed; an input stop writes
  the reason and classification only.
- **Live (est. ≈$0.003):** client 01.
- **Gates moved:** G7, G8, G12, G16 (judge parts), release states, §8 explainability.
- **Done:** client 01 issued as a draft with a complete review sheet; ⛳ verifier before the prompt is
  committed.

### T16. Pipeline wiring and CLI
- **Files:** `src/agent_pipeline/pipeline.py`; `src/agent_pipeline/generate.py` (same command, new
  pipeline); `scripts/check_repo.py` (rule: `openai` imported only in `llm.py`).
- **Interfaces:** `run(client_dir, config, *, fresh=False, estimate=False) -> RunResult`; console line
  with calls, cache hits vs live, cost.
- **Tests:** `tests/test_pipeline_replay.py`: client 01 end to end offline from the committed cache,
  reproducing the committed outputs exactly; `tests/test_check_repo.py` for the import rule.
- **Gates moved:** S2, S4.
- **Done:** `uv run python -m agent_pipeline.generate --client client_01_clean` replays at $0.

### T17. Eval runner and results files ⛳ (eval judge prompt)
- **Files:** `src/report_eval/{run,results,judge_rubric,extraction_score}.py`;
  `config/prompts/eval_judge_*.md`; `eval/results/`.
- **Interfaces:** `python -m report_eval.run --clients <list|all> [--judge] [--fresh]
  [--stage-models stage=model,…] [--outputs-dir <dir>]`; results file per DESIGN §10.4 (incl. issued
  rate, release-state match, wrongly issued, accepted-and-wrong, cost per report).
- **Baseline first:** the first results file scores `outputs/baseline/` from the saved files
  (`--outputs-dir outputs/baseline`): every deterministic gate in eval mode against the four fixtures,
  plus the Sol eval judge. The baseline has no review sheet or ledger, so G15 and the ledger-based
  checks fail by construction, and the results file says so rather than skipping them. This is the
  starting row of the progression table.
- **Tests:** results-file schema; offline deterministic scoring of saved files (baseline and client 01)
  reproduces the committed results.
- **Live (est. ≈$0.28 baseline judge + ≈$0.08 client 01):** printed, then run.
- **Gates moved:** every gate in eval mode for client 01; Q1–Q6; the baseline measured.
- **Done (M1):** baseline results file committed first; client 01 passes every hard gate against its
  expected facts; its results file committed; run summary shows cost and cache use; replay reproduces it
  at $0. CLAUDE.md's `Eval:` command line filled in (your file: I'll propose the line).

⛳ **Verifier checkpoint (end of M1):** the slice end to end against SCOPING §2, and a clean-checkout
run (S2).

---

## M2. Widen: images, clients 02–04, investigation, then the hand-written cases

Images come first because clients 02–04 all have a statement image; the investigation agent comes
before the hand-written cases because cases 2, 16 and 17 need it. Each task adds the rules and gates a
client or case group needs, **failing test first**, then runs the eval across everything built so far
(a change for one client must not regress another).

### T18. Statement images ⛳ (prompt)
- **Files:** `src/agent_pipeline/sources/adapters/image.py`, `extract/image.py`,
  `config/prompts/extract_image.md`; P10 in `reconcile/values.py`.
- **Tests (first):** image observations never select; currency mismatch always a review item, labelled
  a possible read error when the account data says GBP; unreadable image degrades.
- **Live (est. ≈$0.01).**
- **Done:** the image reads for clients 02–04 match their account data (scored against the fixtures'
  extraction expectations), so T19–T21 run with images from the start; case 1 is covered in T23.

### T19. Client 02: joint accounts, live values, disposals, limits ⛳
- **Rules and gates, tests first:** R9 (dedupe by `account_id`, copies agreeing), R3 with a later viewed
  value and superseded footnote, the `disposal extent` label and its default, G5 with a taxable disposal
  and CGT marker (P7), P4 prior-use trigger and the limit marker restricting the writer's facts (DESIGN
  §6 roles), P5 proceeds counted only with amount and destination, G7 deterministic part, the tangent
  class (P6: never in any plan).
- **Prompts:** disposal and money-item extraction, the Tax Implications slot (`iterate-prompt`).
- **Live (est. ≈$0.02 per pass):** client 02, plus clients 01 for regression.
- **Done:** client 02 passes every hard gate; client 01 still does.

### T20. Client 03: new accounts, nulls, exact vs approximate, guidance ⛳
- **Rules and gates, tests first:** new accounts "To be opened" with Type wording (P9) and their charges
  marker; R6 out-of-scope null → review only; R5 same stated amount → exact; blocking open actions (P2);
  derived approximate totals; guidance directives (D8, P8) with the person resolved against the people
  list, and G10 against real notes.
- **Files:** `extract/guidance.py`, `config/prompts/extract_guidance.md`.
- **Live (est. ≈$0.03 per pass).**
- **Done:** client 03 passes every hard gate; clients 01–02 still do.

### T21. Client 04: several platforms, closed accounts, money classes, bond ⛳
- **Rules and gates, tests first:** R6 closed out of scope ignored; P5 received/committed/external with
  the available calculation and the excluded earnout; per-platform charge markers; pension contributions
  always markers (P4); agreed non-actions (G8); bond present with no action; `money class` label
  defaults; derived "available" fact role.
- **Live (est. ≈$0.04 per pass).**
- **Done:** client 04 passes every hard gate; clients 01–03 still do.

### T22. Conflict investigation agent ⛳ (prompt, invariant)
- **Files:** `src/agent_pipeline/investigate/{agent,tools,accept}.py`,
  `src/agent_pipeline/reconcile/questions.py`, `config/prompts/investigate.md`; `pipeline.py` (stage 3a,
  one re-run).
- **Tests (first):** tools are read-only; acceptance: same-paragraph label evidence, exactly one account
  candidate, R8 multi-match stays flagged; "changed by investigation" review entries show default, new
  value and quote; ordering and ≤5 × ≤6 limits; a model failure leaves defaults and never fails the run.
- **Live (est. ≈$0.02):** cases 2, 16, 17 and client 03.
- **Done:** cases 16 and 17 behave as expected; accepted-and-wrong = 0.

### T23. Hand-written cases: remaining rules and failure policy ⛳
- **Rules and gates, tests first, driven by the cases:** R3 image later than account data (1) and
  recalled figures (2); R9 disagreeing copies and same-date disagreement (3, 4); R6 closed and null in
  scope (5, 6); R4 decision mismatch → G5 case b (7); R5 any difference → conflict (8); P5 commitment
  without amount (9); G5/P7 wrapper switch and bond encashment, the `unknown` wrapper class (10); R8
  unresolved phrase marker row and blocking item (11); P12 non-GBP (12); P11 "TBC" (13); R10 several
  meeting records (14); classification of renamed and unknown files (15); undated meeting and missing
  optional fields (18); input stops for disagreeing instructions and "TBC" scope (19, 20); the §8.4
  optional-stage degradations.
- **Live (est. ≈$0.20 per pass over 20 cases).**
- **Done:** every case reaches its expected release state and, if issued, passes every hard gate;
  wrongly issued = 0.

### T24. Full gate coverage: remaining mutations and judge mutations
- **Files:** `tests/test_gate_mutations.py` (every gate and mutation in DESIGN §10.5, across all four
  reference bundles; judge mutations recorded once live, then replayed from the cache).
- **Live (est. ≈$0.05):** ≈12 judge mutations.
- **Done:** every gate has at least one passing mutation test.

### T25. Calibration and the M2 results file
- **Content:** G4 paraphrase threshold calibrated (DESIGN §8.1) and recorded with its results file; G16
  judge calibrated against the hand-written material claims (§10.7).
- **Live (est. ≈$1.70 for the Sol eval judge over 24 clients):** above $1, so I ask first.
- **Done (M2):** all four clients and every expected-draft case pass every hard gate; cases 19–20 fail
  as expected; wrongly issued = 0; accepted-and-wrong = 0; results file committed.

⛳ **Verifier checkpoint (end of M2).**

---

## M3. Model selection by measurement

### T26. Luna vs Sol experiment
- **Method:** DESIGN §10.7 for extraction, release judge and investigation; `--stage-models` overrides.
- **Live (est. ≈$4.60):** above $1, so I ask first.
- **Done:** a `/decision` entry per stage citing both results files and each option's cost per report;
  `config/base.json` stage models updated only where Sol measurably wins. ⛳ verifier if any stage
  model changes.

---

## M4. Synthetic clients

### T27. Generator
- **Files:** `src/report_eval/synth/{scenario,writers,prose,phrases}.py`; phrase bank; D4 checks.
- **Tests (first):** scenario → expected facts deterministic for a seed; required-phrase and
  unplanned-figure checks reject bad prose; phrase bank has no 6-gram overlap with `data/` documents.
- **Live (est. ≈$0.20, one-off):** ≈20 clients generated and frozen under `data/synthetic/generated/`.
- **Done:** 20 clients committed with expected facts.

### T28. Synthetic run and metrics
- **Live (est. ≈$0.25):** pipeline over the 20 synthetic clients; deterministic eval gates.
- **Gates moved:** S1 (generalisation); issued rate, release-state match and wrongly issued on the
  synthetic group.
- **Done:** results file committed; any failure investigated against its sources before M5 (per
  `run-eval`).

---

## M5. Hardening and submission

### T29. `check_repo.py` extensions
- **Files:** `scripts/check_repo.py`, `tests/test_check_repo.py`.
- **Content:** synthetic names and IDs denied in `config/` and `src/agent_pipeline/` (not `synth/`);
  adviser names and general-document fund names; 6-gram overlap between prompts and `data/` documents.
- **Done:** tests green; check.sh green on the full repo.

### T30. README and docs
- **Files:** `README.md`, `ARCHITECTURE.md` (code map status → built), `.claude/skills/run-eval/SKILL.md`
  (drop "$10 budget", apply the $1 / `--fresh` ask rule, per D12).
- **README content:** how to run and evaluate; the committed cache and `--fresh`; cost per report read
  from the latest results file; and **a section explaining each output file**: `outputs/<client>.md`
  (the draft for adviser review), `.failed.md` (a failed generation: reason, draft, failing gates),
  `.review.md` (what the adviser must fill, check and clear, section by section), `.ledger.json` (every
  fact with its source, date and selecting rule), `.run.json` (stages, cache hits vs live calls, cost,
  gate results, release state), `outputs/<client>.run/` (per-stage inputs and outputs), and
  `eval/results/*.json` (what each results file records).
- **Done:** a clean-checkout run following the README works.

### T31. Final fresh run
- **Live (est. ≈$2.15):** a `--fresh` batch, so I ask first. `--fresh` over all clients and cases; eval
  with the Sol judge.
- **Files:** `outputs/` (reports, review sheets, ledgers, run summaries, `outputs/<client>.run/`),
  `cache/llm/`, `eval/results/`, the progression table generated by `scripts/progression.py` (baseline
  row first).
- **Done:** committed outputs and cache match the final code; replay reproduces them at $0.

### T32. DECISIONS.md: summary and your voice pass
- **Content:** I draft the Summary, "What I would do with more time" and "How I worked" sections, with
  every figure quoted from a results file. Then **your voice pass**: you edit every decision entry into
  your own wording (the `/decision` convention); I don't change the substance, and I check afterwards
  that no figure was typed by hand and every cited results file exists.
- **Done:** you sign off DECISIONS.md.

⛳ **Verifier checkpoint (end of M5):** the whole repo against SCOPING and CLAUDE.md before submission.

---

## Estimated live spend (pre-build; measured spend replaces it)

T11 ≈$0.001 · T12–T15 ≈$0.015 · T17 ≈$0.36 · T18 ≈$0.01 · T19–T21 ≈$0.10 per pass · T22 ≈$0.02 ·
T23 ≈$0.20 per pass · T24 ≈$0.05 · T25 ≈$1.70 (ask) · T26 ≈$4.60 (ask) · T27 ≈$0.20 · T28 ≈$0.25 ·
T31 ≈$2.15 (`--fresh`, ask), plus prompt-iteration passes (DESIGN §10.9).
