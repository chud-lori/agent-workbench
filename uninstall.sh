#!/usr/bin/env bash
# Remove everything setup.sh installed: hooks, standing-instruction blocks,
# MCP registrations. NEVER touches .state/ — your brain (brain.sqlite), the
# code index, and guard patterns survive so a re-install picks them right up.
set -euo pipefail
cd "$(dirname "$0")"
WORKBENCH="$(pwd)"

MARK_START="<!-- agent-workbench:start -->"
MARK_END="<!-- agent-workbench:end -->"

info() { printf '\033[36m[workbench]\033[0m %s\n' "$1"; }

# Strip the marker-fenced standing-instructions block from an instruction file.
remove_instructions() {
  local target="$1"
  [ -f "$target" ] || return 0
  python3 - "$target" "$MARK_START" "$MARK_END" <<'PY'
import sys
from pathlib import Path

target, start, end = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = target.read_text()
if start not in text or end not in text:
    sys.exit(0)
head, rest = text.split(start, 1)
_, tail = rest.split(end, 1)
new = head.rstrip() + ("\n\n" + tail.lstrip("\n") if tail.strip() else "\n")
if not new.strip():
    new = ""
target.write_text(new)
print(f"removed standing instructions from {target}")
PY
}

# --- Claude Code ---------------------------------------------------------------
python3 "$WORKBENCH/harness/install_hooks.py" --remove
remove_instructions "$HOME/.claude/CLAUDE.md"
for skill_dir in "$WORKBENCH"/harness/skills/*/; do
  [ -d "$skill_dir" ] || continue
  skill_link="$HOME/.claude/skills/$(basename "$skill_dir")"
  if [ -L "$skill_link" ] && [ "$(readlink "$skill_link")" = "${skill_dir%/}" ]; then
    rm "$skill_link"
    info "unlinked skill '$(basename "$skill_dir")' from ~/.claude/skills."
  fi
done

for agent_file in "$WORKBENCH"/harness/agents/*.md; do
  [ -f "$agent_file" ] || continue
  agent_link="$HOME/.claude/agents/$(basename "$agent_file")"
  if [ -L "$agent_link" ] && [ "$(readlink "$agent_link")" = "$agent_file" ]; then
    rm "$agent_link"
    info "unlinked agent '$(basename "$agent_file")' from ~/.claude/agents."
  fi
done
if command -v claude >/dev/null 2>&1 && claude mcp get agent-workbench >/dev/null 2>&1; then
  claude mcp remove --scope user agent-workbench
  info "unregistered MCP 'agent-workbench' from Claude Code."
fi

# --- Codex ----------------------------------------------------------------------
CODEX_CFG="$HOME/.codex/config.toml"
if [ -f "$CODEX_CFG" ] && grep -q '^\[mcp_servers\.agent_workbench\]' "$CODEX_CFG"; then
  python3 - "$CODEX_CFG" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text().splitlines(keepends=True)
out, skipping = [], False
for line in lines:
    stripped = line.strip()
    if stripped == "[mcp_servers.agent_workbench]":
        skipping = True
        continue
    if skipping and stripped.startswith("["):
        skipping = False
    if not skipping:
        out.append(line)
path.write_text("".join(out))
print(f"removed [mcp_servers.agent_workbench] from {path}")
PY
fi
remove_instructions "$HOME/.codex/AGENTS.md"

# --- Gemini CLI -------------------------------------------------------------------
GEMINI_CFG="$HOME/.gemini/settings.json"
if [ -f "$GEMINI_CFG" ]; then
  python3 - "$GEMINI_CFG" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    cfg = json.loads(path.read_text())
except (OSError, ValueError):
    sys.exit(0)
servers = cfg.get("mcpServers")
if isinstance(servers, dict) and "agent-workbench" in servers:
    del servers["agent-workbench"]
    if not servers:
        del cfg["mcpServers"]
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"removed MCP 'agent-workbench' from {path}")
PY
fi
remove_instructions "$HOME/.gemini/GEMINI.md"

info "done. .state/ (brain, index, guard patterns) was kept; delete it yourself if you really want it gone."
