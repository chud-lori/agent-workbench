from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_workbench import mcp_server
from agent_workbench.config import WorkbenchConfig
from agent_workbench.scanners import scan_secrets
from agent_workbench.work_sources import external_source_instructions


class SmokeTests(unittest.TestCase):
    def test_mcp_lists_core_tools(self) -> None:
        response = mcp_server._handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {},
        )
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("code_search", names)
        self.assertIn("refresh_code_index", names)
        self.assertIn("work_mcp_bridge", names)

    def test_external_source_plan_does_not_break_drive_query_quotes(self) -> None:
        plan = external_source_instructions("owner's package")
        drive_call = plan["recommended_calls"][2]
        self.assertEqual(drive_call["tool"], "mcp__google_workspace_local.drive_search")
        self.assertIn("owner s package", drive_call["arguments"]["query"])

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
