from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .brain import forget, recall, remember
from .code_index import code_search, codebase_overview, index_status, rebuild_index, refresh_index
from .config import default_config
from .knowledge import brief_task, find_service_context, search_knowledge
from .scanners import doctor_report, mcp_health
from .util import dump_json
from .work_sources import work_sources_status


PROTOCOL_VERSION = "2025-06-18"


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
        "description": "One-call orchestrated brief for a ticket/feature/phrase: merges code index hits, agent docs, saved brain notes, likely repos, and repo commands.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "brain_remember": {
        "description": "Persist a durable note (decision, fact, gotcha, preference, todo) so future sessions can recall it. Notes surface in brain_recall and brief_task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "kind": {"type": "string", "enum": ["decision", "fact", "gotcha", "preference", "todo", "note"]},
                "project": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
    "brain_recall": {
        "description": "Search saved brain notes by query/project/kind; omit query to list most recent notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string"},
                "kind": {"type": "string"},
                "limit": {"type": "integer"},
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
        "description": "Rebuild the local SQLite FTS code/product index. Defaults to ~/repo (override with roots or AGENT_WORKBENCH_INDEX_ROOTS). Writes only to the Agent Workbench .state directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"roots": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
    },
    "refresh_code_index": {
        "description": "Incrementally refresh the local SQLite FTS code/product index (defaults to ~/repo), skipping unchanged files.",
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
}


def serve() -> int:
    handlers: dict[str, ToolHandler] = {
        "doctor_report": lambda args: doctor_report(default_config()),
        "mcp_health": lambda args: mcp_health(default_config()),
        "search_knowledge": lambda args: search_knowledge(args.get("query", ""), default_config(), args.get("limit")),
        "brief_task": lambda args: brief_task(args.get("query", ""), default_config()),
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
        ),
        "brain_recall": lambda args: recall(
            args.get("query"),
            args.get("project"),
            args.get("kind"),
            args.get("limit", 20),
            default_config(),
        ),
        "brain_forget": lambda args: forget(args.get("id", 0), default_config()),
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
                "serverInfo": {"name": "agent-workbench", "version": "0.2.0"},
                "instructions": (
                    "Agent Workbench: local setup diagnostics, an FTS code index over ~/repo, and a persistent brain. "
                    "Start a task with brief_task (merges code hits, docs, and brain notes). "
                    "Store durable decisions/gotchas with brain_remember so future sessions recall them."
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


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
