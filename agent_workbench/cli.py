from __future__ import annotations

import argparse
from pathlib import Path

from .activity import recent_activity
from .brain import amend, export, forget, promote, recall, remember, resolve
from .code_index import code_search, codebase_overview, index_status, rebuild_index, refresh_index
from .config import WorkbenchConfig, default_config
from .graph_server import export_html as export_graph, serve as serve_graph
from .knowledge import brief_task, context_for_path, find_service_context, search_knowledge
from .ledger import claim_path, register_session
from .mcp_server import serve
from .prompt_recall import pop_spawn_prompt, prompt_hits, stash_spawn_prompt
from .repo_state import repo_state
from .rules import context_view, remember_rule, rule_feedback, rules_in_force
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
    brief.add_argument("--session", default=None, help="This session's id; its own file claims are not reported")

    service = sub.add_parser("service", help="Find service/repo context")
    service.add_argument("name")
    service.add_argument("--json", action="store_true")

    index = sub.add_parser("index", help="Rebuild local code/product index")
    index.add_argument("roots", nargs="*", help="Optional roots to index; defaults to the configured index roots")
    index.add_argument("--json", action="store_true")

    refresh = sub.add_parser("refresh-index", help="Incrementally refresh local code/product index")
    refresh.add_argument("roots", nargs="*", help="Optional roots to refresh; defaults to the configured index roots")
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

    promote_cmd = sub.add_parser("promote", help="Promote a note into a shared markdown reference file")
    promote_cmd.add_argument("id", type=int)
    promote_cmd.add_argument("target", help="Markdown file to append the note to (team playbook/references)")

    recall_cmd = sub.add_parser("recall", help="Search brain notes; omit query for recent notes")
    recall_cmd.add_argument("query", nargs="?", default=None)
    recall_cmd.add_argument("--project", default=None)
    recall_cmd.add_argument("--kind", default=None)
    recall_cmd.add_argument("--limit", type=int, default=20)
    recall_cmd.add_argument("--all", action="store_true", help="Include resolved notes")
    recall_cmd.add_argument("--superseded", action="store_true", help="Include superseded notes")
    recall_cmd.add_argument("--thread", default=None, help="Digest all notes on a tag/key/keyword chronologically")
    recall_cmd.add_argument("--since", default=None, help="Only notes stored at/after: YYYY-MM-DD, 'yesterday', '7d'")
    recall_cmd.add_argument("--until", default=None, help="Only notes stored at/before (a bare date covers that whole day)")

    rule_cmd = sub.add_parser("rule", help="Store a contextual rule learned from a correction")
    rule_cmd.add_argument("statement")
    rule_cmd.add_argument("--scope", action="append", default=None, help="Context key type:value (repeatable); omit for global")
    rule_cmd.add_argument("--why", default=None)
    rule_cmd.add_argument("--example", default=None)
    rule_cmd.add_argument("--trigger", action="append", default=None, help="Word signalling the context (repeatable)")
    rule_cmd.add_argument("--source", default=None)

    rules_cmd = sub.add_parser("rules", help="Rules governing a context, most specific first")
    rules_cmd.add_argument("--context", action="append", default=None, help="Active context key type:value (repeatable)")
    rules_cmd.add_argument("--prompt", default=None, help="Current request, matched against rule triggers")
    rules_cmd.add_argument("--project", default=None, help="Repo dir name; adds repo:<name>")
    rules_cmd.add_argument("--limit", type=int, default=10)

    rule_feedback_cmd = sub.add_parser("rule-feedback", help="Record that a rule failed, or retire it")
    rule_feedback_cmd.add_argument("id", type=int)
    rule_feedback_cmd.add_argument("outcome", choices=["corrected", "retire"])

    rule_context_cmd = sub.add_parser("rule-context", help="Rules and health flags for one context key")
    rule_context_cmd.add_argument("key")

    sub.add_parser(
        "rules-brief", help="Compact lines for the rules whose scope matches this repo (used by the UserPromptSubmit hook)"
    )

    recall_brief_cmd = sub.add_parser(
        "recall-brief", help="Compact top-hit note lines for a prompt (used by the UserPromptSubmit hook)"
    )
    recall_brief_cmd.add_argument("prompt")
    recall_brief_cmd.add_argument("--session", default=None, help="Hook session_id; a note is not repeated within it")

    session_cmd = sub.add_parser(
        "session-register", help="Record a session's repo and branch in the ledger (used by the SessionStart hook)"
    )
    session_cmd.add_argument("session_id")
    session_cmd.add_argument("--cwd", default=".", help="Directory whose repo and branch to record")
    claim_cmd = sub.add_parser(
        "claim-edit", help="Claim the file in a PostToolUse edit payload on stdin for a session (used by the claim hook)"
    )
    claim_cmd.add_argument("session_id")
    sub.add_parser(
        "subagent-brief", help="Read a PreToolUse(Agent) or SubagentStart hook payload on stdin (used by the subagent hook)"
    )

    repo_state_cmd = sub.add_parser("repo-state", help="Show a repo's branch/divergence vs origin/main")
    repo_state_cmd.add_argument("repo")

    activity_cmd = sub.add_parser("activity", help="Commits you made in a window, across every local repo")
    activity_cmd.add_argument("--since", default="yesterday", help="YYYY-MM-DD, ISO, 'today', 'yesterday', or 'Nd'/'Nh'/'Nw' (default: yesterday)")
    activity_cmd.add_argument("--until", default=None, help="Inclusive end; a bare date covers that whole day")
    activity_cmd.add_argument("--author", default=None, help="Author name/email (default: each repo's git config user.email)")
    activity_cmd.add_argument("--root", action="append", dest="roots", default=None, help="Override scanned dirs (repeatable)")
    activity_cmd.add_argument("--json", action="store_true")

    forget_cmd = sub.add_parser("forget", help="Delete a brain note by id")
    forget_cmd.add_argument("id", type=int)

    resolve_cmd = sub.add_parser("resolve", help="Mark a brain note resolved by id")
    resolve_cmd.add_argument("id", type=int)

    export_cmd = sub.add_parser("export", help="Export all brain notes as markdown")
    export_cmd.add_argument("--out", default=None, help="Optional file path; prints markdown to stdout when omitted")

    graph_cmd = sub.add_parser("graph", help="Serve a read-only graph of the brain on 127.0.0.1")
    graph_cmd.add_argument("--port", type=int, default=0, help="Port on 127.0.0.1 (default: any free port)")
    graph_cmd.add_argument("--no-open", action="store_true", help="Print the URL without opening a browser")
    graph_cmd.add_argument("--export", default=None, metavar="FILE", help="Write one self-contained HTML file instead of serving")

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
        report = brief_task(args.query, config, args.session)
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
    elif args.command == "promote":
        print(dump_json(promote(args.id, args.target, config)))
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
                    since=args.since,
                    until=args.until,
                )
            )
        )
    elif args.command == "recall-brief":
        brief_text = _recall_brief(args.prompt, config, args.session)
        if brief_text:
            print(brief_text)
    elif args.command == "subagent-brief":
        import sys

        output = _subagent_brief(sys.stdin.read(), config)
        if output:
            print(output)
    elif args.command == "rule":
        print(dump_json(remember_rule(args.statement, args.scope, args.why, args.example, args.trigger, args.source, config)))
    elif args.command == "rules":
        print(dump_json(rules_in_force(args.prompt, args.context, args.project, args.limit, config)))
    elif args.command == "rule-feedback":
        print(dump_json(rule_feedback(args.id, args.outcome, config)))
    elif args.command == "rule-context":
        print(dump_json(context_view(args.key, config)))
    elif args.command == "rules-brief":
        brief_text = _rules_brief(config)
        if brief_text:
            print(brief_text)
    elif args.command == "session-register":
        register_session(args.session_id, args.cwd, config)
    elif args.command == "claim-edit":
        import json
        import sys

        tool_input = json.loads(sys.stdin.read()).get("tool_input") or {}
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if isinstance(path, str) and path:
            claim_path(args.session_id, path, config)
    elif args.command == "repo-state":
        print(dump_json(repo_state(args.repo, config)))
    elif args.command == "activity":
        report = recent_activity(args.since, args.until, args.author, args.roots, config)
        print(dump_json(report) if args.json else _format_activity(report))
    elif args.command == "forget":
        print(dump_json(forget(args.id, config)))
    elif args.command == "resolve":
        print(dump_json(resolve(args.id, config)))
    elif args.command == "export":
        report = export(args.out, config)
        print(dump_json(report) if args.out else report["markdown"])
    elif args.command == "graph":
        if not args.export:
            return serve_graph(config, args.port, not args.no_open)
        report = export_graph(config, args.export)
        if report.get("error"):
            print(f"Error: {report['error']}")
            return 1
        print(
            f"Wrote {report['notes']} notes and {report['edges']} links to {report['path']}.\n"
            "Warning: the file holds the full text of every exported note, resolved and superseded included. "
            "Share it only where you would share the brain itself."
        )
    elif args.command == "mcp-server":
        return serve()
    return 0


