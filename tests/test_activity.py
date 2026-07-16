from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_workbench import brain
from agent_workbench.activity import recent_activity
from agent_workbench.config import WorkbenchConfig
from agent_workbench.util import parse_time_bound


# A fixed "now" so relative bounds are assertable: 16 Jul 2026, 09:30 local.
NOW = time.mktime(time.strptime("2026-07-16 09:30:00", "%Y-%m-%d %H:%M:%S"))


class TimeBoundTests(unittest.TestCase):
    def test_bare_date_is_day_aligned_and_end_of_day_is_inclusive(self) -> None:
        start = parse_time_bound("2026-07-15", now=NOW)
        end = parse_time_bound("2026-07-15", end_of_day=True, now=NOW)
        self.assertEqual(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start)), "2026-07-15 00:00:00")
        self.assertEqual(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end)), "2026-07-15 23:59:59")

    def test_yesterday_spans_exactly_one_day(self) -> None:
        start = parse_time_bound("yesterday", now=NOW)
        end = parse_time_bound("yesterday", end_of_day=True, now=NOW)
        self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(start)), "2026-07-15")
        self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(end)), "2026-07-15")
        self.assertEqual(end - start, 86399)

    def test_relative_and_iso_forms(self) -> None:
        self.assertEqual(
            time.strftime("%Y-%m-%d %H:%M", time.localtime(parse_time_bound("7d", now=NOW))),
            "2026-07-09 09:30",
        )
        self.assertEqual(
            time.strftime("%Y-%m-%d %H:%M", time.localtime(parse_time_bound("2026-07-15T14:00:00", now=NOW))),
            "2026-07-15 14:00",
        )

    def test_returns_int_because_a_string_epoch_matches_nothing_in_sqlite(self) -> None:
        # FTS5 keeps `created_at unindexed` as an integer, so `created_at >= '123'`
        # silently matches zero rows. Every bound must reach sqlite as an int.
        for value in ("2026-07-15", "yesterday", "7d", "2026-07-15T14:00:00", 1784000000, 1784000000.5):
            self.assertIsInstance(parse_time_bound(value, now=NOW), int)

    def test_none_passes_through_and_garbage_raises(self) -> None:
        self.assertIsNone(parse_time_bound(None))
        for bad in ("last tuesday", "2026-13-45", "soon"):
            with self.assertRaises(ValueError):
                parse_time_bound(bad, now=NOW)


class RecallWindowTests(unittest.TestCase):
    def _brain_with_dated_notes(self, tmp: str) -> WorkbenchConfig:
        config = WorkbenchConfig(workbench_home=Path(tmp))
        for day, text in (
            ("2026-07-14", "note from the fourteenth"),
            ("2026-07-15", "note from the fifteenth"),
            ("2026-07-15", "another from the fifteenth"),
            ("2026-07-16", "note from the sixteenth"),
        ):
            stored = brain.remember(text, kind="note", project="demo", config=config)
            epoch = int(time.mktime(time.strptime(f"{day} 12:00:00", "%Y-%m-%d %H:%M:%S")))
            conn = brain._connect(config)
            conn.execute("update notes set created_at=? where rowid=?", (epoch, stored["id"]))
            conn.commit()
            conn.close()
        return config

    def test_window_selects_only_that_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain_with_dated_notes(tmp)
            hits = brain.recall(since="2026-07-15", until="2026-07-15", config=config)
            contents = sorted(note["content"] for note in hits["notes"])
            self.assertEqual(contents, ["another from the fifteenth", "note from the fifteenth"])
            self.assertEqual(hits["window"]["matched_in_window"], 2)

    def test_until_bare_date_includes_the_whole_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain_with_dated_notes(tmp)
            # A midday note on the 15th must survive until='2026-07-15'.
            hits = brain.recall(since="2026-07-14", until="2026-07-15", config=config)
            self.assertEqual(len(hits["notes"]), 3)

    def test_limit_truncation_is_announced_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain_with_dated_notes(tmp)
            hits = brain.recall(since="2026-07-14", limit=1, config=config)
            self.assertTrue(hits["truncated"])
            self.assertEqual(hits["window"]["matched_in_window"], 4)
            self.assertIn("limit", hits["hint"])

    def test_date_filter_runs_before_the_limit_cap(self) -> None:
        # The regression this guards: newest-first + a cap used to drop an older
        # day entirely, so an empty result read as "nothing happened that day".
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain_with_dated_notes(tmp)
            hits = brain.recall(since="2026-07-14", until="2026-07-14", limit=1, config=config)
            self.assertEqual([note["content"] for note in hits["notes"]], ["note from the fourteenth"])

    def test_query_and_window_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain_with_dated_notes(tmp)
            hits = brain.recall(query="fifteenth", since="2026-07-15", until="2026-07-15", config=config)
            self.assertEqual(len(hits["notes"]), 2)

    def test_bad_and_inverted_bounds_error_rather_than_return_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain_with_dated_notes(tmp)
            self.assertIn("unrecognized", brain.recall(since="last tuesday", config=config)["error"])
            inverted = brain.recall(since="2026-07-16", until="2026-07-01", config=config)
            self.assertIn("after", inverted["error"])


class RecentActivityTests(unittest.TestCase):
    def _repo(self, root: Path, name: str, commits: list[tuple[str, str]]) -> Path:
        repo = root / name
        repo.mkdir(parents=True)
        for args in (("init", "-q"), ("config", "user.email", "dev@example.com"), ("config", "user.name", "Dev Example")):
            subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
        for day, subject in commits:
            self._commit(repo, day, subject)
        return repo

    def _commit(self, repo: Path, day: str, subject: str) -> None:
        (repo / "file.txt").write_text(subject)
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        stamp = f"{day}T12:00:00"
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", subject],
            capture_output=True,
            check=True,
            env={**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )

    def test_finds_commits_in_window_and_ignores_other_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root, "alpha", [("2026-07-14", "old work"), ("2026-07-15", "yesterday work")])
            config = WorkbenchConfig(index_roots=(root,), projects_root=root)
            report = recent_activity(since="2026-07-15", until="2026-07-15", config=config, roots=[str(root)])
            self.assertEqual(report["total_commits"], 1)
            self.assertEqual(report["repos"][0]["repo"], "alpha")
            self.assertEqual(report["repos"][0]["commits"][0]["subject"], "yesterday work")

    def test_finds_work_on_an_unchecked_out_branch(self) -> None:
        # The reason this scans --all: branch work that never got pushed is
        # invisible to `gh` and to anything reading only the default branch.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._repo(root, "beta", [("2026-07-15", "main work")])
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature"], check=True)
            self._commit(repo, "2026-07-15", "unpushed branch work")
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-"], check=True)
            config = WorkbenchConfig(index_roots=(root,), projects_root=root)
            report = recent_activity(since="2026-07-15", until="2026-07-15", config=config, roots=[str(root)])
            subjects = {commit["subject"] for commit in report["repos"][0]["commits"]}
            self.assertIn("unpushed branch work", subjects)

    def test_author_filter_excludes_other_people(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root, "gamma", [("2026-07-15", "mine")])
            config = WorkbenchConfig(index_roots=(root,), projects_root=root)
            report = recent_activity(
                since="2026-07-15", until="2026-07-15", author="someone.else@example.com", config=config, roots=[str(root)]
            )
            self.assertEqual(report["total_commits"], 0)
            self.assertIn("half", report["note"])

    def test_bad_bound_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = recent_activity(since="whenever", config=WorkbenchConfig(workbench_home=Path(tmp)))
            self.assertIn("unrecognized", report["error"])


if __name__ == "__main__":
    unittest.main()
