from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("install_hooks", REPO / "harness" / "install_hooks.py")
install_hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install_hooks)


class InstallHooksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Path(self.tmp.name) / "settings.json"

    def read(self) -> dict:
        return json.loads(self.settings.read_text())

    def test_fresh_install_wires_all_four_hooks(self) -> None:
        changes = install_hooks.install(self.settings)
        self.assertEqual(len(changes), 4)
        cfg = self.read()
        self.assertEqual(
            set(cfg["hooks"]), {"SessionStart", "UserPromptSubmit", "Stop", "PreToolUse"}
        )
        session = cfg["hooks"]["SessionStart"][0]
        self.assertEqual(session["matcher"], "startup|resume|compact")
        self.assertIn("harness/hooks/session-start.sh", session["hooks"][0]["command"])
        self.assertEqual(cfg["hooks"]["PreToolUse"][0]["matcher"], "Bash")

    def test_reinstall_is_idempotent(self) -> None:
        install_hooks.install(self.settings)
        before = self.read()
        changes = install_hooks.install(self.settings)
        self.assertEqual(changes, [])
        self.assertEqual(self.read(), before)

    def test_upgrades_matcherless_session_start_entry(self) -> None:
        # An existing install (pre-compaction-matcher) gains the matcher in place.
        self.settings.write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [{
                "type": "command",
                "command": "bash /old/clone/harness/hooks/session-start.sh",
                "timeout": 20,
                "statusMessage": "Loading brain notes",
            }]}]},
            "other": {"kept": True},
        }))
        install_hooks.install(self.settings)
        cfg = self.read()
        session_entries = [
            e for e in cfg["hooks"]["SessionStart"]
            if any("session-start.sh" in h["command"] for h in e["hooks"])
        ]
        self.assertEqual(len(session_entries), 1)  # upgraded, not duplicated
        self.assertEqual(session_entries[0]["matcher"], "startup|resume|compact")
        # Command path re-pointed at this clone; unrelated settings untouched.
        self.assertIn(str(REPO), session_entries[0]["hooks"][0]["command"])
        self.assertEqual(cfg["other"], {"kept": True})

    def test_remove_strips_only_our_hooks(self) -> None:
        install_hooks.install(self.settings)
        cfg = self.read()
        cfg["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "echo third-party"}]})
        self.settings.write_text(json.dumps(cfg))

        install_hooks.remove(self.settings)
        cfg = self.read()
        self.assertEqual(list(cfg["hooks"]), ["Stop"])
        self.assertEqual(cfg["hooks"]["Stop"][0]["hooks"][0]["command"], "echo third-party")

    def test_remove_on_empty_settings_is_a_noop(self) -> None:
        self.assertEqual(install_hooks.remove(self.settings), [])
        self.assertFalse(self.settings.exists())


if __name__ == "__main__":
    unittest.main()