def _rules_brief(config: WorkbenchConfig) -> str:
    """Rules whose scope matches the current repo and branch, as compact lines for a hook.

    Matched on scope only: trigger words are common enough to fire a rule on
    unrelated prompts. Not threshold-gated, because the short prompts that
    inject no notes ("yes", "go") are where an unrepeated rule gets forgotten.
    """
    import subprocess

    context: list[str] = []
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if top.returncode == 0 and top.stdout.strip():
            context.append(f"repo:{Path(top.stdout.strip()).name}")
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if branch.returncode == 0 and branch.stdout.strip():
                context.append(f"branch:{branch.stdout.strip()}")
    except (OSError, subprocess.SubprocessError):
        pass
    report = rules_in_force(context=context, limit=5, config=config)
    found = report.get("rules") or []
    if not found:
        return ""
    lines = ["Rules in force here (brain_context <key> for the full picture):"]
    for rule in found:
        statement = " ".join(str(rule.get("statement", "")).split())
        lines.append(f"- [rule#{rule['id']}] ({rule.get('scope')}) {statement}")
    if report.get("conflicts"):
        lines.append(f"- conflicting rules at equal specificity: {report['conflicts']} — say which you followed")
    return "\n".join(lines)


def _recall_brief(prompt: str, config: WorkbenchConfig, session_id: str | None = None) -> str:
    """Top brain hits for a user prompt, as compact one-liners.

    Threshold-gated so trivial prompts ("yes", "go") inject nothing: the prompt
    must carry at least two distinctive terms, and prompt_hits applies the
    relevance floor and per-session dedupe. Full note bodies stay pull-based
    via brain_recall — this only surfaces ids and hooks.
    """
    import re as _re

    prompt = prompt.strip()[:400]
    distinctive = _re.findall(r"[A-Za-z0-9_/-]{4,}", prompt)
    if len(set(term.lower() for term in distinctive)) < 2:
        return ""
    notes = prompt_hits(prompt, session_id=session_id, limit=5, config=config)
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


