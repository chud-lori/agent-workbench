from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_workbench import brain
from agent_workbench.config import WorkbenchConfig


class NoteIdentityTests(unittest.TestCase):
    """A note id is a reference, so it must never point at two different notes.

    SQLite reuses the rowid freed by deleting the highest row. Note ids are
    cited by hand throughout the brain ("brain#42") and by every side table, so
    a reissued id silently rebinds those references.
    """

    def _config(self, tmp: str) -> WorkbenchConfig:
        return WorkbenchConfig(workbench_home=Path(tmp))

    def test_deleting_the_highest_note_does_not_free_its_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            brain.remember("first", kind="note", project="demo", config=config)
            second = brain.remember("second", kind="note", project="demo", config=config)
            brain.forget(second["id"], config=config)
            third = brain.remember("third", kind="note", project="demo", config=config)
            self.assertNotEqual(third["id"], second["id"])
            self.assertGreater(third["id"], second["id"])

    def test_ids_keep_climbing_across_repeated_deletes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            seen = []
            for index in range(5):
                stored = brain.remember(f"note {index}", kind="note", project="demo", config=config)
                seen.append(stored["id"])
                brain.forget(stored["id"], config=config)
            self.assertEqual(seen, sorted(set(seen)))

    def test_an_existing_brain_adopts_the_sequence_without_a_migration(self) -> None:
        # The mark seeds from the current maximum, so a brain written before
        # this existed keeps counting from where it left off.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            conn = brain._connect(config)
            try:
                conn.execute(
                    "insert into notes(rowid,content,kind,project,tags,created_at) values(?,?,?,?,?,?)",
                    (41, "written before the sequence existed", "note", "demo", "", 1),
                )
                conn.execute("delete from note_seq")
                conn.commit()
            finally:
                conn.close()
            self.assertEqual(brain.remember("next one", kind="note", project="demo", config=config)["id"], 42)

    def test_forget_clears_every_table_keyed_on_a_note_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = brain.remember("transient", kind="note", project="demo", config=config)
            brain.recall("transient", config=config)
            brain.forget(stored["id"], config=config)
            conn = brain._connect(config)
            try:
                for table in brain.NOTE_KEYED_TABLES:
                    rows = conn.execute(f"select 1 from {table} where note_id=?", (stored["id"],)).fetchall()
                    self.assertEqual(rows, [], f"{table} kept a row for a forgotten note")
            finally:
                conn.close()

    def test_the_registry_lists_every_table_that_keys_on_a_note_id(self) -> None:
        """The point of the registry: adding a side table cannot skip cleanup.

        A table with a note_id column that forget() does not clear accumulates
        rows for notes that no longer exist, which is how the first orphan bug
        happened.
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            brain.remember("seed", kind="note", project="demo", config=config)
            conn = brain._connect(config)
            try:
                tables = [
                    row[0]
                    for row in conn.execute("select name from sqlite_master where type='table'")
                    if not row[0].startswith("sqlite_")
                ]
                keyed = {
                    table
                    for table in tables
                    if any(column[1] == "note_id" for column in conn.execute(f"pragma table_info({table})"))
                }
            finally:
                conn.close()
            self.assertEqual(
                keyed,
                set(brain.NOTE_KEYED_TABLES),
                "a table keys on note_id but is not in NOTE_KEYED_TABLES, so forget() leaves its rows behind",
            )


if __name__ == "__main__":
    unittest.main()
