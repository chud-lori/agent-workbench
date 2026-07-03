from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .code_index import brief_work_item, code_search, codebase_overview, rebuild_index, refresh_index
from .config import default_config
from .knowledge import brief_task, find_service_context, search_knowledge
from .scanners import doctor_report, mcp_health
from .util import dump_json
from .work_sources import external_source_instructions, work_mcp_bridge, work_sources_status


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
        "description": "Build a deterministic task brief from local indexed context for a ticket, feature, or phrase.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
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
        "description": "Rebuild the local SQLite FTS code/product index across repo and Projects. This writes only to the Agent Workbench .state directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"roots": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
    },
    "refresh_code_index": {
        "description": "Incrementally refresh the local SQLite FTS code/product index, skipping unchanged files.",
        "inputSchema": {
            "type": "object",
            "properties": {"roots": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
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
    "brief_work_item": {
        "description": "Create a work-item brief from indexed local code plus a query plan for Jira/Slack/Google Workspace MCP tools.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "work_sources_status": {
        "description": "Inspect configured work MCP sources: Slack, Google Workspace, Atlassian, and Agent Workbench. Does not expose secrets.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "work_mcp_bridge": {
        "description": "Return work-mcp sidecar status, connector commands, and recommended external MCP calls for a query.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "external_source_plan": {
        "description": "Return recommended Jira/Confluence, Slack, and Google Workspace MCP calls for a query.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
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
        "code_search": lambda args: code_search(args.get("query", ""), default_config(), args.get("limit", 20)),
        "codebase_overview": lambda args: codebase_overview(args.get("target"), default_config()),
        "brief_work_item": lambda args: brief_work_item(args.get("query", ""), default_config()),
        "work_sources_status": lambda args: work_sources_status(default_config()),
        "work_mcp_bridge": lambda args: work_mcp_bridge(args.get("query", ""), default_config()),
        "external_source_plan": lambda args: external_source_instructions(args.get("query", "")),
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
                "serverInfo": {"name": "agent-workbench", "version": "0.1.0"},
                "instructions": "Use Agent Workbench tools to inspect local AI agent setup, MCP health, and repo context.",
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
