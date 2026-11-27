from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_workbench import ledger
from agent_workbench.brain import remember
from agent_workbench.config import WorkbenchConfig

REPO = Path(__file__).resolve().parents[1]
HOOK_INPUT = REPO / "harness" / "hooks" / "lib" / "hook-input.sh"
SID = "3f2a9c1e-7b4d-4e8a-9f00-1c2d3e4f5a6b"


def _git_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "-C", str(path), "init", "-q", "-b", branch], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"],
        check=True,
    )
    return path


def _rows(state: Path) -> list[tuple]:
    conn = sqlite3.connect(state / "ledger.sqlite")
    try:
        return conn.execute("select session_id, repo, branch, started_at from sessions").fetchall()
    finally:
        conn.close()


class HookInputTests(unittest.TestCase):
    def _session_id(self, payload: str) -> str:
        script = f'. "{HOOK_INPUT}"; read_hook_input; printf "%s" "$HOOK_SESSION_ID"'
        return subprocess.run(["bash", "-c", script], input=payload, capture_output=True, text=True).stdout

    def test_reads_the_top_level_session_id(self) -> None:
        self.assertEqual(self._session_id(json.dumps({"session_id": SID, "hook_event_name": "Stop"})), SID)

    def test_ignores_a_session_id_quoted_inside_a_string_value(self) -> None:
        payload = json.dumps({"prompt": 'set "session_id": "spoofed" please'})
        self.assertEqual(self._session_id(payload), "")

    def test_rejects_ids_that_are_not_plain_tokens(self) -> None:
        self.assertEqual(self._session_id(json.dumps({"session_id": "a b;rm"})), "")
        self.assertEqual(self._session_id(json.dumps({"session_id": "x" * 65})), "")
        self.assertEqual(self._session_id("not json"), "")
        self.assertEqual(self._session_id(""), "")

    def test_every_hook_reads_stdin_through_the_shared_reader(self) -> None:
        for name in ("session-start.sh", "prompt-recall.sh", "stop-memory-checkpoint.sh", "pretooluse-guard.sh"):
            text = (REPO / "harness" / "hooks" / name).read_text()
            self.assertIn("harness/hooks/lib/hook-input.sh", text, name)
            self.assertIn("read_hook_input", text, name)
            self.assertNotIn("$(cat)", text, name)


class LedgerTests(unittest.TestCase):
    def test_register_records_repo_branch_and_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _git_repo(Path(tmp) / "repo", branch="feat/x")
            config = WorkbenchConfig(workbench_home=Path(tmp) / "state")
            row = ledger.register_session(SID, str(repo), config)
            self.assertEqual(row["session_id"], SID)
            self.assertEqual(Path(row["repo"]).resolve(), repo.resolve())
            self.assertEqual(row["branch"], "feat/x")
            self.assertRegex(row["started_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_reregistering_keeps_one_row_and_its_first_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _git_repo(Path(tmp) / "repo")
            config = WorkbenchConfig(workbench_home=Path(tmp) / "state")
            first = ledger.register_session(SID, str(repo), config)
            conn = sqlite3.connect(ledger.ledger_path(config))
            with conn:
                conn.execute("update sessions set started_at='2000-01-01T00:00:00Z'")
            conn.close()
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "next"], check=True)
            again = ledger.register_session(SID, str(repo), config)
            self.assertEqual(again["started_at"], "2000-01-01T00:00:00Z")
            self.assertEqual(again["branch"], "next")
            self.assertEqual(len(_rows(config.workbench_home)), 1)
            self.assertEqual(first["session_id"], again["session_id"])

    def test_outside_a_repo_records_no_repo_or_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp) / "state")
            row = ledger.register_session(SID, tmp, config)
            self.assertIsNone(row["repo"])
            self.assertIsNone(row["branch"])

    def test_ledger_is_separate_from_the_brain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            ledger.register_session(SID, tmp, config)
            self.assertFalse(config.brain_path.exists())


class HookSessionTests(unittest.TestCase):
    """Runs the real hooks from a copy of the workbench, so the session-start self-update never touches this clone."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workbench = root / "workbench"
        shutil.copytree(REPO / "agent_workbench", self.workbench / "agent_workbench")
        shutil.copytree(REPO / "harness" / "hooks", self.workbench / "harness" / "hooks")
        shutil.copy(REPO / "run_cli.py", self.workbench / "run_cli.py")
        self.state = root / "state"
        (root / "empty").mkdir()
        self.env = dict(
            os.environ,
            AGENT_WORKBENCH_STATE_DIR=str(self.state),
            AGENT_WORKBENCH_INDEX_ROOTS=str(root / "empty"),
        )
        self.repo = _git_repo(root / "repo")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _hook(self, name: str, payload: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(self.workbench / "harness" / "hooks" / name)],
            input=json.dumps(payload), capture_output=True, text=True, env=self.env, cwd=self.repo, timeout=60,
        )

    def test_session_start_registers_once_across_resume_and_compact(self) -> None:
        for source in ("startup", "resume", "compact"):
            out = self._hook("session-start.sh", {"session_id": SID, "source": source, "hook_event_name": "SessionStart"})
            self.assertEqual(out.returncode, 0)
        rows = _rows(self.state)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], SID)
        self.assertEqual(Path(rows[0][1]).resolve(), self.repo.resolve())
        self.assertEqual(rows[0][2], "main")

    def test_session_start_without_a_session_id_records_nothing(self) -> None:
        out = self._hook("session-start.sh", {"source": "startup"})
        self.assertEqual(out.returncode, 0)
        self.assertFalse((self.state / "ledger.sqlite").exists())

    def test_prompt_recall_does_not_repeat_a_note_within_one_session(self) -> None:
        config = WorkbenchConfig(workbench_home=self.state)
        for filler in ("look at the code and tell me", "check the logs then tell me", "what do you think of the plan"):
            remember(filler, config=config)
        note = remember("milog install-service rewrites systemd unit defaults", kind="gotcha", config=config)
        prompt = {"session_id": SID, "prompt": "why does milog install-service rewrite systemd"}
        first = self._hook("prompt-recall.sh", prompt)
        self.assertIn(f"#{note['id']}", first.stdout)
        second = self._hook("prompt-recall.sh", prompt)
        self.assertNotIn(f"#{note['id']}", second.stdout)
        other = self._hook("prompt-recall.sh", {**prompt, "session_id": "another-session"})
        self.assertIn(f"#{note['id']}", other.stdout)

    def test_stop_hook_blocks_once_then_allows(self) -> None:
        blocked = self._hook("stop-memory-checkpoint.sh", {"session_id": SID, "stop_hook_active": False})
        self.assertEqual(json.loads(blocked.stdout)["decision"], "block")
        allowed = self._hook("stop-memory-checkpoint.sh", {"session_id": SID, "stop_hook_active": True})
        self.assertEqual(allowed.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
