"""Importing this package registers every named predicate (predicates.py's registry) via
each module's own `@predicate(...)` decorator -- so anything that imports
`reconcile.predicates` (e.g. config.py, validating a section's `predicate` name at load)
sees the full registry, not just whichever predicate module it happened to import directly.
"""

from agent_pipeline.reconcile import (
    sections as sections,  # noqa: F401  (side effect: registers predicates)
)
