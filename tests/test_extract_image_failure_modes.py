"""T18 verifier checkpoint: `extract_image` must degrade to `readable=False` on ANY
extraction failure, not just a refusal (`EmptyOutputError`) -- a statement image is optional
and low-trust by design (DESIGN.md section 3.4), so a transient-retry exhaustion, a schema
failure surviving its re-ask, or the API rejecting a malformed image file must never crash
or block a report. Split from `tests/test_reconcile_values_p10.py` (already committed) rather
than editing it, since it only exercised the `EmptyOutputError` path."""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.extract.image import ImageExtraction, RawImageProposal, extract_image
from agent_pipeline.llm import SchemaValidationError, TransientAPIError
from agent_pipeline.sources.adapters.image import ImageSource

_IMAGE = ImageSource(path=Path("data/x/statement_summary.png"), content=b"fake-bytes")


class _RaisingModel:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def propose(self, image: ImageSource) -> RawImageProposal:
        raise self._exc


def test_exhausted_transient_retries_degrade_to_unreadable_not_a_crash() -> None:
    result = extract_image(_IMAGE, model=_RaisingModel(TransientAPIError("still failing")))

    assert isinstance(result, ImageExtraction)
    assert result.readable is False
    assert result.rows == []


def test_a_schema_failure_surviving_its_re_ask_degrades_to_unreadable() -> None:
    result = extract_image(_IMAGE, model=_RaisingModel(SchemaValidationError("bad shape")))

    assert result.readable is False


def test_an_unexpected_api_error_still_degrades_rather_than_propagating() -> None:
    # Stands in for openai.BadRequestError (a malformed image the API rejects outright) --
    # can't be raised by name here since llm.py is the only module allowed to import
    # openai, so a generic exception exercises the same catch-all path.
    result = extract_image(_IMAGE, model=_RaisingModel(RuntimeError("API rejected the image")))

    assert result.readable is False
