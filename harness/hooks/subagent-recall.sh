#!/usr/bin/env bash
# PreToolUse(Agent) stashes the spawn prompt; SubagentStart, whose payload has no prompt, injects its brain hits and rules.
# Prints nothing on PreToolUse so the spawn is never changed or blocked, and always exits 0.

WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0
python3 "$WORKBENCH/run_cli.py" subagent-brief 2>/dev/null || true
exit 0
