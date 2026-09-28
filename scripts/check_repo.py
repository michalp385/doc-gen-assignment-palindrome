"""Repo-level invariants for the pipeline, run by scripts/check.sh (Stop hook + CI).

1. Overfitting: no client-specific names, account IDs or figures in src/agent_pipeline/ or
   config/ -- the pipeline package, which must generalise to clients it has never seen
   (CLAUDE.md). src/report_eval/ (eval and test tooling) is exempt: like eval/expected/*.json,
   its whole job is to encode known facts about specific hand-written clients (D<DECISION>).
   The denylist is derived from data/ at run time, so it grows automatically as clients
   (including synthetic ones) are added.
2. Secrets: no OpenAI-style keys in tracked files.
3. Static regulatory text: the FCA line and the risk warning must exist verbatim in src/ or config/.
4. Protected file: src/document_formatter/formatting.py unchanged from the upstream commit.

Allowlist genuinely general values in scripts/overfit_allowlist.txt, one per line, with a
reason after a '#'. A bare value is allowed everywhere in the overfitting scan, e.g.
`20000  # UK ISA annual allowance, a general rule`. Prefer scoping it to the one file that
needs it, `path/relative/to/repo: value  # reason`, e.g.
`config/tax_rules.json: 20000  # ISA allowance, a general rule` -- the exemption then
doesn't also cover that value showing up unexplained anywhere else in the scan.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCAN_DIRS = [ROOT / "src", ROOT / "config"]
# Overfitting only: src/report_eval/ is deliberately excluded (module docstring, point 1).
OVERFIT_EXCLUDE_PREFIX = "src/report_eval/"
SCAN_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".md", ".txt", ".j2", ".jinja", ".toml"}
ALLOWLIST_FILE = ROOT / "scripts" / "overfit_allowlist.txt"

FCA_LINE = "This firm is authorised and regulated by the Financial Conduct Authority."
RISK_WARNING = (
    "The value of investments can fall as well as rise and you may get back less than you invest."
)
RISK_WARNING_2 = "Past performance is not a guide to future returns."

PROTECTED = "src/document_formatter/formatting.py"
UPSTREAM_COMMIT = "0f7c264"

# DESIGN.md section 9: llm.py is the only module that imports openai.
OPENAI_IMPORT_ONLY_IN = "src/agent_pipeline/llm.py"
OPENAI_IMPORT_RE = re.compile(r"^\s*(import\s+openai\b|from\s+openai\b)")

MIN_AMOUNT = 1000  # ignore small numbers: too generic to signal overfitting
SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
MONEY_RE = re.compile(r"£\s?(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d+)?")


def docx_text(path: Path) -> str:
    """Plain text of a .docx without extra dependencies."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    return re.sub(r"<[^>]+>", " ", xml)


def load_allowlist() -> tuple[set[str], dict[str, set[str]]]:
    """Return (global_values, per_file_values), both lower-cased. A line 'path: value'
    scopes the exemption to that one file; a bare 'value' line is global."""
    global_values: set[str] = set()
    per_file: dict[str, set[str]] = {}
    if not ALLOWLIST_FILE.exists():
        return global_values, per_file
    for raw_line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        path, sep, value = line.partition(":")
        if sep and value.strip() and "/" in path:
            per_file.setdefault(path.strip(), set()).add(value.strip().lower())
        else:
            global_values.add(line.lower())
    return global_values, per_file


def collect_denylist() -> tuple[set[str], set[int]]:
    """Return (terms, amounts) that must not appear in src/ or config/."""
    terms: set[str] = set()
    amounts: set[int] = set()
    if not DATA.exists():
        return terms, amounts
    for client_dir in sorted(p for p in DATA.iterdir() if p.is_dir()):
        db = client_dir / "client_data_db.json"
        if db.exists():
            data = json.loads(db.read_text(encoding="utf-8"))
            for holder in data.get("holders", {}).values():
                name = holder.get("name") or ""
                terms.add(name)
                terms.update(part for part in name.split() if len(part) > 2)
                for acc in holder.get("accounts", []):
                    if acc.get("account_id"):
                        terms.add(acc["account_id"])
                    if acc.get("platform"):
                        terms.add(acc["platform"])
                    value = acc.get("value")
                    if isinstance(value, (int, float)) and value >= MIN_AMOUNT:
                        amounts.add(int(value))
        for doc in client_dir.glob("*.docx"):
            for match in MONEY_RE.finditer(docx_text(doc)):
                value = int(match.group(1).replace(",", ""))
                if value >= MIN_AMOUNT:
                    amounts.add(value)
    return {t for t in terms if t}, amounts


