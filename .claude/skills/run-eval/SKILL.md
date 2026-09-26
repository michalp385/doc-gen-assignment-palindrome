---
name: run-eval
description: Run the report evaluation and record the results so every metric is traceable to an output file. Use this whenever you need to know whether reports are correct, before and after any prompt, config or pipeline change, before committing a change that affects report content, and whenever a number is about to be quoted in DECISIONS.md, a commit message or the README.
---

# Run and record the eval

Two rules make the eval trustworthy: numbers are produced by the eval and read from its output,
never typed by hand; and live runs cost real money from a $10 budget.

## Before running

1. Find the eval entrypoint in CLAUDE.md's Commands. If it doesn't exist yet, stop and say so;
   don't improvise one.
2. **Prefer offline**: deterministic checks on existing reports and cached model responses cost
   nothing. Run those first.
3. **For a live run**, estimate the cost first: number of clients x model calls per report x rough
   tokens per call, priced for the models configured. State the estimate and ask before running
   anything over a few cents, or any run across all clients.

## Running

- Run across **all** clients the eval knows about, including synthetic ones, not only the client
  you were fixing. A fix that helps one client and breaks another is a regression.
- Let the eval write its results file. It should record: git commit, timestamp, config/prompt
  version, models used, per-client and per-check results, token usage and cost.

## After running

1. Compare against the previous results file: list checks that newly pass, newly fail, and
   anything that changed on clients you didn't touch.
2. Report numbers by quoting the results file path alongside them.
3. If a check fails, read the report and the sources before changing anything: the check may be
   wrong, or the data may hold a pattern the design doesn't cover yet.
4. Never edit a check to make a result pass. If a check is wrong, say why and let the user decide.
