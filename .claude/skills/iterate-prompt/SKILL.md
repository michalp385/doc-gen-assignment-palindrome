---
name: iterate-prompt
description: Change a prompt, inclusion rule or section template in a disciplined, measurable way - one hypothesis per change, tested across all clients, committed with its evidence. Use this whenever editing anything in config/ or any prompt text in src/, whenever a report section is wrong, and whenever the user asks to tune, fix or improve a prompt.
---

# Iterate a prompt as code

Prompts are code here: structured, iterated, readable, with the commit history showing why each
changed. The pipeline serves clients it has never seen, so a prompt that fixes one client by
describing that client is a regression in disguise.

## Loop

1. **Name the failure** precisely: which check or which sentence is wrong, for which clients, and
   what the right output is according to the sources.
2. **Find the cause** before editing: missing information in the prompt's input, an ambiguous
   instruction, a rule that belongs in code rather than a prompt, or a wrong source-trust rule.
   Deterministic problems (dedupe, arithmetic, static text, table building) go in code.
3. **State one hypothesis** and make one change that tests it.
4. **Write the change generally**: describe the pattern ("a jointly held account appears under each
   holder; count it once"), never the instance. No client names, figures or account IDs, and no
   examples built from real client values. `scripts/check_repo.py` will fail on them.
5. **Keep prompts structured**: a role line, the inputs the prompt receives, rules as a short
   numbered list, the output format, and what to do when information is missing (flag it, never
   invent it).
6. **Measure** with the `run-eval` skill across all clients. Keep the change only if the target
   improves and nothing else regresses.
7. **Commit** the change alone: message = the failure, the hypothesis, and the result, quoting the
   eval results file. Revert if it didn't help, and say so in the commit history rather than
   hiding it.
