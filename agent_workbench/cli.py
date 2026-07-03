from __future__ import annotations

import argparse
from pathlib import Path

from .code_index import brief_work_item, code_search, codebase_overview, rebuild_index, refresh_index
from .config import WorkbenchConfig, default_config
from .knowledge import brief_task, context_for_path, find_service_context, search_knowledge
from .mcp_server import serve
from .scanners import doctor_report, format_report, mcp_health, report_json
from .util import dump_json
from .work_sources import external_source_instructions, work_mcp_bridge, work_sources_status


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
    index.add_argument("roots", nargs="*", help="Optional roots to index; defaults to repo and Projects")
    index.add_argument("--json", action="store_true")

    refresh = sub.add_parser("refresh-index", help="Incrementally refresh local code/product index")
    refresh.add_argument("roots", nargs="*", help="Optional roots to refresh; defaults to repo and Projects")
    refresh.add_argument("--json", action="store_true")

    code = sub.add_parser("code-search", help="Search indexed code/product context")
    code.add_argument("query")
    code.add_argument("--limit", type=int, default=20)
    code.add_argument("--json", action="store_true")

    overview = sub.add_parser("overview", help="Show indexed codebase overview")
    overview.add_argument("target", nargs="?")
    overview.add_argument("--json", action="store_true")

    work = sub.add_parser("work-brief", help="Build local + external-source query brief for a work item")
    work.add_argument("query")
    work.add_argument("--json", action="store_true")

    sources = sub.add_parser("work-sources", help="Show configured Jira/Slack/Google work MCP sources")
    sources.add_argument("--json", action="store_true")

    bridge = sub.add_parser("work-bridge", help="Show work-mcp bridge status and external MCP call plan")
    bridge.add_argument("query")
    bridge.add_argument("--json", action="store_true")

    external = sub.add_parser("external-plan", help="Show recommended Jira/Slack/Google MCP calls for a query")
    external.add_argument("query")
    external.add_argument("--json", action="store_true")

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
    elif args.command == "code-search":
        report = code_search(args.query, config, args.limit)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "overview":
        report = codebase_overview(args.target, config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "work-brief":
        report = brief_work_item(args.query, config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "work-sources":
        report = work_sources_status(config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "work-bridge":
        report = work_mcp_bridge(args.query, config)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "external-plan":
        report = external_source_instructions(args.query)
        print(dump_json(report) if args.json else dump_json(report))
    elif args.command == "mcp-server":
        return serve()
    return 0


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
    lines = [f"Brief: {report['query']}", report["summary"]]
    if report.get("likely_repos"):
        lines.append("")
        lines.append("Likely repos:")
        lines.extend(f"- {repo}" for repo in report["likely_repos"])
    if report.get("local_hits"):
        lines.append("")
        lines.append("Local hits:")
        for hit in report["local_hits"][:10]:
            lines.append(f"- {hit['path']}:{hit['line']} {hit['snippet']}")
    lines.append("")
    lines.append("Next checks:")
    lines.extend(f"- {item}" for item in report["next_checks"])
    return "\n".join(lines)
