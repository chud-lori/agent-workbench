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
        self.assertIn("repo_state", names)
        for tool in ("brain_remember", "brain_recall", "brain_forget", "brain_resolve", "brain_export", "brain_amend"):
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

    def test_supersede_hides_old_note_from_default_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            old = brain.remember("deploy uses the blue cluster", kind="fact", project="demo", config=config)
            new = brain.remember(
                "deploy uses the green cluster since the June migration",
                kind="fact",
                project="demo",
                config=config,
                supersedes=[old["id"]],
            )
            self.assertEqual(new["superseded"], [old["id"]])
            default_ids = [note["id"] for note in brain.recall("deploy cluster", config=config)["notes"]]
            self.assertEqual(default_ids, [new["id"]])
            everything = brain.recall("deploy cluster", config=config, include_superseded=True)["notes"]
            by_id = {note["id"]: note for note in everything}
            self.assertEqual(by_id[old["id"]]["superseded_by"], new["id"])

    def test_amend_appends_dated_addendum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            stored = brain.remember("the cron runs hourly", kind="fact", project="demo", config=config)
            result = brain.amend(stored["id"], "actually it runs every 30 minutes", config=config)
            self.assertTrue(result["amended"])
            notes = brain.recall("30 minutes cron", config=config)["notes"]
            self.assertEqual([note["id"] for note in notes], [stored["id"]])
            self.assertIn("[AMENDED", notes[0]["content"])

    def test_remember_reports_similar_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            first = brain.remember(
                "ABC-123 worker guards demote leads without an active package",
                kind="note",
                project="demo",
                tags=["ABC-123", "worker"],
                config=config,
            )
            second = brain.remember(
                "ABC-123 verified in dev: worker demotes duplicate leads correctly",
                kind="note",
                project="demo",
                tags=["ABC-123", "qa"],
                config=config,
            )
            self.assertTrue(second["stored"])
            self.assertIn(first["id"], [note["id"] for note in second.get("similar_notes", [])])

    def test_thread_digest_is_chronological_and_collapses_superseded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            a = brain.remember("ABC-123 kickoff decision", kind="decision", tags=["ABC-123"], config=config)
            b = brain.remember("ABC-123 wrong assumption about caching", kind="fact", tags=["ABC-123"], config=config)
            c = brain.remember(
                "ABC-123 corrected caching model", kind="fact", tags=["ABC-123"], config=config, supersedes=[b["id"]]
            )
            digest = brain.recall(config=config, thread="ABC-123")
            self.assertEqual([note["id"] for note in digest["notes"]], [a["id"], c["id"]])
            self.assertEqual([stub["id"] for stub in digest["superseded_stubs"]], [b["id"]])

    def test_reference_kind_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            stored = brain.remember(
                "Ops runbook: wiki page 42 covers pause/resume and transfers",
                kind="reference",
                project="demo",
                config=config,
            )
            self.assertTrue(stored["stored"])
            hits = brain.recall("pause runbook", kind="reference", config=config)["notes"]
            self.assertEqual([note["id"] for note in hits], [stored["id"]])

    def test_repo_state_on_non_git_dir_and_temp_repo(self) -> None:
        import subprocess

        from agent_workbench.repo_state import repo_state

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = WorkbenchConfig(repo_root=root, projects_root=root, workbench_home=root / "state")
            plain = root / "plain"
            plain.mkdir()
            self.assertIn("error", repo_state(str(plain), config))

            repo = root / "repo1"
            repo.mkdir()
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            state = repo_state("repo1", config)
            self.assertIn("branch", state)
            self.assertTrue(any("baseline" in warning for warning in state["warnings"]))

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
