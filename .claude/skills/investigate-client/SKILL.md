---
name: investigate-client
description: Systematically read every source for one client folder under data/ and produce a findings note - facts, conflicts between sources, duplicates, stale or missing values, distractors, and figures a person must supply. Use this whenever starting work on a client, when a report for a client looks wrong, when a new or synthetic client is added, or before changing a prompt or source-trust rule, even if the user only says "look at client X" or "why is this report wrong".
---

# Investigate a client's data

The reports go wrong because of the data, not the prose. Most errors come from a small set of
patterns, and the fastest way to find them is to read every source yourself before trusting
the pipeline's output. Do this before touching prompts.

## Steps

1. **Dump the text sources**: `uv run python scripts/dump_client.py <client>`.
2. **Read every image** in the folder with the Read tool. Images are not read by the pipeline's
   loader, so anything only in an image is invisible to it.
3. **Build a fact table**: for each account, one row per source that mentions it, with the value,
   the date of that value, and the source. Include accounts mentioned only in prose.
4. **Check each pattern** below and write down every instance you find.
5. **Write the findings** to `notes/<client>.md` (create `notes/` if needed) using the template
   at the end. Keep it factual; decisions go in DECISIONS.md via `/decision`.

## Patterns to check

- **Duplicates**: the same account listed under more than one holder (joint accounts). Count once.
- **Conflicting values**: the same account with different values in different sources. Record
  both, with dates. Which one wins is a source-trust rule in DESIGN.md, not a guess.
- **Stale values**: a valuation date well before the meeting date.
- **Approximate values**: prose like "a little over" or "around". Never promote them to exact figures.
- **Missing or null values**, and accounts with a non-open status.
- **Accounts outside scope**: in the data but not in the report request's accounts covered.
- **Accounts not yet in the data**: new accounts the meeting or request creates.
- **Money that isn't available**: contingent, committed elsewhere, not yet received.
- **Distractors**: platform-wide or illustrative figures in general documents.
- **Aspirations and tangents**: things discussed but explicitly not to be actioned.
- **Figures a person must supply**: CGT, fees, amounts the sources leave unspecified.
- **Per-client instructions** in `fde_notes.md` (tone, sensitivity) that the report must respect
  without quoting.

## Findings template

```
# <client>: findings
## Accounts (deduplicated)
| Account | Owner | Type | Value | Value date | Source | In scope? | Notes |
## Conflicts
## Money available vs not available
## Distractors to ignore
## Must not be actioned
## Gaps a person must fill
## Per-client instructions
## Pipeline risks (what the current pipeline is likely to get wrong here)
```

Every finding should name the source it came from. If a pattern here doesn't fit what you see,
say so in the findings rather than forcing it: new clients may bring new patterns.
