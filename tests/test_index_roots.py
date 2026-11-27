from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_workbench import code_index
from agent_workbench.config import WorkbenchConfig, load_index_roots, save_index_roots


def _repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    (repo / "README.md").write_text(f"# {name}\nhello from {name}\n")
    return repo


class IndexRootsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.state = self.base / "state"
        env = {k: v for k, v in os.environ.items() if k != "AGENT_WORKBENCH_INDEX_ROOTS"}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_saved_roots_are_appended_without_duplicates(self) -> None:
        a, b = self.base / "a", self.base / "b"
        save_index_roots([str(a)], self.state)
        save_index_roots([str(b), str(a), ""], self.state)
        self.assertEqual(load_index_roots(self.state)[-2:], (a, b))
        self.assertEqual(len(set(load_index_roots(self.state))), len(load_index_roots(self.state)))

    def test_env_overrides_saved_roots(self) -> None:
        save_index_roots([str(self.base / "a")], self.state)
        with mock.patch.dict(os.environ, {"AGENT_WORKBENCH_INDEX_ROOTS": str(self.base / "env")}):
            self.assertEqual(load_index_roots(self.state), (self.base / "env",))

    def test_refresh_of_a_new_root_keeps_existing_repos(self) -> None:
        old_root, new_root = self.base / "old", self.base / "new"
        _repo(old_root, "kept")
        _repo(new_root, "added")
        config = WorkbenchConfig(workbench_home=self.state, index_roots=(old_root,))
        code_index.refresh_index(config)
        code_index.refresh_index(config, roots=[str(new_root)])
        self.assertEqual(self._repo_names(config), {"kept", "added"})

    def test_refresh_drops_a_repo_deleted_from_disk(self) -> None:
        root = self.base / "root"
        gone = _repo(root, "gone")
        _repo(root, "stays")
        config = WorkbenchConfig(workbench_home=self.state, index_roots=(root,))
        code_index.refresh_index(config)
        for item in gone.iterdir():
            item.unlink()
        gone.rmdir()
        code_index.refresh_index(config)
        self.assertEqual(self._repo_names(config), {"stays"})
        with sqlite3.connect(config.index_path) as conn:
            left = conn.execute("select count(*) from documents where repo_path=?", (str(gone),)).fetchone()[0]
        self.assertEqual(left, 0)

    def _repo_names(self, config: WorkbenchConfig) -> set[str]:
        with sqlite3.connect(config.index_path) as conn:
            return {row[0] for row in conn.execute("select name from repos")}


if __name__ == "__main__":
    unittest.main()
