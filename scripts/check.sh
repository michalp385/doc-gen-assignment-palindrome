#!/usr/bin/env bash
# Single source of truth for the quality gate. Run by the Stop hook AND CI,
# so "green locally" means "green in CI". Configure commands in .claude/hooks/config.sh.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
source .claude/hooks/config.sh

fail=0
step() {
  local name=$1; shift
  [[ -z "$*" ]] && return
  echo "== $name: $*"
  if ! $RUN "$@"; then echo "!! $name FAILED"; fail=1; fi
}
step format    $FORMAT_CHECK_CMD
step lint      $LINT_CMD
step types     $TYPECHECK_CMD
step contracts $EXTRA_CHECK_CMD
step tests     $TEST_CMD
exit $fail
