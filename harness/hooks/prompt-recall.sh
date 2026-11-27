#!/usr/bin/env bash
# Claude Code UserPromptSubmit hook for agent-workbench.
#
# Approximates involuntary human recall: on every user prompt, FTS-match the
# prompt against brain notes and inject up to 5 one-line hits (ids + hooks)
# into the context, then inject the rules whose scope matches this repo. Bodies
# stay pull-based via brain_recall. The CLI side (recall-brief) drops hits below
# a relevance floor and notes already shown in this session, so most prompts
# inject nothing. A hook must never break the session: every step is
# best-effort, always exit 0.
#
# Install (settings.json):
#   {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
#     "command": "bash <WORKBENCH>/harness/hooks/prompt-recall.sh"}]}]}}

WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0

# Extract .session_id (line 1) and .prompt (line 2) from the hook payload;
# empty on any parse failure.
parsed="$(HOOK_PAYLOAD="$(cat)" python3 - <<'EOF' 2>/dev/null || true
import json
import os
import re

try:
    payload = json.loads(os.environ.get("HOOK_PAYLOAD", ""))
except Exception:
    payload = {}
if not isinstance(payload, dict):
    payload = {}
session_id = payload.get("session_id")
prompt = payload.get("prompt")
print(re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:64] if isinstance(session_id, str) else "")
print(prompt[:400].replace("\n", " ") if isinstance(prompt, str) else "")
EOF
)"

session_id="${parsed%%$'\n'*}"
prompt="${parsed#*$'\n'}"
[ "$prompt" = "$parsed" ] && prompt=""
[ -z "$prompt" ] && exit 0

# recall-brief prints nothing when no note clears the floor or every hit was
# already shown this session; whatever it prints lands in this turn's context.
python3 "$WORKBENCH/run_cli.py" recall-brief "$prompt" --session "$session_id" 2>/dev/null || true

# Rules match on scope only and need no threshold: a one-word prompt is
# exactly where an unrepeated rule gets forgotten.
python3 "$WORKBENCH/run_cli.py" rules-brief 2>/dev/null || true

exit 0
