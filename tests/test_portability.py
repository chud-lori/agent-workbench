from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]


class PythonFloorTests(unittest.TestCase):
    """The advertised floor is 3.10; tomllib is 3.11+. The server must still
    start on 3.10, and must not report 'not configured' when it simply could
    not read the file."""

    def _run_without_tomllib(self, snippet: str) -> str:
        code = "import sys; sys.modules['tomllib'] = None; sys.path.insert(0, %r)\n%s" % (str(REPO), snippet)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def test_mcp_server_starts_without_tomllib(self) -> None:
        out = self._run_without_tomllib(
            "from agent_workbench.mcp_server import TOOLS; print(len(TOOLS))"
        )
        self.assertTrue(int(out) > 0)

    def test_scanner_modules_import_without_tomllib(self) -> None:
        out = self._run_without_tomllib(
            "import agent_workbench.scanners, agent_workbench.work_sources; print('ok')"
        )
        self.assertEqual(out, "ok")

    def test_load_toml_raises_a_named_reason_when_unavailable(self) -> None:
        out = self._run_without_tomllib(
            "from agent_workbench.util import load_toml, TOML_AVAILABLE\n"
            "print(TOML_AVAILABLE)\n"
            "try:\n"
            "    load_toml('a = 1')\n"
            "except RuntimeError as exc:\n"
            "    print('3.11' in str(exc))"
        )
        self.assertEqual(out.splitlines(), ["False", "True"])

    def test_toml_parsing_works_when_available(self) -> None:
        from agent_workbench.util import TOML_AVAILABLE, load_toml

        if not TOML_AVAILABLE:
            self.skipTest("interpreter has no tomllib")
        self.assertEqual(load_toml("a = 1"), {"a": 1})


class EmptyMachineTests(unittest.TestCase):
    """A new user has no ~/repo and no work-mcp checkout. Nothing may crash."""

    def test_index_and_activity_survive_missing_roots(self) -> None:
        from agent_workbench.activity import recent_activity
        from agent_workbench.code_index import rebuild_index
        from agent_workbench.config import WorkbenchConfig

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = WorkbenchConfig(
                workbench_home=home,
                index_roots=(home / "absent",),
                projects_root=home / "also-absent",
            )
            self.assertEqual(rebuild_index(config=config)["repos"], 0)
            report = recent_activity(since="yesterday", config=config)
            self.assertEqual(report["total_commits"], 0)
            self.assertIn("note", report)

    def test_doctor_runs_on_an_empty_home(self) -> None:
        from agent_workbench.config import WorkbenchConfig
        from agent_workbench.scanners import doctor_report

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = WorkbenchConfig(
                workbench_home=home,
                index_roots=(home / "absent",),
                projects_root=home / "absent",
                claude_home=home / "no-claude",
                codex_home=home / "no-codex",
            )
            self.assertIsInstance(doctor_report(config=config), dict)


if __name__ == "__main__":
    unittest.main()
