from __future__ import annotations

import argparse
from pathlib import Path

from .brain import amend, export, forget, recall, remember, resolve
from .code_index import code_search, codebase_overview, index_status, rebuild_index, refresh_index
from .config import WorkbenchConfig, default_config
from .knowledge import brief_task, context_for_path, find_service_context, search_knowledge
from .mcp_server import serve
from .repo_state import repo_state
from .scanners import doctor_report, format_report, mcp_health, report_json
from .util import dump_json
from .work_sources import work_sources_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-workbench")
    parser.add_argument("--repo-root", default=str(default_config().repo_root))
    parser.add_argument("--projects-root", default=str(default_config().projects_root))
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Run local setup diagnostics")
    doctor.add_argument("--all", action="store_true", help="Kept for readability; doctor scans all MVP rules by default")
    doctor.add_argument("--json", action="store_true")

    mcp = sub.add_parser("mcp-check", help="Check MCP config health")
    mcp.add_argument("--json", action="store_true")

    context = sub.add_parser("context", help="Summarize project/repo context")
    context.add_argument("path")
    context.add_argument("--json", action="store_true")

    search = sub.add_parser("search", help="Search local agent knowledge")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=None)
    search.add_argument("--json", action="store_true")

    brief = sub.add_parser("brief", help="Build a deterministic task brief")
    brief.add_argument("query")
    brief.add_argument("--json", action="store_true")

    service = sub.add_parser("service", help="Find service/repo context")
    service.add_argument("name")
    service.add_argument("--json", action="store_true")

    index = sub.add_parser("index", help="Rebuild local code/product index")
    index.add_argument("roots", nargs="*", help="Optional roots to index; defaults to ~/repo (or AGENT_WORKBENCH_INDEX_ROOTS)")
    index.add_argument("--json", action="store_true")

    refresh = sub.add_parser("refresh-index", help="Incrementally refresh local code/product index")
    refresh.add_argument("roots", nargs="*", help="Optional roots to refresh; defaults to ~/repo (or AGENT_WORKBENCH_INDEX_ROOTS)")
    refresh.add_argument("--json", action="store_true")

    status = sub.add_parser("index-status", help="Show code index freshness")
    status.add_argument("--json", action="store_true")

    code = sub.add_parser("code-search", help="Search indexed code/product context")
    code.add_argument("query")
    code.add_argument("--limit", type=int, default=20)
    code.add_argument("--json", action="store_true")

    overview = sub.add_parser("overview", help="Show indexed codebase overview")
    overview.add_argument("target", nargs="?")
    overview.add_argument("--json", action="store_true")

    sources = sub.add_parser("work-sources", help="Show configured Jira/Slack/Google work MCP sources")
    sources.add_argument("--json", action="store_true")

    remember_cmd = sub.add_parser("remember", help="Store a durable brain note")
    remember_cmd.add_argument("content")
    remember_cmd.add_argument(
        "--kind", default="note", choices=["decision", "fact", "gotcha", "preference", "todo", "note", "reference"]
    )
    remember_cmd.add_argument("--project", default=None)
    remember_cmd.add_argument("--tags", nargs="*", default=None)
    remember_cmd.add_argument("--supersedes", nargs="*", type=int, default=None, help="Note ids this note replaces")

    amend_cmd = sub.add_parser("amend", help="Amend an existing brain note in place")
    amend_cmd.add_argument("id", type=int)
    amend_cmd.add_argument("content")
    amend_cmd.add_argument("--replace", action="store_true", help="Rewrite the body instead of appending an addendum")

    recall_cmd = sub.add_parser("recall", help="Search brain notes; omit query for recent notes")
    recall_cmd.add_argument("query", nargs="?", default=None)
    recall_cmd.add_argument("--project", default=None)
    recall_cmd.add_argument("--kind", default=None)
    recall_cmd.add_argument("--limit", type=int, default=20)
    recall_cmd.add_argument("--all", action="store_true", help="Include resolved notes")
    recall_cmd.add_argument("--superseded", action="store_true", help="Include superseded notes")
    recall_cmd.add_argument("--thread", default=None, help="Digest all notes on a tag/key/keyword chronologically")

    recall_brief_cmd = sub.add_parser(
        "recall-brief", help="Compact top-hit note lines for a prompt (used by the UserPromptSubmit hook)"
    )
    recall_brief_cmd.add_argument("prompt")

    repo_state_cmd = sub.add_parser("repo-state", help="Show a repo's branch/divergence vs origin/main")
    repo_state_cmd.add_argument("repo")

    forget_cmd = sub.add_parser("forget", help="Delete a brain note by id")
    forget_cmd.add_argument("id", type=int)

    resolve_cmd = sub.add_parser("resolve", help="Mark a brain note resolved by id")
    resolve_cmd.add_argument("id", type=int)

    export_cmd = sub.add_parser("export", help="Export all brain notes as markdown")
    export_cmd.add_argument("--out", default=None, help="Optional file path; prints markdown to stdout when omitted")

    sub.add_parser("mcp-server", help="Run stdio MCP server")

    args = parser.parse_args(argv)
    config = WorkbenchConfig(repo_root=Path(args.repo_root).expanduser(), projects_root=Path(args.projects_root).expanduser())

    if args.command == "doctor":
        report = doctor_report(config)
        print(report_json(report) if args.json else format_report(report))
    elif args.command == "mcp-check":
        report = mcp_health(config)
        print(dump_json(report) if args.json else format_report({"summary": {}, "findings": report["findings"]}))
    elif args.command == "context":
        report = context_for_path(args.path, config)
        print(dump_json(report) if args.json else _format_context(report))
    elif args.command == "search":
        report = search_knowledge(args.query, config, args.limit)
        print(dump_json(report) if args.json else _format_search(report))
    elif args.command == "brief":
        report = brief_task(args.query, config)
        print(dump_json(report) if args.json else _format_brief(report))
    elif args.command == "service":
        report = find_service_context(args.name, config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "index":
        report = rebuild_index(config, args.roots or None)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "refresh-index":
        report = refresh_index(config, args.roots or None)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "index-status":
        report = index_status(config)
        print(dump_json(report))
    elif args.command == "code-search":
        report = code_search(args.query, config, args.limit)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "overview":
        report = codebase_overview(args.target, config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "work-sources":
        report = work_sources_status(config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "remember":
        print(dump_json(remember(args.content, args.kind, args.project, args.tags, config, supersedes=args.supersedes)))
    elif args.command == "amend":
        print(dump_json(amend(args.id, args.content, "replace" if args.replace else "append", config)))
    elif args.command == "recall":
        print(
            dump_json(
                recall(
                    args.query,
                    args.project,
                    args.kind,
                    args.limit,
                    args.all,
                    config,
                    thread=args.thread,
                    include_superseded=args.superseded,
                )
            )
        )
    elif args.command == "recall-brief":
        brief_text = _recall_brief(args.prompt, config)
        if brief_text:
            print(brief_text)
    elif args.command == "repo-state":
        print(dump_json(repo_state(args.repo, config)))
    elif args.command == "forget":
        print(dump_json(forget(args.id, config)))
    elif args.command == "resolve":
        print(dump_json(resolve(args.id, config)))
    elif args.command == "export":
        report = export(args.out, config)
        print(dump_json(report) if args.out else report["markdown"])
    elif args.command == "mcp-server":
        return serve()
    return 0


def _recall_brief(prompt: str, config: WorkbenchConfig) -> str:
    """Top brain hits for a user prompt, as compact one-liners.

    Threshold-gated so trivial prompts ("yes", "go") inject nothing: the prompt
    must carry at least two distinctive terms. Full note bodies stay pull-based
    via brain_recall — this only surfaces ids and hooks.
    """
    import re as _re

    prompt = prompt.strip()[:400]
    distinctive = _re.findall(r"[A-Za-z0-9_/-]{4,}", prompt)
    if len(set(term.lower() for term in distinctive)) < 2:
        return ""
    report = recall(query=prompt, limit=5, config=config)
    notes = report.get("notes") or []
    if not notes:
        return ""
    lines = ["Possibly relevant brain notes (brain_recall <id/query> for full text):"]
    for note in notes:
        content = " ".join(str(note.get("content", "")).split())
        if len(content) > 150:
            content = content[:150].rstrip() + "..."
        project = note.get("project") or "-"
        lines.append(f"- [{note.get('kind', 'note')}#{note.get('id', '?')}] ({project}) {content}")
    return "\n".join(lines)


def _format_context(report: dict) -> str:
    lines = [f"Context: {report['path']}", f"Exists: {report['exists']}"]
    if report.get("warnings"):
        lines.append("Warnings: " + "; ".join(report["warnings"]))
    if report.get("docs"):
        lines.append("")
        lines.append("Docs:")
        for doc in report["docs"]:
            lines.append(f"- {doc['title']} ({doc['path']})")
    if report.get("commands"):
        lines.append("")
        lines.append("Commands:")
        for command in report["commands"]:
            lines.append(f"- {command['command']} ({command['source']})")
    return "\n".join(lines)


def _format_search(report: dict) -> str:
    lines = [f"Search: {report['query']}"]
    for hit in report.get("hits", []):
        lines.append(f"- score={hit['score']} {hit['path']}:{hit['line']} {hit['snippet']}")
    return "\n".join(lines)


def _format_brief(report: dict) -> str:
    lines = [f"Brief: {report['query']}"]
    if report.get("likely_repos"):
        lines.append("")
        lines.append("Likely repos:")
        lines.extend(f"- {repo}" for repo in report["likely_repos"])
    if report.get("brain_notes"):
        lines.append("")
        lines.append("Brain notes:")
        for note in report["brain_notes"]:
            lines.append(f"- [{note['kind']}#{note['id']}] {note['content'][:200]}")
    if report.get("code_hits"):
        lines.append("")
        lines.append("Code hits:")
        for hit in report["code_hits"][:10]:
            lines.append(f"- {hit['repo_path']}/{hit['path']} {hit['snippet'][:160]}")
    if report.get("doc_hits"):
        lines.append("")
        lines.append("Doc hits:")
        for hit in report["doc_hits"][:10]:
            lines.append(f"- {hit['path']}:{hit['line']} {hit['snippet'][:160]}")
    if report.get("commands"):
        lines.append("")
        lines.append("Commands:")
        for command in report["commands"][:10]:
            lines.append(f"- {command['command']}")
    for warning in report.get("warnings", []):
        lines.append("")
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)
