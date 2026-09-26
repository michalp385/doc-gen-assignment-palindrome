#!/usr/bin/env bash
# PostToolUse(Edit|Write|MultiEdit): format + lint the file just touched.
# Unfixable lint -> exit 2, so Claude sees it and fixes it now, not at end of turn.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:?}"
source .claude/hooks/config.sh
require_jq

input=$(cat)
file=$(jq -r '.tool_input.file_path // empty' <<<"$input")
[[ -z "$file" || ! -f "$file" ]] && exit 0
rel=${file#"$CLAUDE_PROJECT_DIR/"}
[[ "$rel" =~ $CODE_EXT_REGEX ]] || exit 0

out=$($RUN $LINT_FILE_CMD "$rel" 2>&1); lint_status=$?   # fix first...
$RUN $FORMAT_FILE_CMD "$rel" >/dev/null 2>&1              # ...then format the result
if (( lint_status != 0 )); then
  { echo "Lint problems in $rel after your edit (auto-fixes already applied):"
    echo "$out" | tail -n 40; } >&2
  exit 2
fi
exit 0
