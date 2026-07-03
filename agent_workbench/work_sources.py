from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig, default_config
from .util import command_exists, read_text_limited, run_capture


def work_sources_status(config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    root = config.work_mcp_root
    sources = {
        "work_mcp_root": str(root),
        "exists": root.exists(),
        "git": _git_status(root),
        "slack": _slack_status(root),
        "google_workspace": _google_status(root),
        "atlassian": _atlassian_status(config),
        "agent_workbench": _agent_workbench_status(config),
        "bridge": {
            "mode": "sidecar",
            "description": "Agent Workbench keeps code/product context; work-mcp keeps connector code and credentials.",
            "secrets_policy": "Do not copy Slack tokens or Google OAuth tokens into Agent Workbench.",
        },
    }
    return sources


def work_mcp_bridge(query: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    status = work_sources_status(config)
    return {
        "query": query,
        "status": status,
        "connector_commands": _connector_commands(config.work_mcp_root),
        "external_source_plan": external_source_instructions(query),
        "recommended_flow": [
            "Call agent_workbench.code_search or brief_work_item first for local code/product context.",
            "Call the existing atlassian, slack, and google_workspace_local MCP servers for source-of-truth work data.",
            "Merge external source results into the local code brief before editing.",
            "Keep connector credentials in work-mcp and user config; do not duplicate them in this repo.",
        ],
    }


def external_source_instructions(query: str) -> dict[str, Any]:
    safe_query = query.replace("'", " ")
    return {
        "query": query,
        "note": "Agent Workbench does not duplicate Jira/Slack/Google secrets. Use these existing MCP tools from Codex/Claude and merge their output with brief_work_item.",
        "recommended_calls": [
            {"tool": "mcp__atlassian.search", "arguments": {"query": query}},
            {"tool": "mcp__slack.slack_search_messages", "arguments": {"query": query, "count": 20}},
            {
                "tool": "mcp__google_workspace_local.drive_search",
                "arguments": {"query": f"fullText contains '{safe_query}'", "page_size": 20},
            },
        ],
    }


def _slack_status(root: Path) -> dict[str, Any]:
    server = root / "slack-mcp" / "index.js"
    package = root / "slack-mcp" / "package.json"
    env_file = root / "slack-mcp" / ".env"
    return {
        "server_path": str(server),
        "server_exists": server.exists(),
        "package_exists": package.exists(),
        "node_available": command_exists("node"),
        "env_file_exists": env_file.exists(),
        "token_configured": _env_has_key(env_file, "SLACK_USER_TOKEN") or _env_has_key(env_file, "SLACK_BOT_TOKEN"),
        "registered_name": "slack",
        "launch_command": ["node", str(server)],
    }


def _google_status(root: Path) -> dict[str, Any]:
    server_dir = root / "google-workspace-mcp"
    pyproject = server_dir / "pyproject.toml"
    venv_binary = server_dir / ".venv" / "bin" / "google-workspace-mcp"
    cfg = Path.home() / ".config" / "codex-google-local-mcp"
    return {
        "server_dir": str(server_dir),
        "server_exists": pyproject.exists(),
        "venv_binary": str(venv_binary),
        "venv_binary_exists": venv_binary.exists(),
        "oauth_client_exists": (cfg / "oauth-client.json").exists(),
        "token_exists": (cfg / "token.json").exists(),
        "registered_name": "google_workspace_local",
        "launch_command": [str(venv_binary)],
    }


def _atlassian_status(config: WorkbenchConfig) -> dict[str, Any]:
    codex_config = config.codex_home / "config.toml"
    configured = False
    url = None
    if codex_config.exists():
        try:
            data = tomllib.loads(read_text_limited(codex_config, 512_000))
            server = data.get("mcp_servers", {}).get("atlassian", {})
            configured = bool(server)
            url = server.get("url")
        except Exception:
            pass
    return {"configured_in_codex": configured, "url": url, "registered_name": "atlassian"}


def _agent_workbench_status(config: WorkbenchConfig) -> dict[str, Any]:
    codex_config = config.codex_home / "config.toml"
    configured = False
    command = None
    args = None
    if codex_config.exists():
        try:
            data = tomllib.loads(read_text_limited(codex_config, 512_000))
            server = data.get("mcp_servers", {}).get("agent_workbench", {})
            configured = bool(server)
            command = server.get("command")
            args = server.get("args")
        except Exception:
            pass
    return {
        "configured_in_codex": configured,
        "command": command,
        "args": args,
        "registered_name": "agent_workbench",
    }


def _git_status(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"is_git_repo": False}
    remote_code, remote_out, remote_err = run_capture(["git", "remote", "-v"], cwd=root)
    status_code, status_out, status_err = run_capture(["git", "status", "--short"], cwd=root)
    branch_code, branch_out, branch_err = run_capture(["git", "branch", "--show-current"], cwd=root)
    return {
        "is_git_repo": True,
        "branch": branch_out.strip() if branch_code == 0 else None,
        "remote": _parse_origin(remote_out) if remote_code == 0 else None,
        "dirty": bool(status_out.strip()) if status_code == 0 else None,
        "status_error": status_err.strip() if status_code != 0 else None,
        "remote_error": remote_err.strip() if remote_code != 0 else None,
        "branch_error": branch_err.strip() if branch_code != 0 else None,
    }


def _parse_origin(remote_out: str) -> str | None:
    for line in remote_out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "origin":
            return parts[1]
    return None


def _connector_commands(root: Path) -> dict[str, Any]:
    slack_server = root / "slack-mcp" / "index.js"
    google_binary = root / "google-workspace-mcp" / ".venv" / "bin" / "google-workspace-mcp"
    return {
        "slack": {
            "registered_name": "slack",
            "command": ["node", str(slack_server)],
            "ready": slack_server.exists() and command_exists("node"),
        },
        "google_workspace_local": {
            "registered_name": "google_workspace_local",
            "command": [str(google_binary)],
            "ready": google_binary.exists(),
        },
        "atlassian": {
            "registered_name": "atlassian",
            "command": "remote MCP configured in Codex/Claude",
            "ready": True,
        },
    }


def _env_has_key(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.strip().startswith(f"{key}="):
                return bool(line.split("=", 1)[1].strip())
    except OSError:
        return False
    return False
