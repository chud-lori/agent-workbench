from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_workbench import brain, mcp_server
from agent_workbench.config import WorkbenchConfig
from agent_workbench.scanners import scan_secrets


class SmokeTests(unittest.TestCase):
    def test_mcp_lists_core_tools(self) -> None:
        response = mcp_server._handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {},
        )
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("code_search", names)
        self.assertIn("refresh_code_index", names)
        self.assertIn("brief_task", names)
        for tool in ("brain_remember", "brain_recall", "brain_forget", "brain_resolve", "brain_export"):
            self.assertIn(tool, names)

    def test_brain_roundtrip_with_stemming_and_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            stored = brain.remember("paused the listing package", kind="todo", project="demo", config=config)
            self.assertTrue(stored["stored"])
            hits = brain.recall("pause listings", config=config)
            self.assertEqual([note["id"] for note in hits["notes"]], [stored["id"]])
            brain.resolve(stored["id"], config=config)
            self.assertEqual(brain.recall(config=config)["notes"], [])
            resolved = brain.recall(include_resolved=True, config=config)["notes"]
            self.assertEqual([note["id"] for note in resolved], [stored["id"]])
            exported = brain.export(config=config)
            self.assertIn("paused the listing package", exported["markdown"])

    def test_config_reads_environment_overrides(self) -> None:
        old_value = os.environ.get("AGENT_WORKBENCH_WORK_MCP_ROOT")
        os.environ["AGENT_WORKBENCH_WORK_MCP_ROOT"] = "/tmp/custom-work-mcp"
        try:
            import agent_workbench.config as config

            reloaded = importlib.reload(config)
            self.assertEqual(reloaded.default_config().work_mcp_root, Path("/tmp/custom-work-mcp"))
        finally:
            if old_value is None:
                os.environ.pop("AGENT_WORKBENCH_WORK_MCP_ROOT", None)
            else:
                os.environ["AGENT_WORKBENCH_WORK_MCP_ROOT"] = old_value
            import agent_workbench.config as config

            importlib.reload(config)

    def test_secret_scan_omits_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            env_file.write_text('API_KEY="super-secret-token-value"\n')
            config = WorkbenchConfig(
                repo_root=root,
                projects_root=root,
                codex_home=root / "codex",
                claude_home=root / "claude",
                work_mcp_root=root / "work-mcp",
                workbench_home=root / "state",
            )
            findings = scan_secrets(config)
            self.assertTrue(findings)
            self.assertNotIn("super-secret-token-value", findings[0].detail)


if __name__ == "__main__":
    unittest.main()
