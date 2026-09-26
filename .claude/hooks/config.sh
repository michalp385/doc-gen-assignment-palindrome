# One place to adapt the kit to the stack. Sourced by every hook and scripts/check.sh.
# Every value can be overridden by an env var of the same name (CI uses this).

RUN="${RUN:-uv run}"   # command prefix. uv keeps tools in .venv, so they are not on PATH.

# Per-edit (PostToolUse): run on the single file just edited
FORMAT_FILE_CMD="${FORMAT_FILE_CMD:-ruff format}"
LINT_FILE_CMD="${LINT_FILE_CMD:-ruff check --fix}"
CODE_EXT_REGEX="${CODE_EXT_REGEX:-\.py$}"

# Full gate (Stop hook + CI via scripts/check.sh)
FORMAT_CHECK_CMD="${FORMAT_CHECK_CMD:-ruff format --check .}"
LINT_CMD="${LINT_CMD:-ruff check .}"
TYPECHECK_CMD="${TYPECHECK_CMD:-pyright}"
TEST_CMD="${TEST_CMD:-pytest -q}"                        # offline only: pyproject addopts excludes -m live
EXTRA_CHECK_CMD="${EXTRA_CHECK_CMD:-python scripts/check_repo.py}"   # overfitting, secrets, static text, protected files

# Paths
TEST_PATH_REGEX="${TEST_PATH_REGEX:-(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$}"
SRC_PATH_REGEX="${SRC_PATH_REGEX:-^(src|app|lib|packages)/}"
DEP_FILES_REGEX="${DEP_FILES_REGEX:-(^|/)(pyproject\.toml|requirements[^/]*\.txt|package\.json|Cargo\.toml|go\.mod)$}"
DOCS_REGEX="${DOCS_REGEX:-^(ARCHITECTURE\.md|DECISIONS\.md|DESIGN\.md|docs/)}"

STATE_DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/.state"

# Hooks parse their input with jq. Without it they would silently pass, so fail closed.
require_jq() {
  command -v jq >/dev/null 2>&1 && return 0
  echo "jq is not installed, so the Claude Code guard hooks cannot run. Install it (macOS: brew install jq)." >&2
  exit 2
}
