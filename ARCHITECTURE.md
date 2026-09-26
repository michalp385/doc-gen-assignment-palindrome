# Architecture
<!-- A map, not the territory. Readable in ~10 minutes. Fill in from DESIGN.md once the design is
     agreed; update when module boundaries, data flow or invariants change. -->

## Bird's-eye view
<One paragraph: client folder in → facts extracted and reconciled → sections generated → report out.>

## Code map
<One entry per module: what it owns, who calls it, what it must NOT do.>

## Data flow
<The life of one report through the modules, 5–10 steps.>

## Invariants
<!-- The verifier checks diffs against these. Promote each to a check where you can. -->
- Static regulatory text (FCA line, risk warning) is never model-generated. [check_repo.py]
- No client-specific values in `src/` or `config/`. [check_repo.py]
- `formatting.py` unchanged; `data/` read-only. [check_repo.py, guard_protected.sh]
- CGT and fee figures are never produced by a model; they are adviser-review markers.
- Every figure in a report traces to a source value or a deterministic calculation over source values.
- Offline tests make no network calls; live calls sit behind `-m live`.
- <Source-trust rules from DESIGN.md.>

## Boundaries & contracts
<Each input source, its shape, and what it is trusted for. The OpenAI API and how it is called.>

## Cross-cutting concerns
<The ONE way we do each: LLM calls + caching, structured output validation, errors/retries,
 logging/tracing, cost accounting, config loading.>

## Where new code goes / don't touch
- New source type → <adapter location>
- New report type → <config location>
- Don't touch: `src/document_formatter/formatting.py`, `data/`
