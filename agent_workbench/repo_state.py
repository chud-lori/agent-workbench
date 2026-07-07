from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig, default_config


_STALE_FETCH_HOURS = 72


def repo_state(repo: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """Report where a working tree sits relative to its deployed baseline.

    Answers "can I trust this checkout to reflect production?" for any git
    repo: current branch, ahead/behind origin/main (or master), dirty files,
    and fetch staleness. Warnings are phrased for an agent about to make
    prod-behavior claims from local code.
    """
    config = config or default_config()
    path = _resolve(repo, config)
    if path is None:
        return {"repo": repo, "error": "repo not found (tried as path, under repo root, and projects root)"}
    if not (path / ".git").exists():
        return {"repo": str(path), "error": "not a git repository"}

    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    baseline = next(
        (ref for ref in ("origin/main", "origin/master") if _git(path, "rev-parse", "--verify", "--quiet", ref)),
        None,
    )
    result: dict[str, Any] = {"repo": str(path), "branch": branch, "baseline": baseline}
    warnings: list[str] = []

    if baseline:
        counts = _git(path, "rev-list", "--left-right", "--count", f"{baseline}...HEAD")
        if counts:
            behind, ahead = (int(part) for part in counts.split())
            result["ahead_of_baseline"] = ahead
            result["behind_baseline"] = behind
            if ahead or (branch not in {"main", "master"}):
                warnings.append(
                    f"working tree is on '{branch}', {ahead} commit(s) ahead / {behind} behind {baseline} — "
                    f"verify against {baseline} (git show {baseline}:<file>) before making prod-behavior claims or patches"
                )
    else:
        warnings.append("no origin/main or origin/master ref — cannot compare against a deployed baseline")

    status = _git(path, "status", "--porcelain")
    dirty = len(status.splitlines()) if status else 0
    result["dirty_files"] = dirty
    if dirty:
        warnings.append(f"{dirty} uncommitted change(s) in the working tree")

    fetch_head = path / ".git" / "FETCH_HEAD"
    if fetch_head.exists():
        age_hours = (time.time() - fetch_head.stat().st_mtime) / 3600
        result["last_fetch_hours_ago"] = round(age_hours, 1)
        if age_hours > _STALE_FETCH_HOURS:
            warnings.append(
                f"origin refs last fetched ~{int(age_hours)}h ago — run git fetch before trusting the baseline"
            )

    last_commit = _git(path, "log", "-1", "--format=%cI")
    if last_commit:
        result["last_commit"] = last_commit
    result["warnings"] = warnings
    return result


def _resolve(repo: str, config: WorkbenchConfig) -> Path | None:
    candidates = [Path(repo).expanduser(), config.repo_root / repo, config.projects_root / repo]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _git(path: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""
