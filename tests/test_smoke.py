"""Offline smoke tests: the config is well-formed. Never calls the API."""

import json
import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "template_config.json"


def test_config_loads_with_sections() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["sections"], "config must define at least one section"


def test_every_placeholder_slot_has_a_spec() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    for section in config["sections"]:
        slots = set(re.findall(r"<<(\w+)>>", section.get("template", "")))
        specs = set(section.get("placeholders", {}))
        assert slots == specs, f"{section['id']}: slots {slots} != placeholder specs {specs}"
