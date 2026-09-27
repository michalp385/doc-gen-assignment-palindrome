"""T15: `build_run_summary` (pure aggregation over trace-line-shaped dicts),
`build_review_sheet` (DESIGN.md section 8.5's 9 sections), `write_draft_or_failed` and
`write_input_stop` (section 8.3's release-state files, and the stale-file swap)."""

from __future__ import annotations

from pathlib import Path

from agent_pipeline.assemble import (
    RunSummary,
    build_review_sheet,
    build_run_summary,
    write_draft_or_failed,
    write_input_stop,
)
from agent_pipeline.config import ReportConfig, Section, StageConfig
from agent_pipeline.gates.deterministic import GateResult, ReportBundle
from agent_pipeline.ledger import Account, Ledger, Marker, ReviewItem
from agent_pipeline.sources.classify import ClassificationResult, ClassifiedSource


def _config() -> ReportConfig:
    return ReportConfig(
        document_title="Investment Advice Report",
        global_instructions="Write in British English.",
        stages={"write": StageConfig(model="gpt-6-luna", reasoning_effort="low")},
        sections=[
            Section(id="introduction", title="Introduction", use_if="always", template="<<x>>"),
            Section(
                id="tax_implications",
                title="Tax Implications",
                use_if="Include on disposal.",
                predicate="taxable_disposal",
                template="<<cgt_statement>>",
            ),
        ],
    )


def _ledger(**overrides) -> Ledger:
    base = Ledger(
        client="client_01_clean",
        tax_section=True,
        accounts=[
            Account(id="H-ISA-01", owners=["Margaret Hughes"], type="ISA", in_scope=True),
            Account(
                id="H-CASH-01",
                owners=["Margaret Hughes"],
                type="Cash Account",
                in_scope=False,
                scope_reason="not named in the report instruction's scope phrase",
            ),
        ],
        markers=[
            Marker(
                id="#1",
                key="advice_charge",
                text="ongoing advice charge rate",
                reason="never estimated",
                section="fees_charges",
            )
        ],
        review=[
            ReviewItem(id="rv1", kind="marker_reference", detail="see marker advice_charge"),
            ReviewItem(
                id="rv2", kind="open_action", blocking=True, detail="confirm the cash account"
            ),
            ReviewItem(id="rv3", kind="open_action", blocking=False, detail="send the annual pack"),
            ReviewItem(id="rv4", kind="p4_note", detail="ISA allowance note"),
            ReviewItem(id="rv5", kind="degradation", detail="meeting date taken from metadata"),
        ],
    )
    return base.model_copy(update=overrides)


def test_build_run_summary_aggregates_calls_and_tokens_per_stage():
    trace_entries = [
        {
            "stage": "write",
            "model": "gpt-6-luna",
            "prompt_version": "v1",
            "cache_hit": True,
            "tokens": {"input_tokens": 100, "output_tokens": 20},
            "cost_usd": "0.0000",
            "latency_s": 0.0,
        },
        {
            "stage": "write",
            "model": "gpt-6-luna",
            "prompt_version": "v1",
            "cache_hit": False,
            "tokens": {"input_tokens": 50, "output_tokens": 10, "reasoning_tokens": 5},
            "cost_usd": "0.0012",
            "latency_s": 1.5,
        },
        {
            "stage": "classify",
            "model": "gpt-6-luna",
            "prompt_version": "v2",
            "cache_hit": False,
            "tokens": {"input_tokens": 30, "output_tokens": 5},
            "cost_usd": "0.0003",
            "latency_s": 0.5,
        },
    ]
    summary = build_run_summary("client_01_clean", "draft", [], trace_entries)
    by_stage = {s.stage: s for s in summary.stages}

    write_stage = by_stage["write"]
    assert write_stage.calls == 2
    assert write_stage.cache_hits == 1
    assert write_stage.live_calls == 1
    assert write_stage.input_tokens == 150
    assert write_stage.output_tokens == 30
    assert write_stage.reasoning_tokens == 5
    assert str(write_stage.cost_usd) == "0.0012"

    assert summary.total_calls == 3
    assert summary.total_cache_hits == 1
    assert summary.total_live_calls == 2


