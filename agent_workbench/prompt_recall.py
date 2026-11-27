"""Note hits for the UserPromptSubmit hook: only strong matches, and each note once per session."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from typing import Any

from .brain import _connect, _fts_query, _record_recall
from .config import WorkbenchConfig, default_config


# bm25 grows with prompt length and idf tops out near ln(note count), so scores are divided by both.
RELEVANCE_FLOOR = 0.6
SESSION_TTL_SECONDS = 24 * 3600
MAX_SESSIONS = 50
SESSIONS_FILE = "prompt-recall-sessions.json"


def prompt_hits(
    prompt: str,
    session_id: str | None = None,
    limit: int = 5,
    config: WorkbenchConfig | None = None,
) -> list[dict[str, Any]]:
    """Notes matching the prompt at or above RELEVANCE_FLOOR, minus repeats in this session."""
    config = config or default_config()
    if not config.brain_path.exists():
        return []
    terms = sorted({term.lower() for term in re.findall(r"[A-Za-z0-9_/-]{2,}", prompt)})
    if not terms:
        return []
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("select count(*) from notes").fetchone()[0]
        norm = math.sqrt(len(terms)) * math.log(max(total, 2))
        rows = conn.execute(
            "select rowid as id, content, kind, project, bm25(notes) as rank from notes "
            "where notes match ? and resolved_at is null and superseded_by is null order by rank limit ?",
            (_fts_query(" ".join(terms)), limit),
        ).fetchall()
        hits = []
        for row in rows:
            strength = -row["rank"] / norm
            if strength >= RELEVANCE_FLOOR:
                hit = dict(row)
                del hit["rank"]
                hit["strength"] = round(strength, 3)
                hits.append(hit)
        if session_id:
            hits = _unseen(hits, session_id, config)
        _record_recall(conn, [hit["id"] for hit in hits])
        return hits
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _unseen(hits: list[dict[str, Any]], session_id: str, config: WorkbenchConfig) -> list[dict[str, Any]]:
    """Drop hits this session already got at equal or greater strength, and record the rest."""
    path = config.workbench_home / SESSIONS_FILE
    now = int(time.time())
    try:
        stored = json.loads(path.read_text())
        sessions = {
            sid: entry
            for sid, entry in stored.items()
            if now - int(entry["at"]) < SESSION_TTL_SECONDS and isinstance(entry["notes"], dict)
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        sessions = {}
    seen = sessions.get(session_id, {}).get("notes", {})
    fresh = [hit for hit in hits if hit["strength"] > seen.get(str(hit["id"]), 0)]
    seen.update({str(hit["id"]): hit["strength"] for hit in fresh})
    sessions[session_id] = {"at": now, "notes": seen}
    newest = sorted(sessions, key=lambda sid: sessions[sid]["at"], reverse=True)[:MAX_SESSIONS]
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps({sid: sessions[sid] for sid in newest}))
        os.replace(tmp, path)
    except OSError:
        pass
    return fresh
