"""Repo-level invariants for the pipeline, run by scripts/check.sh (Stop hook + CI).

1. Overfitting: no client-specific names, account IDs or figures in src/agent_pipeline/ or
   config/ -- the pipeline package, which must generalise to clients it has never seen
   (CLAUDE.md). src/report_eval/ (eval and test tooling) is exempt: like eval/expected/*.json,
   its whole job is to encode known facts about specific hand-written clients (D<DECISION>).
   The denylist is derived from data/ at run time, so it grows automatically as clients
   (including synthetic ones) are added.
   The same scan also denies (T29, DESIGN.md sections 7.3 and 16): the full names and account
   IDs of the synthetic clients under data/synthetic/ (never their platforms, amounts or single
   name parts -- a synthetic surname can be an ordinary word -- and never in src/report_eval/,
   whose generator holds the pools those clients were sampled from), the adviser names in the
   report-request tables, and the fund names in the general documents.
2. Secrets: no OpenAI-style keys in tracked files.
3. Static regulatory text: the FCA line and the risk warning must exist verbatim in src/ or config/.
4. Protected file: src/document_formatter/formatting.py unchanged from the upstream commit.
5. OpenAI import: only src/agent_pipeline/llm.py imports openai.
6. Prompt overlap (T29, DESIGN.md section 7.3): no run of six or more words is shared between
   a prompt in config/prompts/ and a source document under data/ (so a prompt can't quote a
   real meeting note). The report spec (template_spec.md) is exempt: it is the requirement the
   prompts serve, not a client source.

Allowlist genuinely general values in scripts/overfit_allowlist.txt, one per line, with a
reason after a '#'. A bare value is allowed everywhere in the overfitting scan, e.g.
`20000  # UK ISA annual allowance, a general rule`. Prefer scoping it to the one file that
needs it, `path/relative/to/repo: value  # reason`, e.g.
`config/tax_rules.json: 20000  # ISA allowance, a general rule` -- the exemption then
doesn't also cover that value showing up unexplained anywhere else in the scan. For the
prompt-overlap check the value is the shared run of words, lower-case with punctuation
dropped, scoped to the one prompt file; a longer run covers every six-word run inside it.
"""

from __future__ import annotations

import html
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

# DESIGN.md section 7.3: a prompt may not share a run of this many words with a source document.
PROMPTS_DIR = ROOT / "config" / "prompts"
OVERLAP_WORDS = 6
SPEC_NAME = "template_spec.md"  # the requirement the prompts serve, not a client source

# A fund or portfolio name in a general document: one to three capitalised words then the
# suffix. A leading article is not part of the name ("The Pendle Global Fund").
FUND_RE = re.compile(r"\b((?:[A-Z][A-Za-z]*(?:-[A-Za-z]+)*\s+){1,3}(?:Fund|Portfolio|Trust))\b")
LEADING_ARTICLES = {"The", "Our", "Its", "This", "These", "A", "An", "Both", "Each"}
FUND_SUFFIXES = {"Fund", "Portfolio", "Trust"}


def docx_text(path: Path) -> str:
    """Plain text of a .docx without extra dependencies."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    return re.sub(r"<[^>]+>", " ", xml)


def _docx_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8", errors="ignore")


def _xml_text(xml: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def docx_running_text(path: Path) -> str:
    """Plain text of a .docx with a space after each paragraph and table cell but none inside
    a word (a text run can split mid-word, so `docx_text`'s tag-to-space would cut it)."""
    xml = re.sub(r"</w:(?:p|tc)>", " ", _docx_xml(path))
    return _xml_text(xml)


def docx_table_rows(path: Path) -> list[list[str]]:
    rows = []
    for row in re.findall(r"<w:tr[ >].*?</w:tr>", _docx_xml(path), re.DOTALL):
        cells = re.findall(r"<w:tc>.*?</w:tc>", row, re.DOTALL)
        rows.append([_xml_text(cell).strip() for cell in cells])
    return rows


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


def collect_synthetic_terms() -> set[str]:
    """Full holder names and account IDs of the synthetic clients (hand-written and
    generated) -- names whole, never their parts, since a synthetic surname can be an
    ordinary word."""
    terms: set[str] = set()
    for db in sorted((DATA / "synthetic").rglob("client_data_db.json")):
        data = json.loads(db.read_text(encoding="utf-8"))
        for holder in data.get("holders", {}).values():
            if holder.get("name"):
                terms.add(holder["name"])
            terms.update(a["account_id"] for a in holder.get("accounts", []) if a.get("account_id"))
    return terms


def _fund_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in FUND_RE.finditer(text):
        words = match.group(1).split()
        while words and words[0] in LEADING_ARTICLES:
            words = words[1:]
        if len(words) >= 2 and words[-1] in FUND_SUFFIXES:
            names.add(" ".join(words))
    return names


def collect_general_terms() -> set[str]:
    """Adviser names (the 'Adviser' row of a report-request table, whole and by part) and
    fund names found in any source document under data/: none may appear in src/ or config/."""
    terms: set[str] = set()
    if not DATA.exists():
        return terms
    for doc in sorted(DATA.rglob("*.docx")):
        for row in docx_table_rows(doc):
            if len(row) >= 2 and row[0].strip().lower() == "adviser" and row[1]:
                terms.add(row[1])
                terms.update(part for part in row[1].split() if len(part) > 2)
        terms |= _fund_names(docx_running_text(doc))
    return terms


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
    terms = terms | collect_synthetic_terms() | collect_general_terms()
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


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _word_runs(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def _source_document_words() -> dict[str, list[str]]:
    """Every .docx and .md source document under data/ (client and synthetic alike) except
    the report spec, by repo-relative path."""
    documents: dict[str, list[str]] = {}
    if not DATA.exists():
        return documents
    for path in sorted(DATA.rglob("*")):
        if path.name == SPEC_NAME:
            continue
        if path.suffix == ".docx":
            text = docx_running_text(path)
        elif path.suffix == ".md":
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            continue
        documents[path.relative_to(ROOT).as_posix()] = _words(text)
    return documents


def check_prompt_overlap(per_file_allow: dict[str, set[str]]) -> list[str]:
    """DESIGN.md section 7.3: no run of OVERLAP_WORDS or more words is shared between a prompt
    and a source document. `per_file_allow[prompt_path]` holds allowlisted runs (normalised
    words); a run inside one of them is exempt for that prompt only."""
    documents = {
        rel: _word_runs(words, OVERLAP_WORDS) for rel, words in _source_document_words().items()
    }
    problems: list[str] = []
    if not PROMPTS_DIR.exists():
        return problems
    for prompt in sorted(PROMPTS_DIR.glob("*.md")):
        rel = prompt.relative_to(ROOT).as_posix()
        allowed = per_file_allow.get(rel, set())
        prompt_runs = _word_runs(_words(prompt.read_text(encoding="utf-8")), OVERLAP_WORDS)
        for doc_rel, doc_runs in documents.items():
            shared = {
                run
                for run in prompt_runs & doc_runs
                if not any(" ".join(run) in allowed_run for allowed_run in allowed)
            }
            if shared:
                example = " ".join(sorted(shared)[0])
                problems.append(
                    f"{rel}: shares {len(shared)} run(s) of {OVERLAP_WORDS}+ words with "
                    f"{doc_rel}, e.g. {example!r}"
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
        "prompt overlap": check_prompt_overlap(per_file_allow),
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
