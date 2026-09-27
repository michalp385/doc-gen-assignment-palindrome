"""Source classification (DESIGN.md sections 3.1-3.2): which role each file in a client
folder plays, decided by what a document *is*, never its filename. JSON is checked
structurally against the account-data schema; images are flagged as statement-image
candidates (confirmed later, stage 2); every other file goes to one classifier call that
decides a role by function. Code then applies the consistency rules: a report needs account
data, a report instruction and a meeting record, or there is no safe basis to continue
(section 8.4) -- the same "stop, don't guess" shape as T7's `AccountDataError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from agent_pipeline.config import PromptSpec
from agent_pipeline.llm import LLMClient
from agent_pipeline.sources.adapters.docx import read_docx
from agent_pipeline.sources.adapters.json_accounts import AccountDataError, read_accounts
from agent_pipeline.sources.adapters.markdown import read_markdown
from agent_pipeline.sources.document import SourceDoc

Role = Literal[
    "account_data",
    "meeting_record",
    "report_instruction",
    "report_spec",
    "internal_guidance",
    "statement_image",
    "general_document",
    "unknown",
]

# account_data and statement_image are assigned only by the structural check (DESIGN.md
# section 3.2 rule 1), never by the text classifier. The prompt tells the model to avoid
# them, but that's not enforcement: _classify_text defensively downgrades to unknown if a
# classifier (model or stub) returns one anyway, so a text file can never reach
# _content_key's read_accounts() call with role="account_data" (verifier report, T12
# pre-commit checkpoint, finding #1 -- that used to crash the whole run instead of
# degrading). Deliberately not also narrowed at the pydantic-schema level: that would turn
# an errant model role into a schema-validation failure instead, trading one uncaught crash
# for another if the model got it wrong twice in a row (one re-ask, T11's LLMClient).
_STRUCTURAL_ONLY_ROLES: frozenset[Role] = frozenset({"account_data", "statement_image"})

_REQUIRED_ROLES: tuple[Role, ...] = ("account_data", "report_instruction", "meeting_record")
_DEDUP_ROLES: tuple[Role, ...] = ("account_data", "report_instruction")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_TEXT_READERS = {".docx": read_docx, ".md": read_markdown}
_EXCERPT_CHARS = 2000


@dataclass(frozen=True)
class ClassifiedSource:
    path: Path
    role: Role
    method: Literal["structural", "model"]
    evidence_quote: str | None = None
    confidence: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class ClassificationVerdict:
    role: Role
    evidence_quote: str
    confidence: float


class TextClassifier(Protocol):
    def classify_text(self, text: str) -> ClassificationVerdict: ...


@dataclass(frozen=True)
class ClassificationResult:
    sources: list[ClassifiedSource] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ClassificationStopError(Exception):
    """No safe basis to continue (DESIGN.md section 8.4): a required role is missing, or two
    account-data/report-instruction sources disagree."""


def _doc_text(doc: SourceDoc) -> str:
    # A .docx's substantive content can live entirely in a table (e.g. report_request.docx's
    # label | value rows, T7): paragraphs alone can be just a heading, giving the classifier
    # almost nothing to go on.
    lines = list(doc.paragraphs.values())
    lines.extend(" | ".join(row) for table in doc.tables for row in table)
    return "\n".join(lines)


def _classify_structural(path: Path) -> ClassifiedSource | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            read_accounts(path)
        except AccountDataError as exc:
            return ClassifiedSource(path, "unknown", "structural", reason=str(exc))
        return ClassifiedSource(path, "account_data", "structural")
    if suffix in _IMAGE_SUFFIXES:
        return ClassifiedSource(path, "statement_image", "structural")
    return None


def _classify_text(
    path: Path, classifier: TextClassifier, confidence_threshold: float
) -> ClassifiedSource:
    reader = _TEXT_READERS[path.suffix.lower()]
    doc = reader(path)
    full_text = _doc_text(doc)
    verdict = classifier.classify_text(full_text[:_EXCERPT_CHARS])

    if verdict.role in _STRUCTURAL_ONLY_ROLES:
        return ClassifiedSource(
            path,
            "unknown",
            "model",
            evidence_quote=verdict.evidence_quote,
            confidence=verdict.confidence,
            reason=f"model returned {verdict.role!r}, a structural-only role; treated as unknown",
        )
    if verdict.confidence < confidence_threshold:
        return ClassifiedSource(
            path,
            "unknown",
            "model",
            evidence_quote=verdict.evidence_quote,
            confidence=verdict.confidence,
            reason=f"confidence {verdict.confidence} below threshold {confidence_threshold}",
        )
    if verdict.evidence_quote not in full_text:
        return ClassifiedSource(
            path,
            "unknown",
            "model",
            evidence_quote=verdict.evidence_quote,
            confidence=verdict.confidence,
            reason="evidence quote not found in the document",
        )
    return ClassifiedSource(
        path,
        verdict.role,
        "model",
        evidence_quote=verdict.evidence_quote,
        confidence=verdict.confidence,
    )


def _classify_one(
    path: Path, classifier: TextClassifier, confidence_threshold: float
) -> ClassifiedSource:
    structural = _classify_structural(path)
    if structural is not None:
        return structural
    if path.suffix.lower() in _TEXT_READERS:
        return _classify_text(path, classifier, confidence_threshold)
    return ClassifiedSource(path, "unknown", "structural", reason="unrecognised file type")


def _content_key(source: ClassifiedSource) -> str:
    if source.role == "account_data":
        # Only ever reached for a source _classify_structural itself assigned account_data
        # to (a real JSON file that already parsed once) -- a text file can never carry this
        # role here, see _STRUCTURAL_ONLY_ROLES above.
        return read_accounts(source.path).model_dump_json()
    reader = _TEXT_READERS[source.path.suffix.lower()]
    return _doc_text(reader(source.path))


def _resolve_required_role(
    role: Role, matches: list[ClassifiedSource], notes: list[str]
) -> list[ClassifiedSource]:
    if not matches:
        raise ClassificationStopError(f"no {role} found: no safe basis to continue")
    if role not in _DEDUP_ROLES or len(matches) == 1:
        return matches

    keys = {_content_key(m) for m in matches}
    if len(keys) > 1:
        raise ClassificationStopError(
            f"two {role} sources disagree: {[str(m.path) for m in matches]}"
        )
    kept, *dropped = matches
    notes.append(
        f"{role}: {len(dropped)} duplicate copy(ies) of {kept.path} deduplicated "
        f"({', '.join(str(d.path) for d in dropped)})"
    )
    return [kept]


def classify(
    folder: Path, classifier: TextClassifier, *, confidence_threshold: float = 0.7
) -> ClassificationResult:
    all_sources = [
        _classify_one(path, classifier, confidence_threshold)
        for path in sorted(folder.iterdir())
        if path.is_file()
    ]

    notes: list[str] = []
    by_role: dict[Role, list[ClassifiedSource]] = {}
    for source in all_sources:
        by_role.setdefault(source.role, []).append(source)

    resolved: list[ClassifiedSource] = []
    for role in _REQUIRED_ROLES:
        resolved.extend(_resolve_required_role(role, by_role.pop(role, []), notes))
    for remaining in by_role.values():
        resolved.extend(remaining)

    return ClassificationResult(sources=resolved, notes=notes)


class _ClassifierOutput(BaseModel):
    role: Role
    evidence_quote: str
    confidence: float


class LLMTextClassifier:
    """The real `TextClassifier` (DESIGN.md section 3.2 rule 2), wrapping T11's `LLMClient`
    and `config/prompts/classify.md`."""

    def __init__(self, llm_client: LLMClient, prompt: PromptSpec) -> None:
        self._llm = llm_client
        self._prompt = prompt

    def classify_text(self, text: str) -> ClassificationVerdict:
        result = self._llm.structured(
            stage="classify",
            prompt=self._prompt,
            inputs={"text": text},
            schema=_ClassifierOutput,
        )
        return ClassificationVerdict(
            role=result.output.role,
            evidence_quote=result.output.evidence_quote,
            confidence=result.output.confidence,
        )
