"""Stage 3a, the conflict investigation agent (DESIGN.md section 5.2, D14).

A bounded loop with read-only tools that returns quoted findings for open questions; code
verifies and accepts or rejects them. `tools.py` is the read-only tool set, `agent.py` the loop,
`accept.py` the verification, `stage.py` the orchestration that turns outcomes into review-sheet
items, and `model.py` the LLM adapter. The agent never writes to the ledger, selects a value or
changes a rule, and investigation can never fail a run.
"""
