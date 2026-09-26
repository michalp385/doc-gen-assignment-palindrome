#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit|Bash): committed tests are the spec.
# Changing a test file that's already in git needs YOUR approval.
# New/untracked test files (e.g. red phase of TDD) pass freely.
# Stops the "agent rewrites the tests to match its bug" failure mode.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:?}"
source .claude/hooks/config.sh
require_jq

input=$(cat)
tool=$(jq -r '.tool_name' <<<"$input")
mode=$(jq -r '.permission_mode // "default"' <<<"$input")
target=""

is_committed() { git ls-files --error-unmatch -- "$1" >/dev/null 2>&1; }

case "$tool" in
  Edit|Write|MultiEdit)
    f=$(jq -r '.tool_input.file_path // empty' <<<"$input")
    rel=${f#"$CLAUDE_PROJECT_DIR/"}
    if [[ "$rel" =~ $TEST_PATH_REGEX ]] && is_committed "$rel"; then target="$rel"; fi
    ;;
  Bash)
    # Best-effort: shell commands that write to/move/delete a test path.
    cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
    test_ref='(tests?|__tests__)/|test_[A-Za-z0-9_]*\.py|_test\.(py|go)|\.(test|spec)\.[jt]sx?'
    writes='(^|[^0-9&])>+[[:space:]]*[^&/[:space:]]|sed[[:space:]]+-i|perl[[:space:]]+-[a-z]*i|(^|[^[:alnum:]_-])(tee|mv|rm|cp|truncate)[[:space:]]|git[[:space:]]+(checkout|restore|stash|rm|mv)'
    if [[ "$cmd" =~ $test_ref ]] && [[ "$cmd" =~ $writes ]]; then target="shell: $cmd"; fi
    ;;
esac
[[ -z "$target" ]] && exit 0

reason="Guard: '$target' modifies a committed test (the spec). State in one line which behaviour changes and why the old test was wrong; the user decides."
case "$mode" in
  bypassPermissions|dontAsk|auto) decision="deny" ;;   # no human in the loop -> block
  *)                              decision="ask"  ;;   # prompt you
esac
jq -n --arg d "$decision" --arg r "$reason" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'
