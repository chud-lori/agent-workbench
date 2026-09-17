from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS = sorted((REPO / "harness" / "agents").glob("*.md"))
LAUNCHER = "agent-workbench/bin/aw"


def _tools(text: str) -> list[str]:
    match = re.search(r"^tools:\s*\[(.*)\]\s*$", text, re.M)
    return [t.strip() for t in match.group(1).split(",")] if match else []


class AgentTypeTests(unittest.TestCase):
    """The agent types exist to recall before acting, so recall must be reachable.

    They shipped once telling the agent to call `brain_recall` while the
    frontmatter allowlist held no MCP tool: the agent guessed a name and failed
    with "No such tool available". Unknown allowlist names are dropped silently,
    so the only recall path that holds under a restricted toolset is Bash.
    """

    def test_agent_types_exist(self) -> None:
        self.assertEqual({p.stem for p in AGENTS}, {"scout", "implementer", "adversary"})

    def test_every_agent_can_run_the_cli(self) -> None:
        for path in AGENTS:
            text = path.read_text()
            self.assertIn("Bash", _tools(text), f"{path.name} cannot run Bash, so it cannot recall")
            self.assertIn(LAUNCHER, text, f"{path.name} does not tell the agent how to reach the brain")

    def test_no_agent_is_told_to_call_an_mcp_tool_it_does_not_have(self) -> None:
        for path in AGENTS:
            text = path.read_text()
            tools = _tools(text)
            for bare in ("brain_recall", "brief_task", "code_search", "repo_state"):
                if any(bare in t for t in tools):
                    continue
                self.assertNotRegex(
                    text, rf"`{bare}`", f"{path.name} instructs `{bare}` but its toolset has no such tool"
                )

    def test_setup_renders_a_working_launcher(self) -> None:
        # The heredoc escaping of "$@" is the part that breaks silently.
        block = re.search(r"^AW_BIN=.*?^fi$", (REPO / "setup.sh").read_text(), re.S | re.M).group(0)
        with tempfile.TemporaryDirectory() as tmp:
            script = f'info() {{ :; }}\nWORKBENCH="{REPO}"\nXDG_CONFIG_HOME="{tmp}"\n{block}\n'
            subprocess.run(["bash", "-c", script], check=True)
            launcher = Path(tmp) / LAUNCHER
            self.assertTrue(os.access(launcher, os.X_OK))
            self.assertIn('"$@"', launcher.read_text())
            out = subprocess.run([str(launcher), "--help"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("recall", out.stdout)


if __name__ == "__main__":
    unittest.main()
