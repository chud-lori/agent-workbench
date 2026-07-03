from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .config import WorkbenchConfig, default_config
from .util import iter_files, read_text_limited


CODE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".java",
    ".kt",
    ".swift",
    ".rb",
    ".php",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
}

DOC_NAMES = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "SKILL.md",
    "CODEX_HANDOFF.md",
    "COMMANDS.md",
    "adr.md",
    "finanops.md",
}

PACKAGE_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "Dockerfile",
}


def _resolve_roots(config: WorkbenchConfig, roots: list[str] | None) -> list[Path]:
    if roots:
        return [Path(item).expanduser() for item in roots]
    return list(config.index_roots)


def rebuild_index(config: WorkbenchConfig | None = None, roots: list[str] | None = None) -> dict[str, Any]:
    config = config or default_config()
    root_paths = _resolve_roots(config, roots)
    config.workbench_home.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.index_path)
    try:
        _init_db(conn)
        conn.execute("delete from documents")
        conn.execute("delete from repos")
        scanned = 0
        included = 0
        for repo in _repo_roots(root_paths):
            repo_info = _repo_info(repo)
            conn.execute(
                "insert into repos(path,name,language,package_files,updated_at) values(?,?,?,?,?)",
                (
                    str(repo),
                    repo.name,
                    repo_info["language"],
                    json.dumps(repo_info["package_files"]),
                    int(time.time()),
                ),
            )
            for file_path in _indexable_files(repo, config):
                scanned += 1
                try:
                    text = read_text_limited(file_path, config.max_text_bytes)
                except OSError:
                    continue
                if not text.strip():
                    continue
                rel = str(file_path.relative_to(repo))
                conn.execute(
                    """
                    insert into documents(repo_path,path,title,kind,content,sha256,mtime,size)
                    values(?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(repo),
                        rel,
                        _title(text, file_path),
                        _kind(file_path),
                        text,
                        hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
                        int(file_path.stat().st_mtime),
                        file_path.stat().st_size,
                    ),
                )
                included += 1
        conn.commit()
        return {"index_path": str(config.index_path), "repos": len(_repo_roots(root_paths)), "files_scanned": scanned, "files_indexed": included}
    finally:
        conn.close()


def refresh_index(config: WorkbenchConfig | None = None, roots: list[str] | None = None) -> dict[str, Any]:
    config = config or default_config()
    root_paths = _resolve_roots(config, roots)
    config.workbench_home.mkdir(parents=True, exist_ok=True)
    repos = _repo_roots(root_paths)
    conn = sqlite3.connect(config.index_path)
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        scanned = 0
        inserted = 0
        updated = 0
        deleted = 0
        skipped = 0
        for repo in repos:
            repo_info = _repo_info(repo)
            conn.execute(
                """
                insert into repos(path,name,language,package_files,updated_at) values(?,?,?,?,?)
                on conflict(path) do update set
                    name=excluded.name,
                    language=excluded.language,
                    package_files=excluded.package_files,
                    updated_at=excluded.updated_at
                """,
                (
                    str(repo),
                    repo.name,
                    repo_info["language"],
                    json.dumps(repo_info["package_files"]),
                    int(time.time()),
                ),
            )
            seen = set()
            existing = {
                row["path"]: dict(row)
                for row in conn.execute(
                    "select path,sha256,mtime,size from documents where repo_path=?",
                    (str(repo),),
                )
            }
            for file_path in _indexable_files(repo, config):
                scanned += 1
                rel = str(file_path.relative_to(repo))
                seen.add(rel)
                try:
                    stat = file_path.stat()
                    text = read_text_limited(file_path, config.max_text_bytes)
                except OSError:
                    continue
                if not text.strip():
                    continue
                sha = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
                previous = existing.get(rel)
                if previous and previous["sha256"] == sha and previous["mtime"] == int(stat.st_mtime) and previous["size"] == stat.st_size:
                    skipped += 1
                    continue
                conn.execute("delete from documents where repo_path=? and path=?", (str(repo), rel))
                conn.execute(
                    """
                    insert into documents(repo_path,path,title,kind,content,sha256,mtime,size)
                    values(?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(repo),
                        rel,
                        _title(text, file_path),
                        _kind(file_path),
                        text,
                        sha,
                        int(stat.st_mtime),
                        stat.st_size,
                    ),
                )
                if previous:
                    updated += 1
                else:
                    inserted += 1
            for rel in set(existing) - seen:
                conn.execute("delete from documents where repo_path=? and path=?", (str(repo), rel))
                deleted += 1
        conn.commit()
        return {
            "index_path": str(config.index_path),
            "repos": len(repos),
            "files_scanned": scanned,
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "skipped_unchanged": skipped,
        }
    finally:
        conn.close()


