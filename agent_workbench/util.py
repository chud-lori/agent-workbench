from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable


TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
}


def command_exists(command: str) -> bool:
    if "/" in command:
        return Path(command).expanduser().exists()
    return shutil.which(command) is not None


def read_text_limited(path: Path, max_bytes: int = 256_000) -> str:
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def load_json(path: Path) -> Any:
    return json.loads(read_text_limited(path))


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str)


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if path.name in {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "SKILL.md", ".mcp.json"}:
        return True
    return False


def iter_files(
    roots: Iterable[Path],
    *,
    max_depth: int = 6,
    names: set[str] | None = None,
    suffixes: set[str] | None = None,
) -> Iterable[Path]:
    skip_dirs = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "coverage",
        "dist",
        "build",
        "target",
        "vendor",
    }
    for root in roots:
        if not root.exists():
            continue
        root = root.resolve()
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            rel_depth = len(current_path.relative_to(root).parts)
            if rel_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for file_name in files:
                path = current_path / file_name
                if names and file_name in names:
                    yield path
                elif suffixes and path.suffix.lower() in suffixes:
                    yield path


def run_capture(args: list[str], cwd: Path | None = None, timeout: float = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive wrapper
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr
