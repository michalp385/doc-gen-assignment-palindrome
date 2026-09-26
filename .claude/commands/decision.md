---
description: Record a design decision made in this session in DECISIONS.md
argument-hint: <short decision title>
---
Record a decision for: $ARGUMENTS

`DECISIONS.md` is a required deliverable that engineers and stakeholders read, so write for them:
short, specific, first person, grounded in this repo's data. No generic filler.

1. Append a new numbered entry under "## Decisions" in `DECISIONS.md`, using this shape:
   ### N. <Decision, as an imperative: "Prefer the meeting's live value over a stale snapshot value">
   - **Context:** the facts that forced a choice (cite the data, e.g. which sources disagreed). 2–4 lines.
   - **Decision:** what we do, 1–3 lines.
   - **Alternatives:** only ones actually considered, each with why not. If none, write "None considered".
   - **Consequences / how it generalises:** what this commits us to, and what evidence would make us revisit it.
   - **Evidence:** eval result file(s) or commit(s) that show the effect, if any. Never type a metric by hand.
2. If it changes module responsibilities or an invariant, update `ARCHITECTURE.md` in the same change.
3. Show the entry and list anything you inferred rather than were told. The user edits the wording
   into their own voice before it is final.
