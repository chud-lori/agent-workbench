#!/usr/bin/env bash
# Claude Code SessionStart hook for agent-workbench.
#
# Prints a compact block of recent brain notes to stdout (injected into the
# session context) and kicks an incremental code-index refresh in the
# background. A hook must never break session start: every step is
# best-effort and the script always exits 0.
#
# Install (settings.json):
#   {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
#     "command": "bash <WORKBENCH>/harness/hooks/session-start.sh"}]}]}}

# Resolve the workbench root from this script's own location (harness/hooks/ -> repo root).
WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0

# --- Recent brain notes -----------------------------------------------------
# Fetch up to 5 recent notes as JSON; on any failure print nothing for this
# section. JSON is parsed with python3 (jq may not be installed).
notes_json="$(python3 "$WORKBENCH/run_cli.py" recall --limit 5 2>/dev/null)" || notes_json=""

if [ -n "$notes_json" ]; then
    # The heredoc is python's stdin (the program), so the JSON travels via an
    # environment variable rather than a pipe.
    NOTES_JSON="$notes_json" python3 - <<'EOF' 2>/dev/null || true
import json
import os
import sys

try:
    data = json.loads(os.environ.get("NOTES_JSON", ""))
except Exception:
    sys.exit(0)

notes = data.get("notes") if isinstance(data, dict) else None
if not isinstance(notes, list) or not notes:
    sys.exit(0)

lines = []
for note in notes[:5]:
    if not isinstance(note, dict):
        continue
    content = " ".join(str(note.get("content", "")).split())
    if len(content) > 140:
        content = content[:140].rstrip() + "..."
    kind = note.get("kind") or "note"
    note_id = note.get("id", "?")
    project = note.get("project") or "-"
    lines.append(f"- [{kind}#{note_id}] ({project}) {content}")

if lines:
    print("Recent agent-workbench brain notes (brain_recall for more):")
    print("\n".join(lines))
EOF
fi

# --- Background index refresh -----------------------------------------------
# Fully detached and silent; never blocks or fails session start.
(nohup python3 "$WORKBENCH/run_cli.py" refresh-index >/dev/null 2>&1 &)

exit 0
