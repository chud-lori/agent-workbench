from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()


def _path_from_env(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


def _paths_from_env(name: str, fallback: list[Path]) -> tuple[Path, ...]:
    value = os.environ.get(name)
    if not value:
        return tuple(fallback)
    return tuple(Path(item).expanduser() for item in value.replace(",", ":").split(":") if item.strip())


# Where this clone actually sits, and the directory it was cloned into. Defaults
# derive from these rather than naming a directory layout: a hardcoded
# ~/Somewhere/project default is one machine's filing system baked into source,
# it is wrong for everyone else, and it does not belong in a public repository.
CLONE_ROOT = Path(__file__).resolve().parents[1]
CLONE_PARENT = CLONE_ROOT.parent

DEFAULT_REPO_ROOT = _path_from_env("AGENT_WORKBENCH_REPO_ROOT", HOME / "repo")
DEFAULT_PROJECTS_ROOT = _path_from_env("AGENT_WORKBENCH_PROJECTS_ROOT", CLONE_PARENT)
CODEX_HOME = _path_from_env("AGENT_WORKBENCH_CODEX_HOME", HOME / ".codex")
CLAUDE_HOME = _path_from_env("AGENT_WORKBENCH_CLAUDE_HOME", HOME / ".claude")
WORK_MCP_ROOT = _path_from_env("AGENT_WORKBENCH_WORK_MCP_ROOT", CLONE_PARENT / "work-mcp")
# Beside the clone, so moving the clone moves its state with it.
WORKBENCH_HOME = _path_from_env("AGENT_WORKBENCH_STATE_DIR", CLONE_ROOT / ".state")
# Code index scans only the repo root by default. Override with
# AGENT_WORKBENCH_INDEX_ROOTS (colon- or comma-separated paths).
DEFAULT_INDEX_ROOTS = _paths_from_env("AGENT_WORKBENCH_INDEX_ROOTS", [DEFAULT_REPO_ROOT])


@dataclass(frozen=True)
class WorkbenchConfig:
    repo_root: Path = DEFAULT_REPO_ROOT
    projects_root: Path = DEFAULT_PROJECTS_ROOT
    codex_home: Path = CODEX_HOME
    claude_home: Path = CLAUDE_HOME
    work_mcp_root: Path = WORK_MCP_ROOT
    workbench_home: Path = WORKBENCH_HOME
    index_roots: tuple[Path, ...] = DEFAULT_INDEX_ROOTS
    max_text_bytes: int = 256_000
    max_search_results: int = 50

    @property
    def index_path(self) -> Path:
        return self.workbench_home / "index.sqlite"

    @property
    def brain_path(self) -> Path:
        return self.workbench_home / "brain.sqlite"


def default_config() -> WorkbenchConfig:
    return WorkbenchConfig()
