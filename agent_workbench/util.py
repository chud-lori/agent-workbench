from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, time as day_time, timedelta
from pathlib import Path
from typing import Any, Iterable

try:  # tomllib landed in 3.11; this project supports 3.10.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter
    tomllib = None  # type: ignore[assignment]

TOML_AVAILABLE = tomllib is not None
TOML_UNAVAILABLE_REASON = (
    "reading Codex's config.toml needs a TOML parser (tomllib, Python 3.11+); "
    "on 3.10 these checks are skipped rather than guessed"
)


def load_toml(text: str) -> dict[str, Any]:
    """Parse TOML text, raising when the interpreter has no parser.

    Callers already treat a parse failure as "cannot inspect this file"; the
    important part is that they must not silently report *absence* when the
    truth is that nothing could be read.
    """
    if tomllib is None:
        raise RuntimeError(TOML_UNAVAILABLE_REASON)
    return tomllib.loads(text)


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


_RELATIVE_BOUND = re.compile(r"(\d+)([dhw])")
_RELATIVE_UNITS = {"d": "days", "h": "hours", "w": "weeks"}


def parse_time_bound(
    value: str | int | float | None,
    *,
    end_of_day: bool = False,
    now: float | None = None,
) -> int | None:
    """Parse a date/time bound to a local-time epoch, or None if value is None.

    Accepts an epoch number, 'YYYY-MM-DD', an ISO timestamp, or the relative
    shorthands 'today' / 'yesterday' / 'Nd' | 'Nh' | 'Nw' (N ago). Raises
    ValueError on anything else — callers surface it rather than silently
    scanning the wrong window.

    Bare dates are day-aligned, and end_of_day snaps to 23:59:59 so that
    until='2026-07-15' covers all of 15 Jul instead of cutting at midnight.
    Pairing since='yesterday' with until='yesterday' therefore spans exactly
    that one day.

    Always returns int: sqlite compares an int param against the integer
    created_at column, but a *string* epoch matches zero rows silently.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"not a time bound: {value!r}")
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if not text:
        return None
    base = datetime.fromtimestamp(now) if now is not None else datetime.now()

    if text in {"today", "yesterday"}:
        day = base.date() if text == "today" else (base - timedelta(days=1)).date()
        return _day_epoch(day, end_of_day)
    relative = _RELATIVE_BOUND.fullmatch(text)
    if relative:
        unit = _RELATIVE_UNITS[relative.group(2)]
        return int((base - timedelta(**{unit: int(relative.group(1))})).timestamp())
    try:
        return _day_epoch(datetime.strptime(text, "%Y-%m-%d").date(), end_of_day)
    except ValueError:
        pass
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError as exc:
        raise ValueError(
            f"unrecognized time bound {value!r}; use YYYY-MM-DD, an ISO timestamp, "
            "'today', 'yesterday', or 'Nd'/'Nh'/'Nw'"
        ) from exc


def _day_epoch(day: Any, end_of_day: bool) -> int:
    moment = datetime.combine(day, day_time(23, 59, 59) if end_of_day else day_time(0, 0, 0))
    return int(moment.timestamp())


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