def test_review_sheet_renders_all_nine_sections():
    summary = RunSummary(
        client="client_01_clean",
        release_state="draft",
        gate_results=[GateResult("G1", True), GateResult("G4", True)],
    )
    sheet = build_review_sheet(_config(), _ledger(), "draft", summary)

    for heading in (
        "## Status",
        "## Blocking before sign-off",
        "## Other open actions (not blocking)",
        "## Markers to fill",
        "## Conflicts and how they were resolved",
        "## Superseded values",
        "## Accounts left out",
        "## Section decisions",
        "## Notes",
        "## How this draft degraded",
    ):
        assert heading in sheet

    assert "Release state: draft" in sheet
    assert "Gates: 2/2 passed" in sheet
    blocking_section = sheet.split("## Blocking before sign-off\n\n")[1].split("\n\n##")[0]
    other_section = sheet.split("## Other open actions (not blocking)\n\n")[1].split("\n\n##")[0]
    assert "confirm the cash account" in blocking_section
    assert "send the annual pack" not in blocking_section
    assert "send the annual pack" in other_section
    assert "confirm the cash account" not in other_section
    assert "#1: ongoing advice charge rate" in sheet  # markers to fill
    assert "H-CASH-01: not named in the report instruction's scope phrase" in sheet
    assert "Tax Implications: included (predicate: taxable_disposal)" in sheet
    assert "ISA allowance note" in sheet  # a note
    assert "meeting date taken from metadata" in sheet  # a degradation
    assert "## Superseded values\n\nNone." in sheet  # nothing to show renders "None."


def test_write_draft_removes_a_stale_failed_file(tmp_path: Path):
    outputs_dir = tmp_path
    (outputs_dir / "client_01_clean.failed.md").write_text("stale", encoding="utf-8")

    bundle = ReportBundle(report_text="This is the draft report.")
    summary = RunSummary(
        client="client_01_clean", release_state="draft", gate_results=[GateResult("G1", True)]
    )
    write_draft_or_failed(
        "client_01_clean",
        outputs_dir,
        bundle=bundle,
        ledger=_ledger(),
        config=_config(),
        release_state="draft",
        run_summary=summary,
    )

    assert (outputs_dir / "client_01_clean.md").read_text(encoding="utf-8") == bundle.report_text
    assert not (outputs_dir / "client_01_clean.failed.md").exists()
    assert (outputs_dir / "client_01_clean.review.md").exists()
    assert (outputs_dir / "client_01_clean.ledger.json").exists()
    assert (outputs_dir / "client_01_clean.run.json").exists()


def test_write_failed_removes_a_stale_draft_file(tmp_path: Path):
    outputs_dir = tmp_path
    (outputs_dir / "client_01_clean.md").write_text("stale draft", encoding="utf-8")

    summary = RunSummary(
        client="client_01_clean",
        release_state="failed",
        gate_results=[GateResult("G4", False, "paraphrase found")],
    )
    write_draft_or_failed(
        "client_01_clean",
        outputs_dir,
        bundle=None,
        ledger=_ledger(),
        config=_config(),
        release_state="failed",
        run_summary=summary,
        failed_reason="a hard gate failed",
    )

    assert not (outputs_dir / "client_01_clean.md").exists()
    failed_text = (outputs_dir / "client_01_clean.failed.md").read_text(encoding="utf-8")
    assert "NOT ISSUED" in failed_text
    assert "a hard gate failed" in failed_text
    assert "G4: paraphrase found" in failed_text


def test_write_input_stop_writes_reason_and_classification_only_no_draft_or_ledger(
    tmp_path: Path,
):
    outputs_dir = tmp_path
    (outputs_dir / "client_01_clean.md").write_text("stale draft", encoding="utf-8")
    (outputs_dir / "client_01_clean.ledger.json").write_text(
        '{"client": "client_01_clean"}', encoding="utf-8"
    )

    classification = ClassificationResult(
        sources=[
            ClassifiedSource(
                path=Path("report_request.docx"), role="report_instruction", method="structural"
            )
        ],
        notes=["platform_market_update.docx excluded: general document"],
    )
    write_input_stop(
        "client_01_clean",
        outputs_dir,
        reason="no readable account data",
        classification=classification,
    )

    assert not (outputs_dir / "client_01_clean.md").exists()
    assert not (outputs_dir / "client_01_clean.ledger.json").exists()
    failed_text = (outputs_dir / "client_01_clean.failed.md").read_text(encoding="utf-8")
    assert "no readable account data" in failed_text
    assert "report_request.docx: report_instruction (structural)" in failed_text
    assert "platform_market_update.docx excluded: general document" in failed_text
    assert (outputs_dir / "client_01_clean.review.md").exists()
    assert (outputs_dir / "client_01_clean.run.json").exists()
