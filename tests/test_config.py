"""Report config loading (T10): extends merge by id, predicate validation, static text,
prompt content-hash versioning. DESIGN.md sections 7.1, 7.3, 11.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_pipeline.config import ConfigError, load_prompt, load_report_config
from agent_pipeline.gates.deterministic import FCA_LINE, RISK_WARNING_FULL

CONFIG_DIR = Path("config")


def _write_configs(tmp_path: Path, base: dict, child: dict) -> Path:
    (tmp_path / "base.json").write_text(json.dumps(base), encoding="utf-8")
    child_path = tmp_path / "child.json"
    child_path.write_text(json.dumps(child), encoding="utf-8")
    return child_path


def _section(section_id: str, **overrides: object) -> dict:
    section = {
        "id": section_id,
        "title": section_id.title(),
        "use_if": "always",
        "template": "<<x>>",
        "placeholders": {"x": {"kind": "generated", "prompt": "say something"}},
    }
    section.update(overrides)
    return section


def test_merge_by_id_keeps_base_section_when_child_has_no_override(tmp_path: Path) -> None:
    base = {
        "document_title": "Base",
        "global_instructions": "",
        "sections": [_section("introduction", title="Introduction")],
    }
    child = {"extends": "base.json", "sections": []}
    path = _write_configs(tmp_path, base, child)

    config = load_report_config(path)

    assert [s.id for s in config.sections] == ["introduction"]
    assert config.sections[0].title == "Introduction"


def test_merge_by_id_lets_a_child_override_one_field_and_keep_the_rest(tmp_path: Path) -> None:
    base = {
        "document_title": "Base",
        "global_instructions": "",
        "sections": [_section("introduction", title="Introduction", use_if="always")],
    }
    child = {
        "extends": "base.json",
        "sections": [{"id": "introduction", "title": "Overridden Title"}],
    }
    path = _write_configs(tmp_path, base, child)

    config = load_report_config(path)

    assert len(config.sections) == 1
    resolved = config.sections[0]
    assert resolved.title == "Overridden Title"  # overridden
    assert resolved.use_if == "always"  # kept from base
    assert resolved.template == "<<x>>"  # kept from base


def test_merge_by_id_appends_a_child_only_section_after_base_sections(tmp_path: Path) -> None:
    base = {
        "document_title": "Base",
        "global_instructions": "",
        "sections": [_section("introduction"), _section("conclusion")],
    }
    child = {"extends": "base.json", "sections": [_section("recommendations")]}
    path = _write_configs(tmp_path, base, child)

    config = load_report_config(path)

    assert [s.id for s in config.sections] == ["introduction", "conclusion", "recommendations"]


def test_unknown_predicate_fails_at_load(tmp_path: Path) -> None:
    base = {
        "document_title": "Base",
        "global_instructions": "",
        "sections": [_section("tax_implications", predicate="not_a_real_predicate")],
    }
    child = {"extends": "base.json", "sections": []}
    path = _write_configs(tmp_path, base, child)

    with pytest.raises(ConfigError, match="not_a_real_predicate"):
        load_report_config(path)


def test_a_registered_predicate_loads_without_error(tmp_path: Path) -> None:
    base = {
        "document_title": "Base",
        "global_instructions": "",
        "sections": [_section("tax_implications", predicate="taxable_disposal")],
    }
    child = {"extends": "base.json", "sections": []}
    path = _write_configs(tmp_path, base, child)

    config = load_report_config(path)

    assert config.sections[0].predicate == "taxable_disposal"


def test_no_predicate_at_all_is_fine() -> None:
    # DESIGN.md section 7.1: no predicate is a legitimate config, not an error -- it falls
    # back to a model judgement from ledger facts, flagged for review. Only a *misspelled*
    # predicate name fails loading.
    config = load_report_config(CONFIG_DIR / "template_config.json")
    recommendations = next(s for s in config.sections if s.id == "recommendations")
    assert recommendations.predicate is None


def test_the_shipped_config_loads_and_resolves() -> None:
    config = load_report_config(CONFIG_DIR / "template_config.json")
    assert {s.id for s in config.sections} == {
        "introduction",
        "fees_charges",
        "conclusion",
        "background_objectives",
        "recommendations",
        "tax_implications",
    }
    assert config.stages  # base's stage models carried through


def test_introduction_carries_the_fca_line_as_literal_template_text_not_a_slot() -> None:
    config = load_report_config(CONFIG_DIR / "template_config.json")
    introduction = next(s for s in config.sections if s.id == "introduction")
    assert FCA_LINE in introduction.template
    assert "<<" not in FCA_LINE  # sanity: not accidentally itself a slot reference


def test_conclusion_carries_the_risk_warning_as_literal_template_text_not_a_slot() -> None:
    config = load_report_config(CONFIG_DIR / "template_config.json")
    conclusion = next(s for s in config.sections if s.id == "conclusion")
    assert RISK_WARNING_FULL in conclusion.template


def test_tax_implications_predicate_matches_t8s_registered_predicate() -> None:
    config = load_report_config(CONFIG_DIR / "template_config.json")
    tax = next(s for s in config.sections if s.id == "tax_implications")
    assert tax.predicate == "taxable_disposal"


def test_load_prompt_version_changes_with_text(tmp_path: Path) -> None:
    path = tmp_path / "writer.md"
    path.write_text("Write the section.", encoding="utf-8")
    first = load_prompt(path)

    path.write_text("Write the section, differently.", encoding="utf-8")
    second = load_prompt(path)

    assert first.version != second.version
    assert first.text != second.text


def test_load_prompt_version_is_stable_for_the_same_text(tmp_path: Path) -> None:
    path_a = tmp_path / "a.md"
    path_b = tmp_path / "b.md"
    path_a.write_text("Same instructions.", encoding="utf-8")
    path_b.write_text("Same instructions.", encoding="utf-8")

    assert load_prompt(path_a).version == load_prompt(path_b).version


def test_load_prompt_version_changes_with_the_output_schema(tmp_path: Path) -> None:
    path = tmp_path / "writer.md"
    path.write_text("Write the section.", encoding="utf-8")

    plain = load_prompt(path)
    with_schema = load_prompt(path, output_schema='{"paragraphs": ["str"]}')

    assert plain.version != with_schema.version
