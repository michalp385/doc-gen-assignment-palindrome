"""`--clients all` discovery: a client is a report file (`<client>.md` or `<client>.failed.md`)
that has an `eval/expected/<client>.json`. Sibling files in the outputs dir (`<client>.review.md`,
ledgers, run summaries) are not clients, and a report with no expected facts is not scored, so
neither shows up as a bogus skipped client."""

from __future__ import annotations

from pathlib import Path

import pytest

from report_eval.run import _resolve_clients


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    outputs = tmp_path / "outputs"
    expected = tmp_path / "expected"
    outputs.mkdir()
    expected.mkdir()
    return outputs, expected


def _touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).write_text("x", encoding="utf-8")


def test_review_sheets_are_not_clients(dirs: tuple[Path, Path]) -> None:
    outputs, expected = dirs
    _touch(outputs, "alpha.md", "alpha.review.md", "alpha.ledger.json", "alpha.run.json")
    _touch(expected, "alpha.json")

    assert _resolve_clients(["all"], outputs, expected) == ["alpha"]


def test_a_failed_generation_is_found_by_its_client_name(dirs: tuple[Path, Path]) -> None:
    outputs, expected = dirs
    _touch(outputs, "beta.failed.md", "beta.review.md")
    _touch(expected, "beta.json")

    assert _resolve_clients(["all"], outputs, expected) == ["beta"]


def test_a_report_without_expected_facts_is_not_discovered(dirs: tuple[Path, Path]) -> None:
    outputs, expected = dirs
    _touch(outputs, "alpha.md", "gamma.md")
    _touch(expected, "alpha.json")

    assert _resolve_clients(["all"], outputs, expected) == ["alpha"]


def test_a_name_asked_for_explicitly_is_passed_through(dirs: tuple[Path, Path]) -> None:
    outputs, expected = dirs

    assert _resolve_clients(["gamma"], outputs, expected) == ["gamma"]
