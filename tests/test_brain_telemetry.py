from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_workbench import brain
from agent_workbench.config import WorkbenchConfig


class RecallTelemetryTests(unittest.TestCase):
    """The brain only grew, and nothing recorded whether a note was ever read.

    Counting reads gives recall a signal it can rank on, and gives any later
    consolidation an objective staleness measure instead of a date heuristic.
    """

    def _config(self, tmp: str) -> WorkbenchConfig:
        return WorkbenchConfig(workbench_home=Path(tmp))

    def test_a_recall_counts_and_timestamps_the_notes_it_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = brain.remember("the cron runs hourly", kind="fact", project="demo", config=config)
            brain.recall("cron hourly", config=config)
            note = brain.recall("cron hourly", config=config)["notes"][0]
            self.assertEqual(note["id"], stored["id"])
            self.assertEqual(note["recall_count"], 1)
            self.assertIn("last_recalled_at_iso", note)

    def test_the_count_shown_is_the_one_before_this_read(self) -> None:
        # The select runs before the write, so a note reports the reads that
        # preceded this one. A first read therefore carries no count at all.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            brain.remember("the cron runs hourly", kind="fact", project="demo", config=config)
            first = brain.recall("cron hourly", config=config)["notes"][0]
            self.assertNotIn("recall_count", first)
            self.assertNotIn("last_recalled_at", first)

    def test_a_rehearsed_note_outranks_an_equal_textual_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            alpha = brain.remember("widget alpha handling", kind="fact", project="demo", config=config)
            beta = brain.remember("widget beta handling", kind="fact", project="demo", config=config)
            before = [n["id"] for n in brain.recall("widget handling", config=config)["notes"]]
            self.assertEqual(before, [alpha["id"], beta["id"]])
            for _ in range(4):
                brain.recall("beta", config=config)
            after = [n["id"] for n in brain.recall("widget handling", config=config)["notes"]]
            self.assertEqual(after[0], beta["id"], "rehearsed note did not win an equal match")

    def test_rehearsal_does_not_reorder_a_recency_listing(self) -> None:
        # Ordering by date exists to preserve a timeline; a boost there would
        # quietly rewrite it.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            first = brain.remember("oldest entry", kind="note", project="demo", config=config)
            brain.remember("middle entry", kind="note", project="demo", config=config)
            last = brain.remember("newest entry", kind="note", project="demo", config=config)
            for _ in range(8):
                brain.recall("oldest", config=config)
            ids = [n["id"] for n in brain.recall(config=config)["notes"]]
            self.assertEqual(ids[0], last["id"])
            self.assertEqual(ids[-1], first["id"])

    def test_forgetting_a_note_drops_its_counters(self) -> None:
        # FTS5 reuses a freed rowid, so a surviving stats row would hand the
        # deleted note's count to whatever is stored next.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = brain.remember("transient note", kind="note", project="demo", config=config)
            brain.recall("transient", config=config)
            brain.forget(stored["id"], config=config)
            conn = brain._connect(config)
            try:
                rows = conn.execute("select note_id from note_stats").fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [])

    def test_a_thread_digest_counts_the_notes_it_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            brain.remember("rollout started", kind="note", project="demo", tags=["rollout"], config=config)
            brain.recall(thread="rollout", config=config)
            note = brain.recall("rollout started", config=config)["notes"][0]
            self.assertEqual(note["recall_count"], 1)

    def test_a_failed_count_does_not_fail_the_recall(self) -> None:
        # Several sessions can read at once, so a locked or missing stats table
        # must cost a count, never the lookup the caller asked for.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = brain.remember("still readable", kind="fact", project="demo", config=config)
            conn = brain._connect(config)
            try:
                conn.execute("drop table note_stats")
                conn.commit()
                brain._record_recall(conn, [stored["id"]])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
