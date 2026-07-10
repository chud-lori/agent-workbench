#!/usr/bin/env bash
# One-shot setup for agent-workbench: registers the MCP server, installs the
# standing instructions, wires the Claude Code hooks, and builds the code index.
# Idempotent — re-running upgrades in place and never duplicates anything.
# Requires python3 >= 3.10; no other dependencies.
set -euo pipefail
cd "$(dirname "$0")"
WORKBENCH="$(pwd)"

MARK_START="<!-- agent-workbench:start -->"
MARK_END="<!-- agent-workbench:end -->"

info() { printf '\033[36m[workbench]\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

# ask "<prompt>" "<default y|n>" -> returns 0 for yes. Non-interactive runs
# take the default.
ask() {
  local prompt="$1" default="$2" reply
  if [ ! -t 0 ]; then
    [ "$default" = "y" ]
    return
  fi
  if [ "$default" = "y" ]; then prompt="$prompt [Y/n]: "; else prompt="$prompt [y/N]: "; fi
  read -r -p "$prompt" reply
  reply="${reply:-$default}"
  [ "$reply" = "y" ] || [ "$reply" = "Y" ]
}

# Insert (or refresh) the standing-instructions block in an instruction file,
# fenced by markers so uninstall.sh can strip it and re-runs stay current.
install_instructions() {
  local target="$1"
  mkdir -p "$(dirname "$target")"
  python3 - "$target" "$WORKBENCH/harness/standing-instructions.md" "$MARK_START" "$MARK_END" <<'PY'
import sys
from pathlib import Path

target, source, start, end = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
block = f"{start}\n{source.read_text().rstrip()}\n{end}\n"
text = target.read_text() if target.exists() else ""

if start in text and end in text:
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    new = head + block + tail.lstrip("\n")
    action = "refreshed"
elif "# Agent Workbench" in text:
    # A hand-pasted, unmarked copy exists; do not stack a duplicate.
    print(f"unmarked Agent Workbench section already in {target} - left as is")
    sys.exit(0)
else:
    new = (text.rstrip() + "\n\n" if text.strip() else "") + block
    action = "installed"

if new != text:
    target.write_text(new)
    print(f"{action} standing instructions in {target}")
else:
    print(f"standing instructions already current in {target}")
PY
}

# --- Pick harnesses (auto-detected defaults) ---------------------------------
step "Harnesses"
DEF_CLAUDE=n; DEF_CODEX=n; DEF_GEMINI=n
if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then DEF_CLAUDE=y; fi
if [ -d "$HOME/.codex" ]; then DEF_CODEX=y; fi
if [ -d "$HOME/.gemini" ]; then DEF_GEMINI=y; fi

DO_CLAUDE=n; DO_CODEX=n; DO_GEMINI=n
if ask "Set up Claude Code?" "$DEF_CLAUDE"; then DO_CLAUDE=y; fi
if ask "Set up Codex?" "$DEF_CODEX"; then DO_CODEX=y; fi
if ask "Set up Gemini CLI?" "$DEF_GEMINI"; then DO_GEMINI=y; fi
if [ "$DO_CLAUDE$DO_CODEX$DO_GEMINI" = "nnn" ]; then info "nothing selected - exiting."; exit 0; fi

# --- Claude Code --------------------------------------------------------------
if [ "$DO_CLAUDE" = "y" ]; then
  step "Claude Code"
  if command -v claude >/dev/null 2>&1; then
    if claude mcp get agent-workbench >/dev/null 2>&1; then
      info "MCP 'agent-workbench' already registered."
    else
      claude mcp add --scope user agent-workbench python3 "$WORKBENCH/run_mcp.py"
      info "registered MCP 'agent-workbench' (user scope)."
    fi
  else
    info "claude CLI not found - register the MCP later with:"
    info "  claude mcp add --scope user agent-workbench python3 '$WORKBENCH/run_mcp.py'"
  fi
  install_instructions "$HOME/.claude/CLAUDE.md"
  python3 "$WORKBENCH/harness/install_hooks.py"
fi

# --- Codex ---------------------------------------------------------------------
if [ "$DO_CODEX" = "y" ]; then
  step "Codex"
  CODEX_CFG="$HOME/.codex/config.toml"
  mkdir -p "$HOME/.codex"
  if [ -f "$CODEX_CFG" ] && grep -q '^\[mcp_servers\.agent_workbench\]' "$CODEX_CFG"; then
    info "MCP 'agent_workbench' already in $CODEX_CFG."
  else
    {
      echo ""
      echo "[mcp_servers.agent_workbench]"
      echo "command = \"python3\""
      echo "args = [\"$WORKBENCH/run_mcp.py\"]"
      echo "startup_timeout_sec = 20"
      echo "tool_timeout_sec = 90"
      echo "enabled = true"
    } >> "$CODEX_CFG"
    info "registered MCP 'agent_workbench' in $CODEX_CFG."
  fi
  install_instructions "$HOME/.codex/AGENTS.md"
fi

# --- Gemini CLI ------------------------------------------------------------------
if [ "$DO_GEMINI" = "y" ]; then
  step "Gemini CLI"
  python3 - "$HOME/.gemini/settings.json" "$WORKBENCH/run_mcp.py" <<'PY'
import json, sys
from pathlib import Path

path, server = Path(sys.argv[1]), sys.argv[2]
path.parent.mkdir(parents=True, exist_ok=True)
try:
    cfg = json.loads(path.read_text())
except (OSError, ValueError):
    cfg = {}
servers = cfg.setdefault("mcpServers", {})
entry = {"command": "python3", "args": [server]}
if servers.get("agent-workbench") == entry:
    print(f"MCP 'agent-workbench' already in {path}.")
else:
    servers["agent-workbench"] = entry
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"registered MCP 'agent-workbench' in {path}.")
PY
  install_instructions "$HOME/.gemini/GEMINI.md"
fi

# --- Guard patterns (optional, per-machine, untracked) --------------------------
if [ "$DO_CLAUDE" = "y" ] && [ ! -f "$WORKBENCH/.state/guard-patterns.txt" ]; then
  if ask "Seed .state/guard-patterns.txt from the example (PreToolUse guard stays inert until you add patterns)?" "n"; then
    mkdir -p "$WORKBENCH/.state"
    cp "$WORKBENCH/harness/guard-patterns.example.txt" "$WORKBENCH/.state/guard-patterns.txt"
    info "created .state/guard-patterns.txt - add your regexes to activate the guard."
  fi
fi

# --- Code index ------------------------------------------------------------------
step "Code index"
info "index roots: \${AGENT_WORKBENCH_REPO_ROOT:-~/repo} (override via env before re-running)"
if ask "Build/refresh the code index now?" "y"; then
  python3 "$WORKBENCH/run_cli.py" index
fi

step "Done"
info "restart your agent so the MCP server and hooks load."
info "re-run ./setup.sh anytime; ./uninstall.sh removes everything but keeps .state/ (your brain)."
