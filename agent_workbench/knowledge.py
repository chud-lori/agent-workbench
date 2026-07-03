from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig, default_config
from .util import iter_files, read_text_limited


KNOWLEDGE_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "SKILL.md",
    "README.md",
    "CODEX_HANDOFF.md",
    "COMMANDS.md",
    "copilot-instructions.md",
}


@dataclass
class SearchHit:
    path: str
    line: int
    score: int
    title: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def search_knowledge(query: str, config: WorkbenchConfig | None = None, limit: int | None = None) -> dict[str, Any]:
    config = config or default_config()
    limit = limit or config.max_search_results
    terms = _terms(query)
    if not terms:
        return {"query": query, "hits": []}
    hits: list[SearchHit] = []
    for path in iter_files([config.repo_root, config.projects_root], max_depth=5, names=KNOWLEDGE_NAMES, suffixes={".md"}):
        if path.stat().st_size > config.max_text_bytes:
            continue
        try:
            lines = read_text_limited(path, config.max_text_bytes).splitlines()
        except OSError:
            continue
        title = _title(lines, path)
        for line_number, line in enumerate(lines, start=1):
            line_lower = line.lower()
            score = sum(1 for term in terms if term in line_lower)
            if score:
                hits.append(SearchHit(str(path), line_number, score, title, line.strip()[:500]))
    hits.sort(key=lambda hit: (-hit.score, hit.path, hit.line))
    return {"query": query, "hits": [hit.to_dict() for hit in hits[:limit]]}


def context_for_path(path_text: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    path = Path(path_text).expanduser()
    if not path.exists():
        return {"path": str(path), "exists": False, "docs": [], "commands": [], "warnings": ["path does not exist"]}
    if path.is_file():
        root = path.parent
    else:
        root = path
    docs = []
    commands = []
    warnings = []
    for doc in iter_files([root], max_depth=3, names=KNOWLEDGE_NAMES):
        try:
            text = read_text_limited(doc, 128_000)
        except OSError:
            continue
        docs.append({"path": str(doc), "title": _title(text.splitlines(), doc)})
        commands.extend(_extract_commands(text, doc))
    if not docs:
        warnings.append("No common agent/project docs found.")
    return {
        "path": str(path),
        "exists": True,
        "docs": docs[:30],
        "commands": commands[:50],
        "warnings": warnings,
    }


def brief_task(query: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """One-call orchestrated brief: code index + agent docs + brain notes + repo commands."""
    config = config or default_config()
    from .brain import recall
    from .code_index import code_search, index_status

    code_hits = code_search(query, config, limit=15)
    doc_hits = search_knowledge(query, config, limit=15)
    memory = recall(query=query, limit=10, config=config)
    likely_repos = _merge_likely_repos(doc_hits["hits"], code_hits.get("hits", []), config)
    commands = []
    for repo in likely_repos[:2]:
        context = context_for_path(repo, config)
        commands.extend(context["commands"][:10])
    brief: dict[str, Any] = {
        "query": query,
        "likely_repos": likely_repos,
        "code_hits": code_hits.get("hits", []),
        "doc_hits": doc_hits["hits"],
        "brain_notes": memory.get("notes", []),
        "commands": commands[:20],
        "index_status": index_status(config),
    }
    if code_hits.get("warning"):
        brief["warnings"] = [code_hits["warning"]]
    return brief


def find_service_context(service_name: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    candidates = []
    for root in [config.repo_root, config.projects_root]:
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_dir() and service_name.lower() in child.name.lower():
                candidates.append(context_for_path(str(child), config))
    if not candidates:
        search = search_knowledge(service_name, config, limit=20)
        return {"service": service_name, "matches": [], "search_hits": search["hits"]}
    return {"service": service_name, "matches": candidates}


def _terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9_-]{2,}", query)]


def _title(lines: list[str], path: Path) -> str:
    for line in lines[:20]:
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.name


def _extract_commands(text: str, source: Path) -> list[dict[str, str]]:
    commands = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and stripped and not stripped.startswith("#"):
            if re.match(r"^(python|pytest|npm|yarn|pnpm|bun|go|cargo|make|docker|kubectl|gh|git)\b", stripped):
                commands.append({"source": str(source), "command": stripped})
    return commands


def _likely_repos(hits: list[dict[str, Any]], config: WorkbenchConfig) -> list[str]:
    counts: dict[str, int] = {}
    _count_doc_hits(hits, counts, config)
    return [repo for repo, _ in sorted(counts.items(), key=lambda item: -item[1])[:10]]


def _merge_likely_repos(
    doc_hits: list[dict[str, Any]],
    code_hits: list[dict[str, Any]],
    config: WorkbenchConfig,
) -> list[str]:
    counts: dict[str, int] = {}
    _count_doc_hits(doc_hits, counts, config)
    for hit in code_hits:
        repo = hit.get("repo_path")
        if repo:
            counts[repo] = counts.get(repo, 0) + 1
    return [repo for repo, _ in sorted(counts.items(), key=lambda item: -item[1])[:10]]


def _count_doc_hits(hits: list[dict[str, Any]], counts: dict[str, int], config: WorkbenchConfig) -> None:
    for hit in hits:
        path = Path(hit["path"])
        for root in [config.repo_root, config.projects_root]:
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if rel.parts:
                repo = str(root / rel.parts[0])
                counts[repo] = counts.get(repo, 0) + int(hit.get("score", 1))
