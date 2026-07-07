#!/usr/bin/env bash
# Claude Code UserPromptSubmit hook for agent-workbench.
#
# Approximates involuntary human recall: on every user prompt, FTS-match the
# prompt against brain notes and inject up to 5 one-line hits (ids + hooks)
# into the context. Bodies stay pull-based via brain_recall. The CLI side
# (recall-brief) is threshold-gated so trivial prompts inject nothing, and a
# hook must never break the session: every step is best-effort, always exit 0.
#
# Install (settings.json):
#   {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
#     "command": "bash <WORKBENCH>/harness/hooks/prompt-recall.sh"}]}]}}

WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0

# Extract .prompt from the hook payload; empty on any parse failure.
prompt="$(HOOK_PAYLOAD="$(cat)" python3 - <<'EOF' 2>/dev/null || true
import json
import os

try:
    payload = json.loads(os.environ.get("HOOK_PAYLOAD", ""))
except Exception:
    payload = {}
prompt = payload.get("prompt") if isinstance(payload, dict) else ""
if isinstance(prompt, str):
    print(prompt[:400].replace("\n", " "))
EOF
)"

[ -z "$prompt" ] && exit 0

# recall-brief prints nothing when the prompt is trivial or nothing matches;
# whatever it prints lands in the model's context for this turn.
python3 "$WORKBENCH/run_cli.py" recall-brief "$prompt" 2>/dev/null || true

exit 0
