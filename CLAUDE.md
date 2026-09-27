# CLAUDE.md
<!-- Advisory. Anything that MUST hold is a hook (.claude/settings.json) or a check in
     scripts/check.sh / scripts/check_repo.py. If a rule here is broken twice, promote it. -->

## What this is
A production report-generation pipeline for a wealth-management firm. It turns a client's files
(account JSON, adviser meeting note, report request, other documents, statement images) into an
investment advice report that an adviser signs and sends to the client. These are regulated
documents: every fact must be right and traceable, and a wrong figure reaching a client is a
serious failure. Requirements: `PROJECT_GUIDANCE.md`.

What good looks like: correct facts, including which source wins when sources disagree; the right
sections in and out; clear, structured prompts; a pipeline that balances speed, cost and
effectiveness; a well-designed agent setup; and correct reports for clients the pipeline has never
seen, because new clients arrive all the time.

## Map — read before non-trivial work
- `PROJECT_GUIDANCE.md`: requirements. Source of truth for what must be delivered.
- `DESIGN.md` (once written): architecture and source-trust rules.
- `ARCHITECTURE.md`: code map + invariants.
- `DECISIONS.md`: the team's decision log (required). Add entries via `/decision`.
- `data/<client>/`: inputs. Never edit.

## Commands
- Generate: `uv run python -m agent_pipeline.generate --client <client>`
- Full gate: `bash scripts/check.sh` (format, lint, types, repo checks, offline tests). Same as CI.
- Offline tests: `uv run pytest -q`. Live API tests: `uv run pytest -m live` (costs money; ask first).
- Inspect a client's sources: `uv run python scripts/dump_client.py <client>`
- Eval: <add once built>

## Non-negotiables (mechanically checked where possible)
- Every figure in the report is a source value or a deterministic calculation over source values,
  done in code, not by the model. CGT, platform charges and adviser fees are never estimated:
  emit a visible adviser-review marker instead.
- The FCA authorisation line and the risk warning are static text: never model-generated or
  paraphrased.
- Internal guidance (e.g. FDE notes) shapes processing, but its text never appears in the report.
- General documents (market updates, platform packs) are never a source of client facts or figures.
- When sources conflict or information is missing, flag it for the adviser rather than guess, but
  only then: a report where everything is flagged is useless.
- No client-specific names, account IDs or figures in `src/` or `config/`: the pipeline must work
  for clients it has never seen. `scripts/check_repo.py` enforces this; allowlist only genuinely
  general values, with a reason.
- Do not modify `src/document_formatter/formatting.py`.
- Never commit `.env` or any key. Do commit final `outputs/`.
- Must run end to end from a clean checkout (`uv sync` + `.env`).
- Offline tests never call the API. Cache LLM calls. Print the cost estimate before any live batch
  run; ask first when the estimate exceeds $1 or it is a `--fresh` batch.
- Every metric quoted in docs is read from an eval output file, never typed by hand.

## How we work
1. **Plan first** for anything touching >1 module, a public interface, or an invariant: files,
   interfaces/types, invariants affected, test cases. Stop for approval of the plan. Once a plan
   is approved, execute its tasks without stopping for approval on each one; stop only if the
   plan turns out to be wrong or a decision it didn't anticipate comes up.
2. **Small diffs**, one concern each. No drive-by refactors.
3. **Tests are the spec for deterministic code** (source loading, deduplication, reconciliation,
   calculations, validation, static text): write the failing test first. **Model behaviour is
   measured by the eval**, not unit tests. Never weaken, skip or delete an assertion or eval check
   to get green; if one looks wrong, say why and let the user decide (hook-enforced for tests).
4. **Record decisions** between real alternatives with `/decision`, which appends a numbered entry
   (D1, D2, …) to `DECISIONS.md`. Update `ARCHITECTURE.md` when module responsibilities change.
5. **Verify at stage boundaries**: at a stage of the plan being complete, and before any change to
   prompts, source-trust rules or invariants is committed, stop and flag this to the user explicitly
   rather than invoking the `verifier` subagent on your own; they decide whether and when to run it.
6. **Commit per task**, message = what + why ("Make risk warning static: spec requires it verbatim").
   When a commit implements a recorded decision, cite it: "Prefer live meeting value over stale
   snapshot (D3)". Never rewrite, squash or re-date history.
7. **Handover** at the end of each task: what changed and why; 1–3 riskiest spots as file:line;
   assumptions you made that the user didn't state.

## Don't
- Edit `data/` (except `data/synthetic/`, which holds the hand-written and generated eval clients) or
  `formatting.py`. Add dependencies without listing them in the plan.
- Silence errors (broad `except`, `# type: ignore`, `noqa`) without a comment saying why.
- Put anything in committed files that isn't about this project.