#!/usr/bin/env bash
# Claude Code PreToolUse hook for agent-workbench: generic command guard.
#
# Forces an explicit human approval for any Bash command matching one of the
# user's guard patterns — enforcement OUTSIDE the model, so a convincing but
# wrong chain of reasoning cannot talk itself past it. The mechanism is
# generic; the patterns are yours (org-specific, per-machine, untracked).
#
# Patterns file: one Python regex per line, `#` comments allowed. Location:
#   $AGENT_WORKBENCH_GUARD_PATTERNS, else <workbench>/.state/guard-patterns.txt
# Missing/empty file = guard inactive (hook is a silent no-op).
# Start from harness/guard-patterns.example.txt.
#
# Install (settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "bash <WORKBENCH>/harness/hooks/pretooluse-guard.sh"}]}]}}
#
# A hook must never break the session: best-effort everywhere, always exit 0.

WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0
PATTERNS_FILE="${AGENT_WORKBENCH_GUARD_PATTERNS:-$WORKBENCH/.state/guard-patterns.txt}"

[ -s "$PATTERNS_FILE" ] || exit 0

HOOK_PAYLOAD="$(cat)" GUARD_PATTERNS_FILE="$PATTERNS_FILE" python3 - <<'EOF' 2>/dev/null || true
import json
import os
import re
import sys

try:
    payload = json.loads(os.environ.get("HOOK_PAYLOAD", ""))
except Exception:
    sys.exit(0)

if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
    sys.exit(0)
command = (payload.get("tool_input") or {}).get("command") or ""
if not command:
    sys.exit(0)

matched = []
try:
    with open(os.environ["GUARD_PATTERNS_FILE"], encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                if re.search(line, command):
                    matched.append(line)
            except re.error:
                continue
except OSError:
    sys.exit(0)

if matched:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "agent-workbench guard: command matches protected pattern(s) "
                + ", ".join(f"`{p}`" for p in matched[:3])
                + " — confirm this is intended (guard config: .state/guard-patterns.txt)."
            ),
        }
    }))
EOF

exit 0
