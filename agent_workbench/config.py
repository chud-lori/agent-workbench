from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()


def _path_from_env(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


DEFAULT_REPO_ROOT = _path_from_env("AGENT_WORKBENCH_REPO_ROOT", HOME / "repo")
DEFAULT_PROJECTS_ROOT = _path_from_env("AGENT_WORKBENCH_PROJECTS_ROOT", HOME / "Projects")
CODEX_HOME = _path_from_env("AGENT_WORKBENCH_CODEX_HOME", HOME / ".codex")
CLAUDE_HOME = _path_from_env("AGENT_WORKBENCH_CLAUDE_HOME", HOME / ".claude")
WORK_MCP_ROOT = _path_from_env("AGENT_WORKBENCH_WORK_MCP_ROOT", HOME / "Projects" / "work-mcp")
WORKBENCH_HOME = _path_from_env("AGENT_WORKBENCH_STATE_DIR", HOME / "Projects" / "agent-workbench" / ".state")


@dataclass(frozen=True)
class WorkbenchConfig:
    repo_root: Path = DEFAULT_REPO_ROOT
    projects_root: Path = DEFAULT_PROJECTS_ROOT
    codex_home: Path = CODEX_HOME
    claude_home: Path = CLAUDE_HOME
    work_mcp_root: Path = WORK_MCP_ROOT
    workbench_home: Path = WORKBENCH_HOME
    max_text_bytes: int = 256_000
    max_search_results: int = 50

    @property
    def index_path(self) -> Path:
        return self.workbench_home / "index.sqlite"


def default_config() -> WorkbenchConfig:
    return WorkbenchConfig()
