from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_workbench import brain, mcp_server
from agent_workbench.config import WorkbenchConfig


def _call(handlers: dict, name: str, args: dict) -> tuple[str, dict]:
    response = mcp_server._handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}},
        handlers,
    )
    text = response["result"]["content"][0]["text"]
    return text, json.loads(text)


class RecallSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = WorkbenchConfig(workbench_home=Path(self.tmp.name))
        patcher = mock.patch.object(mcp_server, "default_config", return_value=self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.handlers = {"brain_recall": mcp_server._brain_recall}

    def _store(self, count: int, body_chars: int = 50) -> list[int]:
        ids = []
        for n in range(count):
            content = f"widget note {n} " + "x" * body_chars + f"\nsecond line {n}"
            ids.append(brain.remember(content, kind="fact", project="demo", config=self.config)["id"])
        return ids

    def test_at_threshold_returns_full_bodies(self) -> None:
        self._store(mcp_server.SUMMARY_THRESHOLD)
        _, result = _call(self.handlers, "brain_recall", {"query": "widget"})
        self.assertNotIn("truncated", result)
        self.assertTrue(all("content" in note for note in result["notes"]))

    def test_above_threshold_defaults_to_summaries(self) -> None:
        self._store(mcp_server.SUMMARY_THRESHOLD + 1, body_chars=400)
        _, result = _call(self.handlers, "brain_recall", {"query": "widget"})
        self.assertTrue(result["truncated"])
        self.assertEqual(result["notes_count"], mcp_server.SUMMARY_THRESHOLD + 1)
        for note in result["notes"]:
            self.assertEqual(set(note), {"id", "kind", "project", "created_at_iso", "title"})
            self.assertLessEqual(len(note["title"]), mcp_server.SUMMARY_CHARS)
            self.assertNotIn("second line", note["title"])

    def test_explicit_summary_only_overrides_the_default(self) -> None:
        self._store(mcp_server.SUMMARY_THRESHOLD + 1)
        _, full = _call(self.handlers, "brain_recall", {"query": "widget", "summary_only": False})
        self.assertTrue(all("content" in note for note in full["notes"]))
        _, few = _call(self.handlers, "brain_recall", {"query": "widget", "limit": 2, "summary_only": True})
        self.assertTrue(all("title" in note and "content" not in note for note in few["notes"]))

    def test_broad_query_stays_under_cap_by_default(self) -> None:
        self._store(60, body_chars=2500)
        text, result = _call(self.handlers, "brain_recall", {"query": "widget", "limit": 60})
        self.assertLessEqual(len(text.encode()), mcp_server.RESULT_BYTE_CAP)
        self.assertTrue(result["truncated"])

    def test_full_text_by_id(self) -> None:
        ids = self._store(8, body_chars=2500)
        brain.resolve(ids[3], config=self.config)
        _, result = _call(self.handlers, "brain_recall", {"ids": [ids[3], ids[0], 9999]})
        self.assertEqual([note["id"] for note in result["notes"]], [ids[3], ids[0]])
        self.assertIn("second line 3", result["notes"][0]["content"])
        self.assertEqual(result["missing"], [9999])
        self.assertNotIn("truncated", result)


class ResultCapTests(unittest.TestCase):
    def test_cap_cuts_whole_items_and_flags_truncated(self) -> None:
        payload = {"items": [{"n": n, "body": "y" * 500} for n in range(100)], "nested": {"rows": list(range(500))}}
        text, result = _call({"big": lambda args: payload}, "big", {})
        self.assertLessEqual(len(text.encode()), mcp_server.RESULT_BYTE_CAP)
        self.assertTrue(result["truncated"])
        self.assertIn("narrow", result["hint"])
        kept = result["items"]
        self.assertEqual([item["n"] for item in kept], list(range(len(kept))))
        self.assertTrue(all(item["body"] == "y" * 500 for item in kept))
        self.assertEqual(result["dropped_items"]["items"], 100 - len(kept))

    def test_small_result_is_untouched(self) -> None:
        _, result = _call({"small": lambda args: {"items": [1, 2, 3]}}, "small", {})
        self.assertEqual(result, {"items": [1, 2, 3]})

    def test_one_oversized_item_comes_back_whole(self) -> None:
        text, result = _call({"one": lambda args: {"notes": [{"content": "z" * 20_000}]}}, "one", {})
        self.assertEqual(len(result["notes"][0]["content"]), 20_000)
        self.assertTrue(result["truncated"])

    def test_exempt_tool_is_not_capped(self) -> None:
        payload = {"findings": [{"detail": "w" * 500} for _ in range(100)]}
        _, result = _call({"doctor_report": lambda args: payload}, "doctor_report", {})
        self.assertEqual(len(result["findings"]), 100)
        self.assertNotIn("truncated", result)


class RecentActivityShapeTests(unittest.TestCase):
    def _fake(self, *args, **kwargs) -> dict:
        commits = [{"sha": "abc1234", "at": "2026-07-15T10:00:00", "subject": "s", "author": "a"}]
        return {
            "repos": [
                {"repo": "alpha", "path": "/r/alpha", "branch": "main", "commit_count": 1, "commits": list(commits)},
                {"repo": "beta", "path": "/r/beta", "branch": "main", "commit_count": 1, "commits": list(commits)},
            ]
        }

    def test_counts_by_default_and_commits_for_a_named_repo(self) -> None:
        with mock.patch.object(mcp_server, "recent_activity", side_effect=self._fake):
            counts = mcp_server._recent_activity({})
            self.assertEqual([entry["repo"] for entry in counts["repos"]], ["alpha", "beta"])
            self.assertTrue(all("commits" not in entry for entry in counts["repos"]))
            named = mcp_server._recent_activity({"repo": "beta"})
            self.assertEqual([entry["repo"] for entry in named["repos"]], ["beta"])
            self.assertEqual(len(named["repos"][0]["commits"]), 1)


if __name__ == "__main__":
    unittest.main()
