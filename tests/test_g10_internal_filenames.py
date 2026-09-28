"""G10 catches an internal file name in the report deterministically (tests first).

A file name such as `client_data_db.json` is system information, never client-facing text:
the release judge flagged it once in the table footnote, but whether it is present has a
plain answer, so it is checked in code rather than left to a model's judgement.
"""

from __future__ import annotations

import dataclasses

import pytest

from agent_pipeline.gates.deterministic import run_gates
from report_eval.reference import build_reference_bundle

CLIENTS = ["client_01_clean", "client_02_medium", "client_03_hard", "client_04_stretch"]


def _g10(client: str, extra: str) -> tuple[bool, str]:
    bundle, truth = build_reference_bundle(client)
    mutated = dataclasses.replace(bundle, report_text=bundle.report_text + " " + extra)
    result = {r.gate: r for r in run_gates(mutated, truth)}["G10"]
    return result.passed, result.detail


@pytest.mark.parametrize(
    "name",
    [
        "client_data_db.json",
        "meeting_notes.docx",
        "fde_notes.md",
        "statement_summary.png",
        "scan.JPG",
        "report_request_2.docx",
    ],
)
def test_an_internal_file_name_fails_g10(name: str) -> None:
    passed, detail = _g10("client_01_clean", f"Your figure was shown in {name} earlier.")
    assert not passed
    assert name.lower() in detail.lower()


@pytest.mark.parametrize("client", CLIENTS)
def test_the_clean_reference_reports_have_no_file_name(client: str) -> None:
    bundle, truth = build_reference_bundle(client)
    assert {r.gate: r for r in run_gates(bundle, truth)}["G10"].passed


@pytest.mark.parametrize(
    "text",
    [
        "The account is held with Holloway, e.g. the ISA.",
        "See section 2.1 of your statement.",
        "The value was £45,000.5 at that time.",
        "Visit example.com for more.",
    ],
)
def test_ordinary_text_is_not_mistaken_for_a_file_name(text: str) -> None:
    passed, _ = _g10("client_01_clean", text)
    assert passed
