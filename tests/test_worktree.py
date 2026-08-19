from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_workbench.activity import recent_activity
from agent_workbench.code_index import _dedupe_worktrees, _repo_roots
from agent_workbench.config import WorkbenchConfig
from agent_workbench.repo_state import git_common_dir, is_linked_worktree, main_worktree, repo_state


def _run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), capture_output=True, check=True)


class WorktreeFixture(unittest.TestCase):
    """A main checkout plus one linked worktree on a second branch."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.main = self.root / "main"
        self.main.mkdir()
        _run("git", "init", "-q", cwd=self.main)
        _run("git", "config", "user.email", "dev@example.com", cwd=self.main)
        _run("git", "config", "user.name", "Dev Example", cwd=self.main)
        self._commit("first work")
        _run("git", "branch", "-q", "feature", cwd=self.main)
        self.worktree = self.root / "wt"
        _run("git", "worktree", "add", "-q", str(self.worktree), "feature", cwd=self.main)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _commit(self, subject: str, *, at: Path | None = None) -> None:
        repo = at or self.main
        (repo / "file.txt").write_text(subject)
        _run("git", "add", ".", cwd=repo)
        stamp = "2026-08-19T12:00:00"
        subprocess.run(
            ["git", "commit", "-q", "-m", subject],
            cwd=str(repo),
            capture_output=True,
            check=True,
            env={**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )

    def _config(self) -> WorkbenchConfig:
        return WorkbenchConfig(index_roots=(self.root,), projects_root=self.root)


class IdentityTests(WorktreeFixture):
    def test_worktree_and_main_share_one_identity(self) -> None:
        # The whole fix rests on this: same repo, same key.
        self.assertEqual(git_common_dir(self.worktree), git_common_dir(self.main))

    def test_linked_worktree_is_distinguishable_from_main(self) -> None:
        self.assertTrue(is_linked_worktree(self.worktree))
        self.assertFalse(is_linked_worktree(self.main))
        self.assertEqual(main_worktree(self.worktree).resolve(), self.main.resolve())


class ActivityTests(WorktreeFixture):
    def test_commit_is_counted_once_not_once_per_worktree(self) -> None:
        # The regression: both trees were scanned as independent repos, so a
        # single commit was reported twice and every standup inflated.
        report = recent_activity(
            since="2026-08-19", until="2026-08-19", config=self._config(), roots=[str(self.root)]
        )
        self.assertEqual(report["total_commits"], 1)
        self.assertEqual(report["repos_with_activity"], 1)

    def test_the_surviving_entry_is_the_main_checkout(self) -> None:
        report = recent_activity(
            since="2026-08-19", until="2026-08-19", config=self._config(), roots=[str(self.root)]
        )
        self.assertEqual(Path(report["repos"][0]["path"]).resolve(), self.main.resolve())

    def test_folded_worktrees_are_still_reported(self) -> None:
        # Collapsing must not hide that parallel work exists, or the human
        # loses the one signal that a second branch was in play.
        report = recent_activity(
            since="2026-08-19", until="2026-08-19", config=self._config(), roots=[str(self.root)]
        )
        listed = report["repos"][0].get("worktrees") or []
        self.assertEqual([item["branch"] for item in listed], ["feature"])

    def test_worktree_only_commit_still_counted_once(self) -> None:
        self._commit("branch work", at=self.worktree)
        report = recent_activity(
            since="2026-08-19", until="2026-08-19", config=self._config(), roots=[str(self.root)]
        )
        # --all from the main checkout sees the feature branch too.
        subjects = {commit["subject"] for commit in report["repos"][0]["commits"]}
        self.assertEqual(subjects, {"first work", "branch work"})
        self.assertEqual(report["total_commits"], 2)


class IndexTests(WorktreeFixture):
    def test_index_keeps_one_checkout_per_repository(self) -> None:
        found = _repo_roots([self.root])
        self.assertEqual(len(found), 2)  # both look like repos on disk
        deduped = _dedupe_worktrees(found)
        self.assertEqual([p.resolve() for p in deduped], [self.main.resolve()])

    def test_orphaned_worktree_is_still_indexed(self) -> None:
        # If the main checkout is gone, the worktree is the only view we have;
        # dropping it would lose the repo entirely.
        deduped = _dedupe_worktrees([self.worktree, self.root / "vanished"])
        self.assertIn(self.main.resolve(), [p.resolve() for p in deduped])


class RepoStateTests(WorktreeFixture):
    def test_worktree_is_flagged_with_its_main_checkout(self) -> None:
        state = repo_state(str(self.worktree))
        self.assertTrue(state["worktree"])
        self.assertEqual(Path(state["main_worktree"]).resolve(), self.main.resolve())
        self.assertTrue(any("linked worktree" in w for w in state["warnings"]))

    def test_main_checkout_is_not_flagged(self) -> None:
        self.assertNotIn("worktree", repo_state(str(self.main)))

    def test_branch_is_read_from_the_worktree_not_the_main_tree(self) -> None:
        self.assertEqual(repo_state(str(self.worktree))["branch"], "feature")
        self.assertNotEqual(repo_state(str(self.main))["branch"], "feature")


if __name__ == "__main__":
    unittest.main()
