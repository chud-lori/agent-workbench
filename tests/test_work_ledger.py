from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_workbench import code_index, ledger
from agent_workbench.config import WorkbenchConfig
from agent_workbench.knowledge import brief_task

REPO = Path(__file__).resolve().parents[1]
MINE = "session-mine"
THEIRS = "session-theirs"


class ClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.config = WorkbenchConfig(workbench_home=self.base / "state")
        self.file = self.base / "app.py"
        self.file.write_text("x = 1\n")

    def _age_claims(self, stamp: str) -> None:
        conn = sqlite3.connect(ledger.ledger_path(self.config))
        with conn:
            conn.execute("update claims set claimed_at=?", (stamp,))
        conn.close()

    def test_a_claim_is_seen_by_other_sessions_only(self) -> None:
        ledger.claim_path(THEIRS, str(self.file), self.config)
        (claim,) = ledger.open_claims([str(self.file)], MINE, self.config)
        self.assertEqual(claim["session_id"], THEIRS)
        self.assertEqual(claim["path"], os.path.realpath(self.file))
        self.assertEqual(ledger.open_claims([str(self.file)], THEIRS, self.config), [])

    def test_a_claim_older_than_a_week_is_ignored_then_collected(self) -> None:
        ledger.claim_path(THEIRS, str(self.file), self.config)
        self._age_claims("2000-01-01T00:00:00Z")
        self.assertEqual(ledger.open_claims([str(self.file)], MINE, self.config), [])
        ledger.claim_path(MINE, str(self.base / "other.py"), self.config)
        conn = sqlite3.connect(ledger.ledger_path(self.config))
        self.assertEqual(conn.execute("select session_id from claims").fetchall(), [(MINE,)])
        conn.close()

    def test_no_ledger_means_no_claims_and_no_file(self) -> None:
        self.assertEqual(ledger.open_claims([str(self.file)], MINE, self.config), [])
        self.assertFalse(ledger.ledger_path(self.config).exists())

    def test_claims_stay_out_of_the_brain(self) -> None:
        ledger.claim_path(THEIRS, str(self.file), self.config)
        self.assertFalse(self.config.brain_path.exists())


class BriefTaskClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        root = base / "code"
        self.repo = root / "shop"
        self.repo.mkdir(parents=True)
        (self.repo / "README.md").write_text("# shop\n")
        (self.repo / "checkout.py").write_text("def apply_voucher_discount():\n    return 0\n")
        self.config = WorkbenchConfig(
            workbench_home=base / "state", repo_root=root, projects_root=root, index_roots=(root,)
        )
        code_index.rebuild_index(self.config)

    def test_warns_when_another_session_claimed_a_hit(self) -> None:
        ledger.claim_path(THEIRS, str(self.repo / "checkout.py"), self.config)
        warnings = brief_task("apply_voucher_discount", self.config, MINE).get("warnings", [])
        self.assertIn("another session (session-) claimed shop/checkout.py 0 minutes ago", warnings)

    def test_stays_quiet_about_its_own_claim(self) -> None:
        ledger.claim_path(MINE, str(self.repo / "checkout.py"), self.config)
        warnings = brief_task("apply_voucher_discount", self.config, MINE).get("warnings", [])
        self.assertFalse([w for w in warnings if "claimed" in w])


class ClaimHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.file = Path(self.tmp.name) / "notes.md"

    def _hook(self, payload: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(REPO / "harness" / "hooks" / "claim-edit.sh")],
            input=json.dumps(payload), capture_output=True, text=True, timeout=30,
            env=dict(os.environ, AGENT_WORKBENCH_STATE_DIR=str(self.state)),
        )

    def test_an_edit_claims_its_file_for_the_session(self) -> None:
        out = self._hook({"session_id": THEIRS, "tool_name": "Edit", "tool_input": {"file_path": str(self.file)}})
        self.assertEqual((out.returncode, out.stdout), (0, ""))
        config = WorkbenchConfig(workbench_home=self.state)
        (claim,) = ledger.open_claims([str(self.file)], MINE, config)
        self.assertEqual(claim["session_id"], THEIRS)

    def test_without_a_session_id_nothing_is_claimed(self) -> None:
        out = self._hook({"tool_name": "Write", "tool_input": {"file_path": str(self.file)}})
        self.assertEqual(out.returncode, 0)
        self.assertFalse((self.state / "ledger.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
