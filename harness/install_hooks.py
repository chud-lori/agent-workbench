#!/usr/bin/env python3
"""Idempotently wire the agent-workbench hooks into a Claude Code settings.json.

Safe to re-run: existing entries are recognized (by their harness/hooks/<name>
script, even if the clone moved) and upgraded in place — command path, matcher,
timeout — instead of duplicated. --remove strips exactly our hooks and nothing
else. Stdlib only.

Usage:
    python3 install_hooks.py                 # install/upgrade into ~/.claude/settings.json
    python3 install_hooks.py --remove        # remove our hooks
    python3 install_hooks.py --settings PATH # target a different settings file
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKBENCH = Path(__file__).resolve().parents[1]

# (event, matcher, script name, timeout, status message)
# SessionStart matches resume|compact too so the brain re-primes after a
# context compaction instead of fading mid-session.
HOOK_SPECS = [
    ("SessionStart", "startup|resume|compact", "session-start.sh", 20, "Loading brain notes"),
    ("UserPromptSubmit", None, "prompt-recall.sh", 10, "Recalling brain notes"),
    ("Stop", None, "stop-memory-checkpoint.sh", 10, "Memory checkpoint"),
    ("PreToolUse", "Bash", "pretooluse-guard.sh", 10, "Guard check"),
]


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _is_ours(hook: dict, script: str) -> bool:
    """A hook is ours if its command runs harness/hooks/<script> from any clone path."""
    command = hook.get("command", "")
    return f"harness/hooks/{script}" in command


def install(settings_path: Path) -> list[str]:
    cfg = _load(settings_path)
    hooks = cfg.setdefault("hooks", {})
    changes: list[str] = []

    for event, matcher, script, timeout, status in HOOK_SPECS:
        command = f"bash {WORKBENCH}/harness/hooks/{script}"
        desired_entry_fields = {"matcher": matcher} if matcher else {}
        desired_hook = {
            "type": "command",
            "command": command,
            "timeout": timeout,
            "statusMessage": status,
        }
        entries = hooks.setdefault(event, [])
        found = False
        for entry in entries:
            for hook in entry.get("hooks", []):
                if not _is_ours(hook, script):
                    continue
                found = True
                if hook != desired_hook:
                    hook.clear()
                    hook.update(desired_hook)
                    changes.append(f"{event}: upgraded {script} hook")
                if matcher and entry.get("matcher") != matcher:
                    entry["matcher"] = matcher
                    changes.append(f"{event}: set matcher '{matcher}'")
        if not found:
            entries.append({**desired_entry_fields, "hooks": [desired_hook]})
            changes.append(f"{event}: installed {script}")

    if changes:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return changes


def remove(settings_path: Path) -> list[str]:
    cfg = _load(settings_path)
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return []
    changes: list[str] = []
    scripts = [spec[2] for spec in HOOK_SPECS]

    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        for entry in entries:
            kept = [
                h for h in entry.get("hooks", [])
                if not any(_is_ours(h, s) for s in scripts)
            ]
            if len(kept) != len(entry.get("hooks", [])):
                changes.append(f"{event}: removed workbench hook")
                entry["hooks"] = kept
        hooks[event] = [e for e in entries if e.get("hooks")]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        cfg.pop("hooks", None)

    if changes:
        settings_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"))
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()

    settings_path = Path(args.settings).expanduser()
    changes = remove(settings_path) if args.remove else install(settings_path)
    for change in changes:
        print(change)
    if not changes:
        print("hooks already up to date" if not args.remove else "no workbench hooks found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
