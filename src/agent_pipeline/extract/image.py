"""Statement-image extraction (P10, DESIGN.md section 3.4): one vision call reading every
row of the statement table raw and verbatim -- no arithmetic, no currency conversion, no
multi-round verification loop like the text extractors (T13). There is no text to re-ask
against, and P10's own trust rule means a misread never becomes a wrong report fact: it only
ever confirms, conflicts, or gets silently unmatched (`reconcile/values.py`), so one call is
enough.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from agent_pipeline.config import PromptSpec
from agent_pipeline.llm import EmptyOutputError, ImageInput, LLMClient
from agent_pipeline.sources.adapters.image import ImageSource


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageValueRow(_Strict):
    account_label: str  # the statement's own "Account" column, printed verbatim
    account_type: str  # the statement's own "Type" column, e.g. "Stocks & Shares ISA"
    amount_text: str  # the amount as printed -- parsed in code (T4), never by the model
    currency_symbol: str  # the currency symbol as printed
    valued_on_text: str | None = None  # the valuation date as printed


class RawImageProposal(_Strict):
    """Exactly what the model's structured output produces, one call."""

    rows: list[ImageValueRow] = Field(default_factory=list)


class ImageExtraction(_Strict):
    rows: list[ImageValueRow] = Field(default_factory=list)
    # False only when the vision call itself refused or returned nothing (EmptyOutputError) --
    # not when it read rows that later fail to match any account, which is a downstream P10
    # review item (reconcile/values.py), not an unreadable image.
    readable: bool = True


class ImageModel(Protocol):
    def propose(self, image: ImageSource) -> RawImageProposal: ...


class LLMImageModel:
    """The real `ImageModel`, wrapping T11's `LLMClient` and
    `config/prompts/extract_image.md`."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def propose(self, image: ImageSource) -> RawImageProposal:
        result = self._llm.structured(
            stage="extract",
            prompt=self._prompt,
            inputs={},
            schema=RawImageProposal,
            images=[ImageInput(name=image.path.name, content=image.content)],
        )
        return result.output


def extract_image(image: ImageSource, model: ImageModel) -> ImageExtraction:
    try:
        raw = model.propose(image)
    except EmptyOutputError:
        return ImageExtraction(rows=[], readable=False)
    return ImageExtraction(rows=raw.rows, readable=True)
