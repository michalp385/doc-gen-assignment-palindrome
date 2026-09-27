#!/usr/bin/env bash
# PreToolUse(Bash): require explicit human approval for any command that could make a
# live OpenAI API call — in every permission mode, including auto. Cost and the
# correctness of committed outputs/cache both depend on a human seeing this before it
# runs (CLAUDE.md: cache LLM calls, estimate and ask before any live batch).
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:?}"
source .claude/hooks/config.sh
require_jq

input=$(cat)
tool=$(jq -r '.tool_name' <<<"$input")
[[ "$tool" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -z "$cmd" ]] && exit 0

# Single quote pulled in via a variable so it can sit inside a double-quoted ERE without
# fighting bash's own quoting.
SQ="'"
LIVE_API_RE="-m[[:space:]]+[\"$SQ]?live[\"$SQ]?"
LIVE_API_RE+="|agent_pipeline\.generate"
LIVE_API_RE+="|report_eval\.run"
LIVE_API_RE+="|--fresh"
LIVE_API_RE+="|OpenAI\("
LIVE_API_RE+="|[Oo]penai\.[A-Za-z_]+\("
LIVE_API_RE+="|chat\.completions\.create"
LIVE_API_RE+="|responses\.(parse|create)\("

echo "$cmd" | grep -Eq -e "$LIVE_API_RE" || exit 0

reason="Guard: this command can make a live OpenAI API call. Needs your explicit approval every time, even in auto mode, per your standing instruction."
mode=$(jq -r '.permission_mode // "default"' <<<"$input")
case "$mode" in
  bypassPermissions|dontAsk) decision="deny" ;;   # no human in the loop -> block, don't silently run
  *)                         decision="ask"  ;;   # includes "auto": always prompt
esac
jq -n --arg d "$decision" --arg r "$reason" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'
