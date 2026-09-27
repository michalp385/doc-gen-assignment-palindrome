"""The overfitting allowlist is file-scoped, not global (T8).

An entry written 'path: value' exempts that value only in that one file; a value the
sources also happen to use is still flagged everywhere else in src/ and config/.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def _load_check_repo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_repo", ROOT / "scripts" / "check_repo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECK_REPO = _load_check_repo()


def test_load_allowlist_distinguishes_global_from_file_scoped(tmp_path: Path, monkeypatch) -> None:
    allowlist = tmp_path / "overfit_allowlist.txt"
    allowlist.write_text(
        "# comment\n"
        "genuinely-global-term  # applies everywhere\n"
        "config/tax_rules.json: 20000  # ISA allowance, a general rule\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(CHECK_REPO, "ALLOWLIST_FILE", allowlist)

    global_allow, per_file = CHECK_REPO.load_allowlist()

    assert global_allow == {"genuinely-global-term"}
    assert per_file == {"config/tax_rules.json": {"20000"}}


def test_the_repos_own_isa_allowance_entry_is_file_scoped() -> None:
    global_allow, per_file = CHECK_REPO.load_allowlist()
    assert "20000" not in global_allow
    assert per_file.get("config/tax_rules.json") == {"20000"}


def test_check_overfitting_allows_a_value_only_in_its_scoped_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(CHECK_REPO, "ROOT", tmp_path)
    monkeypatch.setattr(CHECK_REPO, "DATA", tmp_path / "data")
    monkeypatch.setattr(CHECK_REPO, "SCAN_DIRS", [tmp_path / "src", tmp_path / "config"])

    client_dir = tmp_path / "data" / "client_x"
    client_dir.mkdir(parents=True)
    (client_dir / "client_data_db.json").write_text(
        json.dumps(
            {
                "holders": {
                    "client": {
                        "name": "Somebody Fictional",
                        "accounts": [{"account_id": "X-1", "value": 20000, "platform": "Holloway"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "tax_rules.json").write_text('{"isa": {"2026/27": 20000}}', encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "other.py").write_text("LIMIT = 20000\n", encoding="utf-8")

    per_file_allow = {"config/tax_rules.json": {"20000"}}
    problems = CHECK_REPO.check_overfitting(set(), per_file_allow)

    problem_files = {p.split(":")[0] for p in problems}
    assert "config/tax_rules.json" not in problem_files
    assert "src/other.py" in problem_files
