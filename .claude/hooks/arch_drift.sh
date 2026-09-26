#!/usr/bin/env bash
# Stop: if this change set adds dependencies or new modules but ARCHITECTURE.md
# and docs/adr/ are untouched, ask Claude to draft a record (once per change set).
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:?}"
source .claude/hooks/config.sh
input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
[[ "$(jq -r '.permission_mode // ""' <<<"$input")" == "plan" ]] && exit 0
git rev-parse --verify -q HEAD >/dev/null 2>&1 || exit 0

changed=$( { git diff HEAD --name-only; git ls-files -o --exclude-standard; } 2>/dev/null | sort -u | sed '/^$/d')
[[ -z "$changed" ]] && exit 0
grep -Eq "$DOCS_REGEX" <<<"$changed" && exit 0

deps=$(grep -E "$DEP_FILES_REGEX" <<<"$changed" | paste -sd, -)
newdirs=""
while IFS= read -r f; do
  [[ "$f" =~ $SRC_PATH_REGEX ]] || continue
  d=$(dirname "$f")
  git cat-file -e "HEAD:$d" 2>/dev/null || newdirs+="$d"$'\n'
done <<<"$changed"
newdirs=$(sort -u <<<"$newdirs" | sed '/^$/d' | paste -sd, -)
[[ -z "$deps$newdirs" ]] && exit 0

mkdir -p "$STATE_DIR"
fp=$(printf '%s|%s' "$deps" "$newdirs" | git hash-object --stdin)
[[ -f "$STATE_DIR/arch_nudged" && "$(cat "$STATE_DIR/arch_nudged")" == "$fp" ]] && exit 0
echo "$fp" > "$STATE_DIR/arch_nudged"

reason="Structural change with no architecture record."
[[ -n "$deps" ]]    && reason+=" Dependency files changed: $deps."
[[ -n "$newdirs" ]] && reason+=" New modules: $newdirs."
reason+=" Either (a) record it with /decision in DECISIONS.md and update the ARCHITECTURE.md code map, or (b) say in one line why no record is needed. Then finish."
jq -n --arg r "$reason" '{decision:"block", reason:$r}'
