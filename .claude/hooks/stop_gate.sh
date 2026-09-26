#!/usr/bin/env bash
# Stop: the turn can't end while scripts/check.sh fails (exit 2 = keep working).
# Skips when code is unchanged since the last green run, in plan mode,
# or when .claude/.state/skip_gate exists (escape hatch: `touch` it, `rm` to re-arm).
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:?}"
source .claude/hooks/config.sh
input=$(cat)
mode=$(jq -r '.permission_mode // ""' <<<"$input" 2>/dev/null || echo "")
[[ "$mode" == "plan" ]] && exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
mkdir -p "$STATE_DIR"
[[ -f "$STATE_DIR/skip_gate" ]] && exit 0

# Fingerprint of uncommitted code changes (docs excluded)
changes=$( { git diff HEAD -- . ':(exclude)*.md' 2>/dev/null
             git ls-files -o --exclude-standard -- . ':(exclude)*.md' | while IFS= read -r f; do
               echo "$f"; git hash-object -- "$f"; done; } )
[[ -z "$changes" ]] && exit 0
fp=$(printf '%s' "$changes" | git hash-object --stdin)
[[ -f "$STATE_DIR/last_green" && "$(cat "$STATE_DIR/last_green")" == "$fp" ]] && exit 0

if out=$(bash scripts/check.sh 2>&1); then
  echo "$fp" > "$STATE_DIR/last_green"
  exit 0
fi
{ echo "Quality gate failed. Fix the root cause (do not weaken tests or add ignores), then finish:"
  echo "$out" | tail -n 80; } >&2
exit 2
