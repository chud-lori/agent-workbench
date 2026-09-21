#!/usr/bin/env bash
# One-shot setup for agent-workbench: registers the MCP server, installs the
# standing instructions, wires the Claude Code hooks, links the Claude Code
# skills, and builds the code index.
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

  # Skills: symlink each harness/skills/<name> into ~/.claude/skills so repo
  # updates flow through without re-running setup.
  mkdir -p "$HOME/.claude/skills"
  for skill_dir in "$WORKBENCH"/harness/skills/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name="$(basename "$skill_dir")"
    skill_link="$HOME/.claude/skills/$skill_name"
    if [ -L "$skill_link" ] && [ "$(readlink "$skill_link")" = "${skill_dir%/}" ]; then
      info "skill '$skill_name' already linked."
    elif [ -e "$skill_link" ] || [ -L "$skill_link" ]; then
      info "skill '$skill_name': $skill_link already exists and is not our symlink - left as is."
    else
      ln -s "${skill_dir%/}" "$skill_link"
      info "linked skill '$skill_name' into ~/.claude/skills."
    fi
  done

  # Agents: symlink each harness/agents/<name>.md into ~/.claude/agents. These
  # are brain-primed subagent types - a subagent gets no SessionStart/prompt
  # hook, so recall has to live in its own system prompt or it never happens.
  mkdir -p "$HOME/.claude/agents"
  for agent_file in "$WORKBENCH"/harness/agents/*.md; do
    [ -f "$agent_file" ] || continue
    agent_name="$(basename "$agent_file")"
    agent_link="$HOME/.claude/agents/$agent_name"
    if [ -L "$agent_link" ] && [ "$(readlink "$agent_link")" = "$agent_file" ]; then
      info "agent '$agent_name' already linked."
    elif [ -e "$agent_link" ] || [ -L "$agent_link" ]; then
      info "agent '$agent_name': $agent_link already exists and is not our symlink - left as is."
    else
      ln -s "$agent_file" "$agent_link"
      info "linked agent '$agent_name' into ~/.claude/agents."
    fi
  done

  # Transcript retention: Claude Code prunes ~/.claude/projects after
  # cleanupPeriodDays (default 30), so session history silently evaporates.
  python3 - "$HOME/.claude/settings.json" <<'PYEOF'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    cfg = json.loads(path.read_text())
except (OSError, ValueError):
    cfg = {}
current = cfg.get("cleanupPeriodDays")
if current is None:
    cfg["cleanupPeriodDays"] = 3650
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("set cleanupPeriodDays=3650 (was unset; default 30 deletes transcripts)")
else:
    print(f"cleanupPeriodDays already set to {current} - left as is.")
PYEOF
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

# --- CLI launcher (stable path for subagents and other harnesses) --------------
# Agent types run with a restricted toolset and cannot reach the MCP tools, so
# they recall through Bash instead. A fixed path outside the clone means an agent
# prompt never has to know where the repo lives.
RULES_SRC="$WORKBENCH/harness/skills/pr-review/rules.md"
RULES_DST="${XDG_CONFIG_HOME:-$HOME/.config}/agent-workbench/review-rules.md"
mkdir -p "$(dirname "$RULES_DST")"
if cmp -s "$RULES_SRC" "$RULES_DST"; then
  info "review-rules.md already current at $RULES_DST."
else
  cp "$RULES_SRC" "$RULES_DST"
  info "installed review-rules.md at $RULES_DST (readable without loading the skill)."
fi

DISCIPLINE_SRC="$WORKBENCH/harness/coding-discipline.md"
DISCIPLINE_DST="${XDG_CONFIG_HOME:-$HOME/.config}/agent-workbench/coding-discipline.md"
mkdir -p "$(dirname "$DISCIPLINE_DST")"
if cmp -s "$DISCIPLINE_SRC" "$DISCIPLINE_DST"; then
  info "coding-discipline.md already current at $DISCIPLINE_DST."
else
  cp "$DISCIPLINE_SRC" "$DISCIPLINE_DST"
  info "installed coding-discipline.md at $DISCIPLINE_DST (the standing instructions point here)."
fi

AW_BIN="${XDG_CONFIG_HOME:-$HOME/.config}/agent-workbench/bin/aw"
mkdir -p "$(dirname "$AW_BIN")"
cat > "$AW_BIN.tmp" <<AWEOF
#!/bin/sh
exec python3 "$WORKBENCH/run_cli.py" "\$@"
AWEOF
chmod +x "$AW_BIN.tmp"
if cmp -s "$AW_BIN.tmp" "$AW_BIN"; then
  rm "$AW_BIN.tmp"; info "CLI launcher already current at $AW_BIN."
else
  mv "$AW_BIN.tmp" "$AW_BIN"; info "installed CLI launcher at $AW_BIN."
fi

# --- Commit attribution guard (git hooks) ---------------------------------------
# Keeps AI attribution out of commit messages and refuses commits made under an
# assistant/bot identity. Harness-independent: plain git hooks, so it applies to
# every agent (and every human) that commits in the repo, not just one vendor.
step "Commit attribution guard"
# Hooks are COPIED to a stable location outside any working tree, never
# symlinked into it. A hook that lives in the repo it guards stops existing the
# moment you check out a branch that predates it - and a dangling hook fails
# silently, which is the worst way for a guardrail to fail.
HOOKS_SRC="$WORKBENCH/harness/git-hooks"
HOOKS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/agent-workbench/git-hooks"
info "hooks: commit-msg strips AI trailers, pre-commit blocks bot identities"
mkdir -p "$HOOKS_DIR"
for hook in commit-msg pre-commit; do
  if [ -f "$HOOKS_SRC/$hook" ]; then
    if cmp -s "$HOOKS_SRC/$hook" "$HOOKS_DIR/$hook"; then
      info "$hook already current in $HOOKS_DIR."
    else
      cp "$HOOKS_SRC/$hook" "$HOOKS_DIR/$hook"
      chmod +x "$HOOKS_DIR/$hook"
      info "installed $hook into $HOOKS_DIR."
    fi
  fi
done
info "re-run setup.sh after editing a hook - these are copies, not symlinks."
# Machine-wide is the stronger option: core.hooksPath makes the guard apply to
# EVERY repo. Our hooks chain to a repo-local hook of the same name afterwards,
# so projects with their own hooks keep working.
CURRENT_HOOKS_PATH="$(git config --global core.hooksPath || true)"
if [ -z "$CURRENT_HOOKS_PATH" ]; then
  if ask "Apply the guard to EVERY repo on this machine (git core.hooksPath)?" "y"; then
    git config --global core.hooksPath "$HOOKS_DIR"
    info "set global core.hooksPath=$HOOKS_DIR (repo-local hooks still run, chained)."
  else
    info "not enabled. Per-repo alternative: cp '$HOOKS_DIR'/* <repo>/.git/hooks/"
  fi
elif [ "$CURRENT_HOOKS_PATH" = "$HOOKS_DIR" ]; then
  info "global core.hooksPath already points at $HOOKS_DIR."
elif [ "$CURRENT_HOOKS_PATH" = "$HOOKS_SRC" ]; then
  git config --global core.hooksPath "$HOOKS_DIR"
  info "moved core.hooksPath off the working tree to $HOOKS_DIR (branch-independent)."
else
  info "global core.hooksPath is set to $CURRENT_HOOKS_PATH - left as is."
fi

# --- Companion plugins (optional, third-party, installed from upstream) ---------
# Not vendored: these are maintained elsewhere and install with their own
# installers. setup.sh just offers them so a new machine is one command.
if [ "$DO_CLAUDE" = "y" ]; then
  step "Companion plugins (optional)"
  if command -v node >/dev/null 2>&1 && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ]; then
    if ask "Install caveman (concise agent output, github.com/JuliusBrussee/caveman)?" "n"; then
      # Run from $HOME: with a repo as CWD the installer also writes per-repo
      # .agents/ rule files into it. Its Gemini step prompts for trust, so a
      # closed stdin hangs it — keep this step interactive-only (ask already
      # defaults to no when non-interactive).
      (cd "$HOME" && curl -fsSL https://raw.githubusercontent.com/JuliusBrussee/caveman/main/install.sh | bash) \
        && info "caveman installed." || info "caveman install failed - re-run its installer manually."
    fi
  else
    info "node >=18 not found - skipping companion plugin offers (caveman needs it)."
  fi
  info "ponytail (minimalist code generation) installs from inside Claude Code - two separate prompts:"
  info "  /plugin marketplace add DietrichGebert/ponytail"
  info "  /plugin install ponytail@ponytail"
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