def code_search(query: str, config: WorkbenchConfig | None = None, limit: int = 20) -> dict[str, Any]:
    config = config or default_config()
    if not config.index_path.exists():
        return {"query": query, "hits": [], "warning": "index does not exist; run index first"}
    conn = sqlite3.connect(config.index_path)
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        fts_query = _fts_query(query)
        rows = conn.execute(
            """
            select repo_path, path, title, kind, snippet(documents, 4, '[', ']', ' ... ', 12) as snippet
            from documents
            where documents match ?
            order by bm25(documents)
            limit ?
            """,
            (fts_query, limit),
        ).fetchall()
        result = {"query": query, "hits": [dict(row) for row in rows]}
        status = index_status(config)
        if status.get("warning"):
            result["warning"] = status["warning"]
        return result
    except sqlite3.OperationalError:
        rows = conn.execute(
            """
            select repo_path, path, title, kind, substr(content, 1, 300) as snippet
            from documents
            where lower(content) like ?
            limit ?
            """,
            (f"%{query.lower()}%", limit),
        ).fetchall()
        return {"query": query, "hits": [dict(row) for row in rows], "fallback": "like"}
    finally:
        conn.close()


def codebase_overview(target: str | None = None, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    if not config.index_path.exists():
        return {"repos": [], "warning": "index does not exist; run index first"}
    conn = sqlite3.connect(config.index_path)
    conn.row_factory = sqlite3.Row
    try:
        if target:
            rows = conn.execute(
                "select * from repos where lower(name) like ? or lower(path) like ? order by name limit 20",
                (f"%{target.lower()}%", f"%{target.lower()}%"),
            ).fetchall()
        else:
            rows = conn.execute("select * from repos order by name limit 80").fetchall()
        repos = []
        for row in rows:
            repo_path = row["path"]
            docs = conn.execute(
                "select path,title,kind from documents where repo_path=? and kind in ('doc','agent-doc','package') order by kind,path limit 20",
                (repo_path,),
            ).fetchall()
            repos.append(
                {
                    "path": repo_path,
                    "name": row["name"],
                    "language": row["language"],
                    "package_files": json.loads(row["package_files"] or "[]"),
                    "docs": [dict(doc) for doc in docs],
                }
            )
        return {"repos": repos}
    finally:
        conn.close()


def index_status(config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    if not config.index_path.exists():
        return {"exists": False, "warning": "index does not exist; run rebuild_code_index first"}
    conn = sqlite3.connect(config.index_path)
    try:
        _init_db(conn)
        repos = conn.execute("select count(*) from repos").fetchone()[0]
        documents = conn.execute("select count(*) from documents").fetchone()[0]
        last_updated = conn.execute("select max(updated_at) from repos").fetchone()[0]
        age_hours = round((time.time() - last_updated) / 3600, 1) if last_updated else None
        status: dict[str, Any] = {
            "exists": True,
            "index_path": str(config.index_path),
            "repos": repos,
            "documents": documents,
            "age_hours": age_hours,
        }
        if age_hours is not None and age_hours > 24:
            status["warning"] = f"index is {age_hours} hours old; run refresh_code_index"
        return status
    finally:
        conn.close()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists repos(
            path text primary key,
            name text not null,
            language text,
            package_files text not null,
            updated_at integer not null
        )
        """
    )
    conn.execute(
        """
        create virtual table if not exists documents using fts5(
            repo_path unindexed,
            path,
            title,
            kind,
            content,
            sha256 unindexed,
            mtime unindexed,
            size unindexed
        )
        """
    )


def _repo_roots(roots: Iterable[Path]) -> list[Path]:
    repos: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_dir() and any((root / marker).exists() for marker in [".git", "README.md", "pyproject.toml", "package.json", "go.mod"]):
            repos.append(root)
            continue
        for child in root.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            if any((child / marker).exists() for marker in [".git", "README.md", "pyproject.toml", "package.json", "go.mod"]):
                repos.append(child)
    return sorted(set(repos))


def _indexable_files(repo: Path, config: WorkbenchConfig) -> Iterable[Path]:
    names = DOC_NAMES | PACKAGE_FILES
    suffixes = CODE_SUFFIXES | {".md"}
    for path in iter_files([repo], max_depth=5, names=names, suffixes=suffixes):
        try:
            if path.stat().st_size > config.max_text_bytes:
                continue
        except OSError:
            continue
        yield path


def _repo_info(repo: Path) -> dict[str, Any]:
    packages = [name for name in PACKAGE_FILES if (repo / name).exists()]
    suffix_counts: dict[str, int] = {}
    for current, dirs, files in os.walk(repo):
        current_path = Path(current)
        if len(current_path.relative_to(repo).parts) > 3:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", "__pycache__"}]
        for file_name in files:
            suffix = Path(file_name).suffix.lower()
            if suffix in CODE_SUFFIXES:
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    language = _language_from_suffix(max(suffix_counts, key=suffix_counts.get)) if suffix_counts else None
    return {"package_files": packages, "language": language}


def _language_from_suffix(suffix: str) -> str:
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript/react",
        ".jsx": "javascript/react",
        ".go": "go",
        ".java": "java",
        ".kt": "kotlin",
        ".swift": "swift",
        ".rb": "ruby",
        ".php": "php",
    }.get(suffix, suffix.lstrip("."))


def _title(text: str, path: Path) -> str:
    for line in text.splitlines()[:20]:
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.name


def _kind(path: Path) -> str:
    if path.name in {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "SKILL.md"}:
        return "agent-doc"
    if path.name in PACKAGE_FILES:
        return "package"
    if path.suffix.lower() == ".md":
        return "doc"
    return "code"


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_/-]{2,}", query)
    return " AND ".join(f'"{term}"' for term in terms) if terms else '""'
