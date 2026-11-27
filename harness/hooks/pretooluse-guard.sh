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
# Missing/empty file = pattern guard inactive.
# Start from harness/guard-patterns.example.txt.
#
# Separately, denies a `git commit` whose added lines fail harness/gates/check_diff.py.
# Agent-scoped, not a git hook: those checks are not conventions for every repo.
#
# Install (settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "bash <WORKBENCH>/harness/hooks/pretooluse-guard.sh"}]}]}}
#
# A hook must never break the session: best-effort everywhere, always exit 0.

WORKBENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 0
PATTERNS_FILE="${AGENT_WORKBENCH_GUARD_PATTERNS:-$WORKBENCH/.state/guard-patterns.txt}"

. "$WORKBENCH/harness/hooks/lib/hook-input.sh" || exit 0
read_hook_input
case "$HOOK_PAYLOAD" in *commit*) ;; *) [ -s "$PATTERNS_FILE" ] || exit 0 ;; esac

GUARD_PATTERNS_FILE="$PATTERNS_FILE" GATES="$WORKBENCH/harness/gates/check_diff.py" python3 - <<'EOF' 2>/dev/null || true
import json
import os
import re
import shlex
import subprocess
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


def gate_findings(command, cwd):
    """Findings for each `git commit` in the command, against what it will commit."""
    findings = []
    for segment in re.split(r"&&|\|\||;|\n", command):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        if words[:1] == ["cd"] and len(words) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(words[1]))
            continue
        if "git" not in words or "commit" not in words:
            continue
        rest = words[words.index("git") + 1:]
        repo = cwd
        while rest[:1] in (["-C"], ["-c"]) and len(rest) > 1:
            if rest[0] == "-C":
                repo = os.path.join(repo, rest[1])
            rest = rest[2:]
        if rest[:1] != ["commit"]:
            continue
        opts = rest[1:]
        commit_all = any(o == "--all" or re.fullmatch(r"-[a-zA-Z]*a[a-zA-Z]*", o) for o in opts)
        target = ["HEAD"] if commit_all else []
        try:
            out = subprocess.run(
                [sys.executable, os.environ["GATES"], "-C", repo, *target],
                capture_output=True, text=True, timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode == 1:
            findings.extend(out.stdout.splitlines())
    return findings


findings = gate_findings(command, payload.get("cwd") or os.getcwd())
if findings:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "agent-workbench gate: the commit adds Gate-tier violations:\n"
                + "\n".join(findings[:10])
                + "\nFix them, or mark a known false positive with `gate-allow: CR-NN` "
                "in a comment on that line."
            ),
        }
    }))
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