def amount_patterns(value: int) -> list[re.Pattern[str]]:
    forms = {str(value), f"{value:,}"}
    if value % 1000 == 0:
        forms.add(f"{value // 1000}k")
    return [re.compile(rf"(?<![\d,.]){re.escape(f)}(?![\d,])", re.IGNORECASE) for f in forms]


def scan_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_DIRS:
        if base.exists():
            files.extend(p for p in base.rglob("*") if p.is_file() and p.suffix in SCAN_SUFFIXES)
    return files


def check_overfitting(global_allow: set[str], per_file_allow: dict[str, set[str]]) -> list[str]:
    terms, amounts = collect_denylist()
    term_res = [
        (t, re.compile(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", re.IGNORECASE))
        for t in sorted(terms)
    ]
    amount_res = [(str(a), p) for a in sorted(amounts) for p in amount_patterns(a)]
    problems = []
    for path in scan_files():
        rel = path.relative_to(ROOT)
        rel_str = rel.as_posix()
        if rel_str.startswith(OVERFIT_EXCLUDE_PREFIX):
            continue
        file_allow = per_file_allow.get(rel_str, set())
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for label, pattern in term_res + amount_res:
                if label.lower() in global_allow or label.lower() in file_allow:
                    continue
                if pattern.search(line):
                    problems.append(f"{rel}:{lineno}: client-specific value '{label}'")
    return sorted(set(problems))


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False)
    return [ROOT / f for f in out.stdout.splitlines() if f]


def check_secrets() -> list[str]:
    problems = []
    for path in tracked_files():
        if path.name == ".env":
            problems.append(f"{path.relative_to(ROOT)}: .env is tracked by git")
            continue
        if not path.is_file() or path.suffix in {".png", ".jpg", ".jpeg", ".docx", ".lock"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_RE.search(text):
            problems.append(f"{path.relative_to(ROOT)}: looks like an API key")
    return problems


def check_static_text() -> list[str]:
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in scan_files())
    corpus = re.sub(r"\s+", " ", corpus)
    problems = []
    required = [
        ("FCA line", FCA_LINE),
        ("risk warning (1/2)", RISK_WARNING),
        ("risk warning (2/2)", RISK_WARNING_2),
    ]
    for label, text in required:
        if text not in corpus:
            problems.append(f"{label} not found verbatim in src/ or config/: {text!r}")
    return problems


def check_protected() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--quiet", UPSTREAM_COMMIT, "--", PROTECTED],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode == 1:
        return [f"{PROTECTED} differs from upstream {UPSTREAM_COMMIT}; it must stay as provided"]
    return []  # 0 = unchanged; 128 = commit unknown (e.g. shallow clone): skip rather than fail


def check_openai_import() -> list[str]:
    problems = []
    src = ROOT / "src"
    if not src.exists():
        return problems
    for path in src.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == OPENAI_IMPORT_ONLY_IN:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if OPENAI_IMPORT_RE.match(line):
                problems.append(
                    f"{rel}:{lineno}: imports openai (only {OPENAI_IMPORT_ONLY_IN} may)"
                )
    return problems


def main() -> int:
    global_allow, per_file_allow = load_allowlist()
    sections = {
        "overfitting": check_overfitting(global_allow, per_file_allow),
        "secrets": check_secrets(),
        "static text": check_static_text(),
        "protected files": check_protected(),
        "openai import": check_openai_import(),
    }
    failed = False
    for name, problems in sections.items():
        if problems:
            failed = True
            print(f"!! {name}:")
            for p in problems:
                print(f"   {p}")
        else:
            print(f"ok {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
