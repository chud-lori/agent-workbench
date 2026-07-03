from __future__ import annotations

import re
import sqlite3
import time
from typing import Any

from .config import WorkbenchConfig, default_config


VALID_KINDS = {"decision", "fact", "gotcha", "preference", "todo", "note"}


def remember(
    content: str,
    kind: str = "note",
    project: str | None = None,
    tags: list[str] | None = None,
    config: WorkbenchConfig | None = None,
) -> dict[str, Any]:
    config = config or default_config()
    content = content.strip()
    if not content:
        return {"error": "content is empty; nothing stored"}
    if kind not in VALID_KINDS:
        return {"error": f"kind must be one of {sorted(VALID_KINDS)}"}
    config.workbench_home.mkdir(parents=True, exist_ok=True)
    conn = _connect(config)
    try:
        duplicate = conn.execute(
            "select rowid from notes where content=? and coalesce(project,'')=coalesce(?,'')",
            (content, project),
        ).fetchone()
        if duplicate:
            return {"id": duplicate[0], "stored": False, "warning": "identical note already exists"}
        cursor = conn.execute(
            "insert into notes(content,kind,project,tags,created_at) values(?,?,?,?,?)",
            (content, kind, project, " ".join(tags or []), int(time.time())),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "stored": True, "kind": kind, "project": project}
    finally:
        conn.close()


def recall(
    query: str | None = None,
    project: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    config: WorkbenchConfig | None = None,
) -> dict[str, Any]:
    config = config or default_config()
    if not config.brain_path.exists():
        return {"query": query, "notes": [], "warning": "brain is empty; store notes with brain_remember"}
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        clauses = []
        params: list[Any] = []
        if query and query.strip():
            clauses.append("notes match ?")
            params.append(_fts_query(query))
        if project:
            clauses.append("coalesce(project,'') = ?")
            params.append(project)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        order = "order by bm25(notes)" if query and query.strip() else "order by created_at desc, rowid desc"
        rows = conn.execute(
            f"select rowid as id, content, kind, project, tags, created_at from notes {where} {order} limit ?",
            (*params, limit),
        ).fetchall()
        total = conn.execute("select count(*) from notes").fetchone()[0]
        return {
            "query": query,
            "total_notes": total,
            "notes": [_note_dict(row) for row in rows],
        }
    except sqlite3.OperationalError as exc:
        return {"query": query, "notes": [], "error": str(exc)}
    finally:
        conn.close()


def forget(note_id: int, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    if not config.brain_path.exists():
        return {"id": note_id, "deleted": False, "warning": "brain is empty"}
    conn = _connect(config)
    try:
        cursor = conn.execute("delete from notes where rowid=?", (note_id,))
        conn.commit()
        return {"id": note_id, "deleted": cursor.rowcount > 0}
    finally:
        conn.close()


def _connect(config: WorkbenchConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(config.brain_path)
    conn.execute(
        """
        create virtual table if not exists notes using fts5(
            content,
            kind,
            project,
            tags,
            created_at unindexed
        )
        """
    )
    return conn


def _note_dict(row: sqlite3.Row) -> dict[str, Any]:
    note = dict(row)
    note["tags"] = row["tags"].split() if row["tags"] else []
    note["created_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(row["created_at"]))
    return note


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_/-]{2,}", query)
    return " OR ".join(f'"{term}"' for term in terms) if terms else '""'