SUBAGENT_CONTEXT_CHARS = 2000


def _subagent_brief(payload_text: str, config: WorkbenchConfig) -> str:
    """Stash the Agent prompt on PreToolUse; on SubagentStart, return its recall as hook JSON."""
    import json

    try:
        payload = json.loads(payload_text)
    except ValueError:
        return ""
    if not isinstance(payload, dict) or not isinstance(payload.get("session_id"), str):
        return ""
    session_id = payload["session_id"]
    event = payload.get("hook_event_name")
    if event == "PreToolUse":
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict) and isinstance(tool_input.get("prompt"), str):
            agent_type = tool_input.get("subagent_type") or "general-purpose"
            stash_spawn_prompt(session_id, str(agent_type), tool_input["prompt"], config)
        return ""
    if event != "SubagentStart":
        return ""
    prompt = pop_spawn_prompt(session_id, str(payload.get("agent_type") or ""), config)
    if not prompt:
        return ""
    # No session dedupe: the subagent has not seen what the parent was shown.
    parts = [part for part in (_recall_brief(prompt, config), _rules_brief(config)) if part]
    if not parts:
        return ""
    context = "\n".join(parts)[:SUBAGENT_CONTEXT_CHARS]
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context}})


def _format_activity(report: dict) -> str:
    if report.get("error"):
        return f"Error: {report['error']}"
    window = report.get("window", {})
    lines = [f"Commits {window.get('since')} .. {window.get('until') or 'now'}"]
    lines.append(
        f"{report['total_commits']} commit(s) in {report['repos_with_activity']}/{report['repos_scanned']} repo(s)"
    )
    for repo in report.get("repos", []):
        lines.append("")
        lines.append(f"{repo['repo']} ({repo['commit_count']}) [{repo['branch']}]")
        for commit in repo["commits"]:
            lines.append(f"  {commit['sha']}  {commit['at'][:16].replace('T', ' ')}  {commit['subject']}")
    for key in ("hint", "note"):
        if report.get(key):
            lines.extend(["", report[key]])
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
