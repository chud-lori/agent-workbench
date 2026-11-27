from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .activity import recent_activity
from .brain import amend, export, forget, get_notes, promote, recall, remember, resolve
from .code_index import code_search, codebase_overview, index_status, rebuild_index, refresh_index
from .config import default_config
from .knowledge import brief_task, find_service_context, search_knowledge
from .repo_state import repo_state
from .rules import context_view, remember_rule, rule_feedback, rules_in_force
from .scanners import doctor_report, mcp_health
from .util import dump_json
from .work_sources import work_sources_status


PROTOCOL_VERSION = "2025-06-18"

# Above this many notes, recall and brief_task return one-line summaries unless summary_only=false.
SUMMARY_THRESHOLD = 5
SUMMARY_CHARS = 160
RESULT_BYTE_CAP = 10_000
# Neither can be narrowed by an argument: a cut export or findings list could never be completed.
UNCAPPED_TOOLS = {"brain_export", "doctor_report"}


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


TOOLS: dict[str, dict[str, Any]] = {
    "doctor_report": {
        "description": "Return local Agent Workbench diagnostics: secrets, MCP config, broad permissions, stale docs, and large state.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "mcp_health": {
        "description": "Check local MCP config health for Codex/Claude/project MCP files.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "search_knowledge": {
        "description": "Search local repo docs, AGENTS.md, CLAUDE.md, SKILL.md, and README files.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "brief_task": {
        "description": "One-call orchestrated brief for a ticket/feature/phrase: merges code index hits, agent docs, saved brain notes, likely repos, and repo commands. Warns when another session edited a file in the code hits within the last week. A note list longer than 5 comes back as one-line summaries (id, kind, project, title, created date); fetch bodies with brain_recall ids=[...]. Results over ~10 KB drop whole items from the longest lists and set truncated.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "summary_only": {"type": "boolean", "description": "Force note summaries (true) or full bodies (false). Default: summaries when a list has more than 5 notes"},
                "session_id": {"type": "string", "description": "This session's id, printed at session start, so its own file claims are not reported back"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "brain_remember": {
        "description": "Persist a durable note (decision, fact, gotcha, preference, todo, reference) so future sessions can recall it. Pass supersedes=[ids] when this note corrects/replaces older ones — superseded notes are hidden from default recall. The result may include similar_notes; review them and amend/supersede instead of stacking contradictions. Use kind=reference to pin canonical docs (runbooks, wiki pages, dashboards) with their title, key sections, and URL/id so they surface in recall and brief_task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "kind": {"type": "string", "enum": ["decision", "fact", "gotcha", "preference", "todo", "note", "reference"]},
                "project": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "supersedes": {"type": "array", "items": {"type": "integer"}, "description": "Note ids this note corrects/replaces; they get hidden from default recall"},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
    "brain_amend": {
        "description": "Update an existing brain note in place: mode=append (default) adds a dated addendum, mode=replace rewrites the body. Prefer this over storing a near-duplicate note when correcting or extending earlier knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["append", "replace"]},
            },
            "required": ["id", "content"],
            "additionalProperties": False,
        },
    },
    "brain_rule_remember": {
        "description": "Store a contextual RULE: how to behave in a context, learned from a correction. Different from brain_remember, which stores what is true. Give the narrowest scope that explains the correction (repo:x, workstream:y, audience:qa, task:z, channel:c) — a global rule applies everywhere and a global rule that is wrong somewhere gets ignored everywhere. A correction that restates an existing rule in the same scope sharpens that rule instead of duplicating it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "statement": {"type": "string", "description": "The behaviour to follow"},
                "scope": {"type": "array", "items": {"type": "string"}, "description": "Context keys, each type:value. Omit for a rule that truly holds everywhere"},
                "why": {"type": "string", "description": "The user's reason, quoted where possible"},
                "example": {"type": "string", "description": "One real case this came from"},
                "trigger": {"type": "array", "items": {"type": "string"}, "description": "Words that signal the context is active even when the scope keys are not known"},
                "source": {"type": "string", "description": "Where this came from: ticket, thread, file:line, session date"},
            },
            "required": ["statement"],
            "additionalProperties": False,
        },
    },
    "brain_rules_in_force": {
        "description": "The rules governing the active context, most specific first. Retrieved by scope match rather than text similarity, so a rule comes back when you are in its context even when the prompt shares no words with the correction that created it. Reports which rules overlap at equal specificity so an ambiguity is visible rather than silently resolved.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The current request, matched against rule triggers"},
                "context": {"type": "array", "items": {"type": "string"}, "description": "Active context keys, each type:value"},
                "project": {"type": "string", "description": "Repo dir name; adds repo:<name> to the context"},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    "brain_rule_feedback": {
        "description": "Record that a surfaced rule failed (outcome=corrected), or retire it (outcome=retire). There is no 'applied' outcome on purpose: self-reported compliance is not evidence, so the measurable facts are that a rule was surfaced and that the output still had to be corrected.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "outcome": {"type": "string", "enum": ["corrected", "retire"]},
            },
            "required": ["id", "outcome"],
            "additionalProperties": False,
        },
    },
    "brain_context": {
        "description": "Everything known about behaving in one context: its rules most-specific-first, plus health flags — rules never surfaced there (likely mis-scoped) and rules corrected more than once after being shown (likely wrong).",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "A single context key, type:value"}},
            "required": ["key"],
            "additionalProperties": False,
        },
    },
    "brain_promote": {
        "description": "Promote a personal brain note into a shared, git-versioned markdown reference file (team playbook, skill references/, runbook repo). Appends the note as a readable block and stamps the note so it is never promoted twice. Use when a personal learning proves general enough for the whole team.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "target": {"type": "string", "description": "Markdown file path to append the note to"},
            },
            "required": ["id", "target"],
            "additionalProperties": False,
        },
    },
    "brain_recall": {
        "description": "Search saved brain notes by query/project/kind; omit query to list most recent notes. Bound by when notes were stored with since/until ('yesterday', '2026-07-15', '7d'). Superseded notes are hidden unless include_superseded. Pass thread=<tag/key/keyword> for a chronological digest of every note on that storyline (superseded collapsed to stubs). Note: the brain holds durable facts, not an activity log — for what you actually did in a window, use recent_activity. More than 5 hits come back as one-line summaries (id, kind, project, title, created date) with truncated and notes_count; pass ids=[...] for full bodies. Results over ~10 KB drop whole notes and set truncated.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "integer"}, "description": "Fetch these notes in full by id (resolved and superseded included); other filters are ignored"},
                "summary_only": {"type": "boolean", "description": "Force summaries (true) or full bodies (false). Default: summaries above 5 hits"},
                "query": {"type": "string"},
                "project": {"type": "string"},
                "kind": {"type": "string"},
                "limit": {"type": "integer"},
                "include_resolved": {"type": "boolean"},
                "include_superseded": {"type": "boolean"},
                "thread": {"type": "string", "description": "Tag, issue key, or keyword to digest chronologically"},
                "since": {
                    "type": "string",
                    "description": "Only notes stored at/after this: YYYY-MM-DD, ISO timestamp, 'today', 'yesterday', or 'Nd'/'Nh'/'Nw' ago. Filters before `limit`, so nothing is silently dropped.",
                },
                "until": {
                    "type": "string",
                    "description": "Only notes stored at/before this (inclusive; a bare date covers that whole day).",
                },
            },
            "additionalProperties": False,
        },
    },
    "brain_forget": {
        "description": "Delete a brain note by id (ids come from brain_recall).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    "brain_resolve": {
        "description": "Mark a brain note resolved by id so default brain_recall hides it.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    "brain_export": {
        "description": "Export all brain notes (including resolved) as a markdown document, optionally written to a file.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "find_service_context": {
        "description": "Find likely repo/service context and commands for a service name.",
        "inputSchema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
            "additionalProperties": False,
        },
    },
    "rebuild_code_index": {
        "description": "Rebuild the local SQLite FTS code/product index. Defaults to the configured index roots (AGENT_WORKBENCH_INDEX_ROOTS, else .state/index-roots, else ~/repo). Writes only to the Agent Workbench .state directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"roots": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
    },
    "refresh_code_index": {
        "description": "Incrementally refresh the local SQLite FTS code/product index (defaults to the configured index roots), skipping unchanged files; a new root is added alongside existing repos.",
        "inputSchema": {
            "type": "object",
            "properties": {"roots": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
    },
    "index_status": {
        "description": "Report code index freshness: repo/document counts and age in hours.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "code_search": {
        "description": "Search the local SQLite FTS code/product index. Run rebuild_code_index first if needed.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "codebase_overview": {
        "description": "Return indexed repo/product overview: languages, package files, and docs.",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "work_sources_status": {
        "description": "Inspect configured work MCP sources: Slack, Google Workspace, Atlassian, and Agent Workbench. Does not expose secrets.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "repo_state": {
        "description": "Report a repo's working-tree state vs its deployed baseline: current branch, ahead/behind origin/main|master, dirty files, fetch staleness. Call before making claims about production behavior from local code — local checkouts often sit on feature branches with undeployed changes.",
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string", "description": "Repo name (under the repo/projects roots) or absolute path"}},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    "recent_activity": {
        "description": (
            "What you committed in a time window, across every local repo (scans all branches, so "
            "unpushed work that `gh` cannot see still shows up). The git evidence for standups and "
            '"what did I do yesterday?" — commits only; pair it with Slack/calendar/PR lookups for a '
            "full picture, since this server has no network access. Returns per-repo commit counts by "
            "default; pass repo=<name> for that repo's commits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": "Start of window: YYYY-MM-DD, ISO timestamp, 'today', 'yesterday', or 'Nd'/'Nh'/'Nw' ago. Default 'yesterday'.",
                },
                "until": {
                    "type": "string",
                    "description": "End of window (inclusive; a bare date covers that whole day). Omit for 'up to now'.",
                },
                "author": {
                    "type": "string",
                    "description": "Author name/email substring. Defaults per-repo to that repo's git config user.email.",
                },
                "repo": {
                    "type": "string",
                    "description": "Repo name or path from a previous call; returns only that repo, with its commits.",
                },
                "roots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Override the directories scanned. Defaults to the index roots plus the projects root.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def serve() -> int:
    handlers: dict[str, ToolHandler] = {
        "doctor_report": lambda args: doctor_report(default_config()),
        "mcp_health": lambda args: mcp_health(default_config()),
        "search_knowledge": lambda args: search_knowledge(args.get("query", ""), default_config(), args.get("limit")),
        "brief_task": lambda args: _brief_task(args),
        "find_service_context": lambda args: find_service_context(args.get("service", ""), default_config()),
        "rebuild_code_index": lambda args: rebuild_index(default_config(), args.get("roots")),
        "refresh_code_index": lambda args: refresh_index(default_config(), args.get("roots")),
        "index_status": lambda args: index_status(default_config()),
        "code_search": lambda args: code_search(args.get("query", ""), default_config(), args.get("limit", 20)),
        "codebase_overview": lambda args: codebase_overview(args.get("target"), default_config()),
        "brain_remember": lambda args: remember(
            args.get("content", ""),
            args.get("kind", "note"),
            args.get("project"),
            args.get("tags"),
            default_config(),
            supersedes=args.get("supersedes"),
        ),
        "brain_promote": lambda args: promote(args.get("id", 0), args.get("target", ""), default_config()),
        "brain_rule_remember": lambda args: remember_rule(
            args.get("statement", ""),
            args.get("scope"),
            args.get("why"),
            args.get("example"),
            args.get("trigger"),
            args.get("source"),
            default_config(),
        ),
        "brain_rules_in_force": lambda args: rules_in_force(
            args.get("prompt"),
            args.get("context"),
            args.get("project"),
            args.get("limit", 10),
            default_config(),
        ),
        "brain_rule_feedback": lambda args: rule_feedback(args.get("id", 0), args.get("outcome", ""), default_config()),
        "brain_context": lambda args: context_view(args.get("key", ""), default_config()),
        "brain_amend": lambda args: amend(
            args.get("id", 0),
            args.get("content", ""),
            args.get("mode", "append"),
            default_config(),
        ),
        "brain_recall": lambda args: _brain_recall(args),
        "repo_state": lambda args: repo_state(args.get("repo", ""), default_config()),
        "recent_activity": lambda args: _recent_activity(args),
        "brain_forget": lambda args: forget(args.get("id", 0), default_config()),
        "brain_resolve": lambda args: resolve(args.get("id", 0), default_config()),
        "brain_export": lambda args: export(args.get("path"), default_config()),
        "work_sources_status": lambda args: work_sources_status(default_config()),
    }
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = _handle_request(request, handlers)
        except Exception as exc:
            response = _error(None, -32603, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def _handle_request(request: dict[str, Any], handlers: dict[str, ToolHandler]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        client_version = (request.get("params") or {}).get("protocolVersion")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": client_version if client_version == PROTOCOL_VERSION else PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "agent-workbench", "version": "0.5.0"},
                "instructions": (
                    "Agent Workbench: local setup diagnostics, an FTS code index over ~/repo, and a persistent brain. "
                    "Start a task with brief_task (merges code hits, docs, brain notes, and pinned references). "
                    "Store durable decisions/gotchas with brain_remember; correct earlier notes with brain_amend or "
                    "supersedes=[ids] instead of stacking contradictions. Use brain_recall thread=<key> for a "
                    "chronological storyline digest. Before claiming how production behaves, run repo_state on the "
                    "repo — local checkouts often carry undeployed branches."
                ),
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": [{"name": name, **spec} for name, spec in TOOLS.items()]},
        }
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = handlers.get(name)
        if not handler:
            return _error(request_id, -32602, f"Unknown tool: {name}")
        result = handler(args)
        if name not in UNCAPPED_TOOLS:
            result = _cap_result(result)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": dump_json(result)}],
                "structuredContent": result,
                "isError": False,
            },
        }
    return _error(request_id, -32601, f"Method not found: {method}")


def _brain_recall(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("ids"):
        result = get_notes(args["ids"], default_config())
        if args.get("summary_only"):
            _summarise(result, "notes", True)
        return result
    result = recall(
        args.get("query"),
        args.get("project"),
        args.get("kind"),
        args.get("limit", 20),
        args.get("include_resolved", False),
        default_config(),
        thread=args.get("thread"),
        include_superseded=args.get("include_superseded", False),
        since=args.get("since"),
        until=args.get("until"),
    )
    _summarise(result, "notes", args.get("summary_only"))
    return result


def _brief_task(args: dict[str, Any]) -> dict[str, Any]:
    result = brief_task(args.get("query", ""), default_config(), args.get("session_id"))
    for key in ("brain_notes", "pinned_references"):
        _summarise(result, key, args.get("summary_only"))
    return result


def _recent_activity(args: dict[str, Any]) -> dict[str, Any]:
    result = recent_activity(
        args.get("since", "yesterday"),
        args.get("until"),
        args.get("author"),
        args.get("roots"),
        default_config(),
    )
    repo = args.get("repo")
    if repo:
        result["repos"] = [entry for entry in result["repos"] if repo in (entry["repo"], entry["path"])]
        if not result["repos"]:
            _add_hint(result, f"no activity for repo {repo!r} in this window; call without repo to list active repos.")
    elif result.get("repos"):
        for entry in result["repos"]:
            entry.pop("commits", None)
        _add_hint(result, "counts only; pass repo=<name> for that repo's commits.")
    return result


def _summarise(result: dict[str, Any], key: str, summary_only: bool | None) -> None:
    """Swap note bodies for one-line summaries in place; summary_only=None means only above the threshold."""
    notes = result.get(key)
    if not isinstance(notes, list) or not notes:
        return
    if summary_only is None:
        summary_only = len(notes) > SUMMARY_THRESHOLD
    if not summary_only:
        return
    result[key] = [_note_summary(note) for note in notes]
    result["truncated"] = True
    result[f"{key}_count"] = len(notes)
    _add_hint(result, f"{key} are summaries; brain_recall ids=[...] returns full bodies.")


def _note_summary(note: dict[str, Any]) -> dict[str, Any]:
    lines = (note.get("content") or "").strip().splitlines()
    title = lines[0].strip() if lines else ""
    if len(title) > SUMMARY_CHARS:
        title = title[: SUMMARY_CHARS - 1] + "…"
    summary = {key: note.get(key) for key in ("id", "kind", "project", "created_at_iso")}
    summary["title"] = title
    return summary


def _cap_result(result: Any) -> Any:
    """Drop whole items from the largest lists until the serialised result fits RESULT_BYTE_CAP."""
    if not isinstance(result, dict) or _size(result) <= RESULT_BYTE_CAP:
        return result
    dropped: dict[str, int] = {}
    result["truncated"] = True
    result["dropped_items"] = dropped
    _add_hint(result, f"result capped at {RESULT_BYTE_CAP} bytes; narrow the query or filters to see the dropped items.")
    while _size(result) > RESULT_BYTE_CAP:
        # A list is never emptied, so one oversized item still comes back whole.
        candidates = [(path, items) for path, items in _lists(result, "") if len(items) > 1]
        if not candidates:
            break
        path, items = max(candidates, key=lambda candidate: _size(candidate[1]))
        items.pop()
        dropped[path] = dropped.get(path, 0) + 1
    return result


def _lists(value: Any, path: str):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _lists(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        yield path, value
        for child in value:
            yield from _lists(child, f"{path}[]")


def _size(value: Any) -> int:
    return len(dump_json(value).encode("utf-8"))


def _add_hint(result: dict[str, Any], hint: str) -> None:
    result["hint"] = f"{result['hint']} {hint}" if result.get("hint") else hint


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
