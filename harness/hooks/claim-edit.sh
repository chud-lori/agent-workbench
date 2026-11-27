#!/usr/bin/env bash
# PostToolUse(Edit|Write|MultiEdit|NotebookEdit): claims the edited file for this session in .state/ledger.sqlite.
# brief_task in another session reads the claim and warns; nothing blocks. Prints nothing and always exits 0.

WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0
. "$WORKBENCH/harness/hooks/lib/hook-input.sh" || exit 0
read_hook_input
[ -n "$HOOK_SESSION_ID" ] || exit 0
printf '%s' "$HOOK_PAYLOAD" | python3 "$WORKBENCH/run_cli.py" claim-edit "$HOOK_SESSION_ID" >/dev/null 2>&1 || true
exit 0
