from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .code_index import _repo_roots
from .config import WorkbenchConfig, default_config
from .repo_state import _git
from .util import parse_time_bound


# Fields for `git log --format`: sha, author ISO date, subject, author name.
_LOG_FORMAT = "%h%x1f%aI%x1f%s%x1f%an"
_MAX_COMMITS_PER_REPO = 100


def recent_activity(
    since: str | int = "yesterday",
    until: str | int | None = None,
    author: str | None = None,
    roots: list[str] | None = None,
    config: WorkbenchConfig | None = None,
) -> dict[str, Any]:
    """What you actually committed in a time window, across every local repo.

    The deterministic half of "what did I do yesterday?": git only, no network.
    Scans all local branches (--all), so work on a branch that is not checked
    out and never pushed still shows up — that work is invisible to `gh` and to
    anything that only reads the default branch.

    Slack, calendar, and PR review load are NOT here: an MCP server cannot call
    another MCP server, so those are the model's job to fetch and merge (see the
    standup skill). This tool owns the git evidence and nothing else.

    author defaults per-repo to that repo's configured user.email, falling back
    to user.name — matching how the commits were actually attributed.
    """
    config = config or default_config()
    try:
        since_epoch = parse_time_bound(since)
        until_epoch = parse_time_bound(until, end_of_day=True) if until is not None else None
    except ValueError as exc:
        return {"error": str(exc), "repos": []}
    if since_epoch is None:
        return {"error": "since is required", "repos": []}
    if until_epoch is not None and since_epoch > until_epoch:
        return {"error": f"since ({since!r}) is after until ({until!r})", "repos": []}

    search_roots = [Path(root).expanduser() for root in roots] if roots else _default_roots(config)
    repos = _repo_roots(search_roots)

    since_arg = _iso_local(since_epoch)
    until_arg = _iso_local(until_epoch) if until_epoch is not None else None

    active: list[dict[str, Any]] = []
    scanned = 0
    truncated_repos: list[str] = []
    for repo in repos:
        if not (repo / ".git").exists():
            continue
        scanned += 1
        who = author or _repo_author(repo)
        if not who:
            continue
        commits = _commits(repo, who, since_arg, until_arg)
        if not commits:
            continue
        if len(commits) > _MAX_COMMITS_PER_REPO:
            truncated_repos.append(repo.name)
            commits = commits[:_MAX_COMMITS_PER_REPO]
        active.append(
            {
                "repo": repo.name,
                "path": str(repo),
                "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
                "commit_count": len(commits),
                "commits": commits,
            }
        )

    result: dict[str, Any] = {
        "window": {"since": since_arg, "until": until_arg},
        "author": author or "(per-repo git config)",
        "repos_scanned": scanned,
        "repos_with_activity": len(active),
        "total_commits": sum(repo["commit_count"] for repo in active),
        "repos": sorted(active, key=lambda item: item["commit_count"], reverse=True),
    }
    if truncated_repos:
        result["truncated_repos"] = truncated_repos
        result["hint"] = (
            f"capped at {_MAX_COMMITS_PER_REPO} commits/repo in: {', '.join(truncated_repos)} — "
            "narrow the window to see the rest."
        )
    if not active:
        result["note"] = (
            f"no commits by this author in {scanned} repo(s) for this window. Commits are only half "
            "the picture — check Slack, PRs, and the calendar before reporting an empty day."
        )
    return result


def _default_roots(config: WorkbenchConfig) -> list[Path]:
    """Index roots plus the projects root — own tooling lives outside ~/repo."""
    seen: list[Path] = []
    for root in (*config.index_roots, config.projects_root):
        if root not in seen:
            seen.append(root)
    return seen


def _repo_author(repo: Path) -> str:
    return _git(repo, "config", "user.email") or _git(repo, "config", "user.name")


def _commits(repo: Path, author: str, since_arg: str, until_arg: str | None) -> list[dict[str, str]]:
    args = [
        "log",
        "--all",
        "--no-merges",
        f"--author={author}",
        f"--since={since_arg}",
        f"--format={_LOG_FORMAT}",
        f"--max-count={_MAX_COMMITS_PER_REPO + 1}",
    ]
    if until_arg:
        args.append(f"--until={until_arg}")
    out = _git(repo, *args)
    if not out:
        return []
    commits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        commits.append({"sha": parts[0], "at": parts[1], "subject": parts[2], "author": parts[3]})
    return commits


def _iso_local(epoch: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(epoch))
