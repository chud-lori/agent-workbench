"""In-flight session state, kept apart from the brain: rows here live for hours, notes forever."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig, default_config
from .repo_state import _git

SESSIONS_SCHEMA = (
    "create table if not exists sessions("
    "session_id text primary key, repo text, branch text, started_at text not null)"
)


def ledger_path(config: WorkbenchConfig) -> Path:
    return config.workbench_home / "ledger.sqlite"


def register_session(session_id: str, cwd: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """Record a session's repo and branch; a resumed or compacted session keeps its first started_at."""
    config = config or default_config()
    repo = _git(Path(cwd), "rev-parse", "--show-toplevel") or None
    branch = (_git(Path(cwd), "rev-parse", "--abbrev-ref", "HEAD") or None) if repo else None
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config.workbench_home.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_path(config), timeout=5)
    try:
        with conn:
            conn.execute(SESSIONS_SCHEMA)
            conn.execute(
                "insert into sessions(session_id, repo, branch, started_at) values(?,?,?,?) "
                "on conflict(session_id) do update set repo=excluded.repo, branch=excluded.branch",
                (session_id, repo, branch, started_at),
            )
        row = conn.execute(
            "select session_id, repo, branch, started_at from sessions where session_id=?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(zip(("session_id", "repo", "branch", "started_at"), row))
