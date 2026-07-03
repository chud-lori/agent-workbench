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
    cfg = Path.home() / ".config" / "google-workspace-mcp"
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


DEPRECATED_ATLASSIAN_ENDPOINT = "mcp.atlassian.com/v1/sse"
CURRENT_ATLASSIAN_ENDPOINT = "https://mcp.atlassian.com/v1/mcp"


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
    claude_url = _claude_server_url("atlassian")
    status: dict[str, Any] = {
        "configured_in_codex": configured,
        "url": url,
        "claude_url": claude_url,
        "registered_name": "atlassian",
    }
    warnings = []
    for label, value in (("codex", url), ("claude", claude_url)):
        if value and DEPRECATED_ATLASSIAN_ENDPOINT in value:
            warnings.append(
                f"{label} config uses the deprecated Atlassian SSE endpoint (unsupported after 2026-06-30); "
                f"switch to {CURRENT_ATLASSIAN_ENDPOINT}"
            )
    if warnings:
        status["warnings"] = warnings
    return status


def _claude_server_url(name: str) -> str | None:
    path = Path.home() / ".claude.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(errors="replace"))
    except Exception:
        return None
    server = (data.get("mcpServers") or {}).get(name) or {}
    url = server.get("url")
    if url:
        return url
    for arg in server.get("args") or []:
        if isinstance(arg, str) and arg.startswith("http"):
            return arg
    return None


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
