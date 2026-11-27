"""In-flight session state, kept apart from the brain: rows here live for hours, notes forever."""

from __future__ import annotations

import os
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
CLAIMS_SCHEMA = (
    "create table if not exists claims("
    "session_id text not null, path text not null, claimed_at text not null, primary key(session_id, path))"
)
CLAIM_TTL_SECONDS = 7 * 24 * 3600
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def ledger_path(config: WorkbenchConfig) -> Path:
    return config.workbench_home / "ledger.sqlite"


def register_session(session_id: str, cwd: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """Record a session's repo and branch; a resumed or compacted session keeps its first started_at."""
    config = config or default_config()
    repo = _git(Path(cwd), "rev-parse", "--show-toplevel") or None
    branch = (_git(Path(cwd), "rev-parse", "--abbrev-ref", "HEAD") or None) if repo else None
    started_at = time.strftime(STAMP, time.gmtime())
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


def claim_path(session_id: str, path: str, config: WorkbenchConfig | None = None) -> None:
    """Mark a file as being worked on by this session; each edit refreshes the claim."""
    config = config or default_config()
    now = time.time()
    config.workbench_home.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_path(config), timeout=5)
    try:
        with conn:
            conn.execute(CLAIMS_SCHEMA)
            conn.execute("delete from claims where claimed_at < ?", (_stamp(now - CLAIM_TTL_SECONDS),))
            conn.execute(
                "insert into claims(session_id, path, claimed_at) values(?,?,?) "
                "on conflict(session_id, path) do update set claimed_at=excluded.claimed_at",
                (session_id, os.path.realpath(path), _stamp(now)),
            )
    finally:
        conn.close()


def open_claims(paths: list[str], exclude_session: str | None = None, config: WorkbenchConfig | None = None) -> list[dict[str, Any]]:
    """Claims younger than the TTL on any of these paths, newest first, skipping exclude_session's own."""
    config = config or default_config()
    if not paths or not ledger_path(config).exists():
        return []
    wanted = sorted({os.path.realpath(path) for path in paths})
    conn = sqlite3.connect(ledger_path(config), timeout=5)
    try:
        conn.execute(CLAIMS_SCHEMA)
        rows = conn.execute(
            f"select session_id, path, claimed_at from claims where path in ({','.join('?' * len(wanted))}) "
            "and claimed_at >= ? and session_id != ? order by claimed_at desc",
            (*wanted, _stamp(time.time() - CLAIM_TTL_SECONDS), exclude_session or ""),
        ).fetchall()
    finally:
        conn.close()
    return [dict(zip(("session_id", "path", "claimed_at"), row)) for row in rows]


def _stamp(epoch: float) -> str:
    return time.strftime(STAMP, time.gmtime(epoch))
