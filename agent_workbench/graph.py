"""The brain as a graph: notes are nodes, inline `kind#id` references and supersedes chains are edges."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .brain import VALID_KINDS
from .config import WorkbenchConfig, default_config

REF_PATTERN = re.compile(r"\b(?:brain|" + "|".join(sorted(VALID_KINDS)) + r")#(\d+)")
TITLE_CHARS = 120
SAMPLE_SIZE = 20
MOST_CITED = 10


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open the brain with mode=ro, so nothing reached through this connection can change it."""
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


def build(
    conn: sqlite3.Connection,
    *,
    project: str | None = None,
    include_resolved: bool = False,
    include_superseded: bool = False,
    with_content: bool = False,
) -> dict[str, Any]:
    """Nodes, edges and health stats for the notes that pass the filters.

    A reference to an id that exists but is filtered out adds no edge and is not
    dangling; only ids missing from the brain altogether count as dangling.
    """
    rows = conn.execute(
        "select rowid, content, kind, project, tags, created_at, resolved_at, superseded_by from notes order by rowid"
    ).fetchall()
    existing = {row[0] for row in rows}
    nodes: dict[int, dict[str, Any]] = {}
    contents: dict[int, str] = {}
    for note_id, content, note_kind, note_project, tags, created_at, resolved_at, superseded_by in rows:
        if project is not None and (note_project or "") != project:
            continue
        if resolved_at and not include_resolved:
            continue
        if superseded_by and not include_superseded:
            continue
        node: dict[str, Any] = {
            "id": note_id,
            "kind": note_kind,
            "project": note_project or "",
            "tags": tags.split() if tags else [],
            "title": _title(content),
            "created_at": created_at,
            "resolved": bool(resolved_at),
            "superseded_by": superseded_by,
            "cited_by": 0,
        }
        if with_content:
            node["content"] = content
        nodes[note_id] = node
        contents[note_id] = content

    edges: list[dict[str, Any]] = []
    dangling: list[dict[str, int]] = []
    for note_id, content in contents.items():
        for target in dict.fromkeys(int(match) for match in REF_PATTERN.findall(content)):
            if target == note_id:
                continue
            if target not in existing:
                dangling.append({"from": note_id, "to": target})
            elif target in nodes:
                edges.append({"source": note_id, "target": target, "type": "cites"})
                nodes[target]["cited_by"] += 1
    for note_id, node in nodes.items():
        newer = node["superseded_by"]
        if newer in nodes:
            edges.append({"source": newer, "target": note_id, "type": "supersedes"})

    linked = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    orphans = [note_id for note_id in nodes if note_id not in linked]
    cited = sorted((node for node in nodes.values() if node["cited_by"]), key=lambda node: (-node["cited_by"], node["id"]))
    types = Counter(edge["type"] for edge in edges)
    stats = {
        "notes": len(nodes),
        "edges": {"cites": types["cites"], "supersedes": types["supersedes"]},
        "orphans": {"count": len(orphans), "sample": orphans[:SAMPLE_SIZE]},
        "dangling": {"count": len(dangling), "sample": dangling[:SAMPLE_SIZE]},
        "most_cited": [
            {key: node[key] for key in ("id", "kind", "project", "title", "cited_by")} for node in cited[:MOST_CITED]
        ],
    }
    return {"nodes": list(nodes.values()), "edges": edges, "dangling": dangling, "stats": stats}


def note(conn: sqlite3.Connection, note_id: int) -> dict[str, Any] | None:
    row = conn.execute("select rowid, kind, content from notes where rowid=?", (note_id,)).fetchone()
    return {"id": row[0], "kind": row[1], "content": row[2]} if row else None


def stats(project: str | None = None, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """build() stats alone, for an agent tidying the brain without a browser."""
    config = config or default_config()
    if not config.brain_path.exists():
        return {"warning": "brain is empty; store notes with brain_remember"}
    conn = connect_readonly(config.brain_path)
    try:
        return build(conn, project=project)["stats"]
    finally:
        conn.close()


def _title(content: str) -> str:
    lines = content.strip().splitlines()
    title = lines[0].strip() if lines else ""
    return title if len(title) <= TITLE_CHARS else title[: TITLE_CHARS - 1] + "…"
