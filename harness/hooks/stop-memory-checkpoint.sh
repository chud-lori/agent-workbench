#!/usr/bin/env bash
# Claude Code Stop hook for agent-workbench.
#
# Enforces the "second brain" contract: when the model finishes a turn, block
# the stop ONCE and instruct it to store any durable knowledge from the turn
# (decisions, gotchas, run/deploy results, new scripts or conventions) with
# brain_remember before ending. If nothing durable was learned, the model is
# told to end immediately, so the extra pass stays cheap.
#
# The hook input's stop_hook_active flag is true when the model is already
# continuing from a previous block by this hook — in that case print nothing
# (allow the stop) so it can never loop. A hook must never break the session:
# every step is best-effort and the script always exits 0.
#
# Install (settings.json):
#   {"hooks": {"Stop": [{"hooks": [{"type": "command",
#     "command": "bash <WORKBENCH>/harness/hooks/stop-memory-checkpoint.sh"}]}]}}

# The heredoc is python's stdin (the program), so the hook payload travels
# via an environment variable rather than a pipe.
HOOK_PAYLOAD="$(cat)" python3 - <<'EOF' 2>/dev/null || true
import json
import os
import sys

try:
    payload = json.loads(os.environ.get("HOOK_PAYLOAD", ""))
except Exception:
    payload = {}

if isinstance(payload, dict) and payload.get("stop_hook_active"):
    sys.exit(0)

print(json.dumps({
    "decision": "block",
    "reason": (
        "Routine memory checkpoint - NOT an error, the harness renders any "
        "blocking Stop hook this way. Store any durable knowledge from this "
        "turn (decisions, gotchas, run results, new scripts/conventions) with "
        "brain_remember on the agent-workbench MCP, with a source reference. "
        "If nothing durable was learned, end immediately without commentary."
    ),
}))
EOF

exit 0
