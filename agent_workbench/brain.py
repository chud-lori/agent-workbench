from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig, default_config


VALID_KINDS = {"decision", "fact", "gotcha", "preference", "todo", "note", "reference"}

# Tokens that look like an issue/entity key (JIRA-123, GH-42, INC-9001...).
# One grouping heuristic among several — the brain is domain-agnostic.
_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d{1,8}\b")


def remember(
    content: str,
    kind: str = "note",
    project: str | None = None,
    tags: list[str] | None = None,
    config: WorkbenchConfig | None = None,
    *,
    supersedes: list[int] | None = None,
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
        similar = _find_similar(conn, content, project, tags)
        cursor = conn.execute(
            "insert into notes(content,kind,project,tags,created_at) values(?,?,?,?,?)",
            (content, kind, project, " ".join(tags or []), int(time.time())),
        )
        new_id = cursor.lastrowid
        superseded: list[int] = []
        for old_id in supersedes or []:
            if old_id == new_id:
                continue
            updated = conn.execute(
                "update notes set superseded_by=? where rowid=? and superseded_by is null",
                (new_id, old_id),
            )
            if updated.rowcount:
                superseded.append(old_id)
        conn.commit()
        result: dict[str, Any] = {"id": new_id, "stored": True, "kind": kind, "project": project}
        if superseded:
            result["superseded"] = superseded
        similar = [note for note in similar if note["id"] != new_id and note["id"] not in superseded]
        if similar:
            result["similar_notes"] = similar
            result["hint"] = (
                "Similar notes already exist. If this note corrects or extends one of them, "
                "prefer brain_amend(id, ...) or re-store with supersedes=[ids] so recall does not "
                "surface stale contradictions."
            )
        return result
    finally:
        conn.close()


def amend(
    note_id: int,
    content: str,
    mode: str = "append",
    config: WorkbenchConfig | None = None,
) -> dict[str, Any]:
    """Update a note in place. append (default) adds a dated addendum; replace rewrites the body."""
    config = config or default_config()
    content = content.strip()
    if not content:
        return {"id": note_id, "amended": False, "error": "content is empty"}
    if mode not in {"append", "replace"}:
        return {"id": note_id, "amended": False, "error": "mode must be 'append' or 'replace'"}
    if not config.brain_path.exists():
        return {"id": note_id, "amended": False, "warning": "brain is empty"}
    conn = _connect(config)
    try:
        row = conn.execute("select content from notes where rowid=?", (note_id,)).fetchone()
        if not row:
            return {"id": note_id, "amended": False, "warning": "note not found"}
        if mode == "append":
            stamp = time.strftime("%Y-%m-%d", time.localtime())
            new_content = f"{row[0].rstrip()}\n\n[AMENDED {stamp}] {content}"
        else:
            new_content = content
        conn.execute("update notes set content=? where rowid=?", (new_content, note_id))
        conn.commit()
        return {"id": note_id, "amended": True, "mode": mode}
    finally:
        conn.close()


def recall(
    query: str | None = None,
    project: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    include_resolved: bool = False,
    config: WorkbenchConfig | None = None,
    *,
    thread: str | None = None,
    include_superseded: bool = False,
) -> dict[str, Any]:
    config = config or default_config()
    if not config.brain_path.exists():
        return {"query": query, "notes": [], "warning": "brain is empty; store notes with brain_remember"}
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        if thread:
            return _thread_digest(conn, thread, limit)
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
        if not include_resolved:
            clauses.append("resolved_at is null")
        if not include_superseded:
            clauses.append("superseded_by is null")
        where = f"where {' and '.join(clauses)}" if clauses else ""
        order = "order by bm25(notes)" if query and query.strip() else "order by created_at desc, rowid desc"
        rows = conn.execute(
            f"select rowid as id, content, kind, project, tags, created_at, resolved_at, superseded_by "
            f"from notes {where} {order} limit ?",
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


def _thread_digest(conn: sqlite3.Connection, thread: str, limit: int) -> dict[str, Any]:
    """Chronological digest of every note grouped by a tag/key/keyword.

    Generic by design: `thread` can be an issue key, a tag, a feature name —
    anything worth following as a storyline. Superseded notes collapse to stubs
    so the digest reads as current truth plus history markers.
    """
    token = thread.strip()
    rows = conn.execute(
        "select rowid as id, content, kind, project, tags, created_at, resolved_at, superseded_by "
        "from notes where notes match ? order by created_at asc, rowid asc limit ?",
        (f'"{token}"', max(limit, 50)),
    ).fetchall()
    token_lower = token.lower()
    active: list[dict[str, Any]] = []
    stubs: list[dict[str, Any]] = []
    for row in rows:
        note = _note_dict(row)
        tag_hit = any(token_lower == tag.lower() for tag in note["tags"])
        content_hit = token_lower in note["content"].lower()
        if not (tag_hit or content_hit):
            continue
        if note.get("superseded_by"):
            stubs.append(
                {
                    "id": note["id"],
                    "kind": note["kind"],
                    "created_at_iso": note["created_at_iso"],
                    "superseded_by": note["superseded_by"],
                }
            )
        else:
            active.append(note)
    return {
        "thread": token,
        "notes": active,
        "superseded_stubs": stubs,
        "hint": "notes are chronological (oldest first); stubs were superseded — fetch by id only for history",
    }


def _find_similar(
    conn: sqlite3.Connection,
    content: str,
    project: str | None,
    tags: list[str] | None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Best-effort near-duplicate detection at write time.

    Generic recipe: entity-like keys found in the content, the supplied tags,
    and the longest distinctive words form an FTS query; candidates then need
    real overlap (a shared key, >=2 shared tags, or heavy shared vocabulary)
    before they are reported.
    """
    keys = set(_KEY_PATTERN.findall(content))
    tag_set = {tag.lower() for tag in (tags or [])}
    words = [term.lower() for term in re.findall(r"[A-Za-z0-9_/-]{5,}", content)]
    distinctive = list(dict.fromkeys(list(keys) + list(tags or []) + words[:12]))
    if not distinctive:
        return []
    query = " OR ".join(f'"{term}"' for term in distinctive[:20])
    try:
        rows = conn.execute(
            "select rowid as id, content, kind, project, tags from notes "
            "where notes match ? and superseded_by is null order by bm25(notes) limit 8",
            (query,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    content_terms = set(words)
    similar: list[dict[str, Any]] = []
    for row in rows:
        row_id, row_content, row_kind, row_project, row_tags = row
        if project and (row_project or "") != project:
            continue
        row_tag_set = {tag.lower() for tag in (row_tags or "").split()}
        row_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_/-]{5,}", row_content)}
        shared_keys = keys & set(_KEY_PATTERN.findall(row_content)) | (keys & row_tag_set)
        shared_tags = tag_set & row_tag_set
        shared_terms = content_terms & row_terms
        if shared_keys or len(shared_tags) >= 2 or len(shared_terms) >= 10:
            preview = " ".join(row_content.split())[:140]
            similar.append({"id": row_id, "kind": row_kind, "tags": sorted(row_tag_set), "preview": preview})
        if len(similar) >= limit:
            break
    return similar


def promote(note_id: int, target: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """Promote a personal note into a shared reference file (team playbook).

    The brain is per-person; teams share knowledge through git-versioned
    markdown (a skill's references/, a runbook repo, any playbook). Promote
    appends the note there in a readable block and stamps the note itself so
    it is never promoted twice. The target is any markdown path — the
    mechanism carries no org assumptions.
    """
    config = config or default_config()
    if not config.brain_path.exists():
        return {"id": note_id, "promoted": False, "warning": "brain is empty"}
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select rowid as id, content, kind, project, tags, created_at, resolved_at, superseded_by "
            "from notes where rowid=?",
            (note_id,),
        ).fetchone()
        if not row:
            return {"id": note_id, "promoted": False, "warning": "note not found"}
        note = _note_dict(row)
        if f"[PROMOTED " in note["content"]:
            return {"id": note_id, "promoted": False, "warning": "note already promoted (see its content stamp)"}
        target_path = Path(target).expanduser()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d", time.localtime())
        tags = " ".join(note["tags"])
        block = (
            f"\n## {note['kind']}#{note['id']}"
            + (f" ({note['project']})" if note.get("project") else "")
            + f" — promoted {stamp}\n"
            + (f"tags: {tags}\n\n" if tags else "\n")
            + note["content"].strip()
            + "\n"
        )
        with target_path.open("a", encoding="utf-8") as fh:
            fh.write(block)
        conn.execute(
            "update notes set content=? where rowid=?",
            (f"{note['content'].rstrip()}\n\n[PROMOTED {stamp}] to {target_path}", note_id),
        )
        conn.commit()
        return {"id": note_id, "promoted": True, "target": str(target_path)}
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


def resolve(note_id: int, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    if not config.brain_path.exists():
        return {"id": note_id, "resolved": False, "warning": "brain is empty"}
    conn = _connect(config)
    try:
        cursor = conn.execute("update notes set resolved_at=? where rowid=?", (int(time.time()), note_id))
        conn.commit()
        return {"id": note_id, "resolved": cursor.rowcount > 0}
    finally:
        conn.close()


def export(path: str | None = None, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    lines = ["# Brain export", ""]
    notes: list[dict[str, Any]] = []
    if config.brain_path.exists():
        conn = _connect(config)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "select rowid as id, content, kind, project, tags, created_at, resolved_at, superseded_by "
                "from notes order by coalesce(project,''), created_at, rowid"
            ).fetchall()
            notes = [_note_dict(row) for row in rows]
        finally:
            conn.close()
    if not notes:
        lines.append("No notes stored.")
    current_project: str | None = None
    for note in notes:
        heading = note["project"] or "(no project)"
        if heading != current_project:
            current_project = heading
            lines.extend([f"## {heading}", ""])
        markers = []
        if note.get("resolved_at"):
            markers.append("resolved")
        if note.get("superseded_by"):
            markers.append(f"superseded by #{note['superseded_by']}")
        marker = f" ({', '.join(markers)})" if markers else ""
        tags = " ".join(note["tags"])
        lines.append(f"- [{note['kind']}#{note['id']}]{marker} tags: {tags or '-'} created: {note['created_at_iso']}")
        lines.append(f"  {note['content']}")
        lines.append("")
    markdown = "\n".join(lines).rstrip() + "\n"
    result: dict[str, Any] = {"count": len(notes), "markdown": markdown}
    if path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        result["path"] = str(target)
    return result


NOTES_SCHEMA = """
        create virtual table if not exists {name} using fts5(
            content,
            kind,
            project,
            tags,
            created_at unindexed,
            resolved_at unindexed,
            superseded_by unindexed,
            tokenize='porter'
        )
"""


def _connect(config: WorkbenchConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(config.brain_path)
    existing = conn.execute("select sql from sqlite_master where name='notes'").fetchone()
    if existing and (
        "porter" not in existing[0].lower()
        or "resolved_at" not in existing[0].lower()
        or "superseded_by" not in existing[0].lower()
    ):
        _migrate(conn)
    else:
        conn.execute(NOTES_SCHEMA.format(name="notes"))
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    columns = [row[1] for row in conn.execute("pragma table_info(notes)")]
    resolved_source = "resolved_at" if "resolved_at" in columns else "null"
    superseded_source = "superseded_by" if "superseded_by" in columns else "null"
    try:
        conn.execute("begin")
        conn.execute("drop table if exists notes_migrated")
        conn.execute(NOTES_SCHEMA.format(name="notes_migrated"))
        conn.execute(
            "insert into notes_migrated(rowid, content, kind, project, tags, created_at, resolved_at, superseded_by) "
            f"select rowid, content, kind, project, tags, created_at, {resolved_source}, {superseded_source} from notes"
        )
        conn.execute("drop table notes")
        conn.execute("alter table notes_migrated rename to notes")
        conn.execute("commit")
    except Exception:
        conn.execute("rollback")
        raise


def _note_dict(row: sqlite3.Row) -> dict[str, Any]:
    note = dict(row)
    note["tags"] = row["tags"].split() if row["tags"] else []
    note["created_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(row["created_at"]))
    if note.get("resolved_at"):
        note["resolved_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(note["resolved_at"]))
    if not note.get("superseded_by"):
        note.pop("superseded_by", None)
    return note


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_/-]{2,}", query)
    return " OR ".join(f'"{term}"' for term in terms) if terms else '""'
