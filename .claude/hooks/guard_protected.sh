#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit|Bash): block edits to inputs and to the file that must
# stay as provided, and block staging .env. Hard deny: these are never legitimate here.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:?}"
source .claude/hooks/config.sh
require_jq
input=$(cat)
tool=$(jq -r '.tool_name' <<<"$input")
reason=""

case "$tool" in
  Edit|Write|MultiEdit)
    f=$(jq -r '.tool_input.file_path // empty' <<<"$input")
    rel=${f#"$CLAUDE_PROJECT_DIR/"}
    # data/ is read-only, except synthetic clients if the design adds a dedicated folder for them
    if [[ "$rel" == data/* && "$rel" != data/synthetic/* ]]; then reason="data/ holds the given client inputs and must not be edited."; fi
    if [[ "$rel" == "src/document_formatter/formatting.py" ]]; then reason="formatting.py must stay as provided."; fi
    ;;
  Bash)
    cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
    if [[ "$cmd" =~ git[[:space:]]+add ]] && [[ "$cmd" =~ (^|[[:space:]/])\.env([[:space:]]|$) ]]; then
      reason="Never stage .env: it holds the API key and the fork is public."
    fi
    ;;
esac
[[ -z "$reason" ]] && exit 0
jq -n --arg r "Guard: $reason" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
