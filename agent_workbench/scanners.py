from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import WorkbenchConfig, default_config
from .util import command_exists, dump_json, iter_files, load_json, read_text_limited


@dataclass
class Finding:
    severity: str
    category: str
    path: str
    line: int | None
    title: str
    detail: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("MongoDB URI with credentials", re.compile(r"mongodb(?:\+srv)?://[^:\s/]+:[^@\s]+@", re.I)),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Generic API token assignment", re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]")),
]

BROAD_PERMISSION_PATTERNS = [
    "Bash(git *)",
    "Bash(python *)",
    "Bash(python3 *)",
    "Bash(curl *)",
    "Bash(pip install *)",
    "Bash(npm install *)",
]

DOC_NAMES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "SKILL.md", "copilot-instructions.md"}


def scan_all(config: WorkbenchConfig | None = None) -> list[Finding]:
    config = config or default_config()
    findings: list[Finding] = []
    findings.extend(scan_mcp_configs(config))
    findings.extend(scan_assistant_permissions(config))
    findings.extend(scan_secrets(config))
    findings.extend(scan_large_state(config))
    findings.extend(scan_stale_doc_paths(config))
    return sorted(findings, key=_finding_sort_key)


def scan_mcp_configs(config: WorkbenchConfig) -> list[Finding]:
    findings: list[Finding] = []
    codex_config = config.codex_home / "config.toml"
    if codex_config.exists():
        try:
            data = tomllib.loads(read_text_limited(codex_config, 512_000))
            servers = data.get("mcp_servers", {})
            for name, server in servers.items():
                command = server.get("command")
                if command and not command_exists(command):
                    findings.append(
                        Finding(
                            "high",
                            "mcp",
                            str(codex_config),
                            None,
                            f"Codex MCP command missing: {name}",
                            f"Configured command is not executable or not on PATH: {command}",
                            "Install the command or update ~/.codex/config.toml.",
                        )
                    )
        except Exception as exc:
            findings.append(
                Finding("medium", "mcp", str(codex_config), None, "Cannot parse Codex config", str(exc), "Fix TOML syntax.")
            )

    for mcp_json in iter_files([config.repo_root, config.projects_root], max_depth=4, names={".mcp.json"}):
        try:
            data = load_json(mcp_json)
        except Exception as exc:
            findings.append(Finding("medium", "mcp", str(mcp_json), None, "Cannot parse .mcp.json", str(exc), "Fix JSON syntax."))
            continue
        for name, server in data.get("mcpServers", {}).items():
            command = server.get("command")
            if command and not command_exists(command):
                findings.append(
                    Finding(
                        "high",
                        "mcp",
                        str(mcp_json),
                        _line_for(mcp_json, f'"command": "{command}"'),
                        f"Project MCP command missing: {name}",
                        f"Configured command is not executable or not on PATH: {command}",
                        "Install the command or update/remove this project MCP server.",
                    )
                )
    return findings


def scan_assistant_permissions(config: WorkbenchConfig) -> list[Finding]:
    findings: list[Finding] = []
    settings_files = list(iter_files([config.repo_root, config.projects_root], max_depth=5, names={"settings.local.json", "settings.json"}))
    settings_files.extend([config.claude_home / "settings.json"])
    for path in settings_files:
        if not path.exists():
            continue
        try:
            text = read_text_limited(path)
        except OSError:
            continue
        for pattern in BROAD_PERMISSION_PATTERNS:
            line = _line_for_text(text, pattern)
            if line:
                findings.append(
                    Finding(
                        "medium",
                        "permissions",
                        str(path),
                        line,
                        "Broad assistant permission",
                        f"Permission allowlist contains {pattern}.",
                        "Replace broad permissions with task-specific commands.",
                    )
                )
        if "\x1b" in text or "[1m" in text:
            findings.append(
                Finding(
                    "medium",
                    "config",
                    str(path),
                    _line_for_text(text, "[1m"),
                    "Possible terminal escape text in config",
                    "Config appears to include copied terminal formatting.",
                    "Edit the value to a clean model/config string.",
                )
            )
    return findings


def scan_secrets(config: WorkbenchConfig) -> list[Finding]:
    findings: list[Finding] = []
    roots = [config.repo_root, config.projects_root, config.claude_home, config.codex_home]
    interesting_names = DOC_NAMES | {"settings.local.json", "settings.json", ".mcp.json", "config.toml", ".env", ".env.example"}
    for path in iter_files(roots, max_depth=5, names=interesting_names, suffixes={".md", ".json", ".toml", ".env"}):
        if not path.exists() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = read_text_limited(path)
        except OSError:
            continue
        for label, regex in SECRET_PATTERNS:
            match = regex.search(text)
            if match:
                findings.append(
                    Finding(
                        "critical",
                        "secret",
                        str(path),
                        _line_for_offset(text, match.start()),
                        label,
                        "Potential secret material found. Value intentionally omitted.",
                        "Move secret to a private credential store, rotate if exposed, and remove from assistant config/docs.",
                    )
                )
    for path in iter_files([config.repo_root, config.projects_root], max_depth=4, suffixes={".json"}):
        if path.name.startswith("client_secret_"):
            findings.append(
                Finding(
                    "high",
                    "secret",
                    str(path),
                    None,
                    "OAuth client secret file in project tree",
                    "A Google OAuth client_secret_*.json file is present under a repo/project.",
                    "Move it to ~/.config/... and add client_secret_*.json to .gitignore.",
                )
            )
    return findings


def scan_large_state(config: WorkbenchConfig) -> list[Finding]:
    findings: list[Finding] = []
    targets = [config.codex_home / "sessions", config.codex_home / "logs_2.sqlite", config.claude_home / "projects"]
    for path in targets:
        if not path.exists():
            continue
        size = _path_size(path)
        threshold = 500_000_000 if path.is_dir() else 250_000_000
        if size > threshold:
            findings.append(
                Finding(
                    "low",
                    "performance",
                    str(path),
                    None,
                    "Large assistant state",
                    f"Path uses approximately {size / 1_000_000:.1f} MB.",
                    "Archive or rotate old sessions/logs; avoid broad searches across assistant state.",
                )
            )
    return findings


def scan_stale_doc_paths(config: WorkbenchConfig) -> list[Finding]:
    findings: list[Finding] = []
    path_regex = re.compile(r"(?P<path>(?:/Users/[A-Za-z0-9_.-]+/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+)")
    for path in iter_files([config.repo_root, config.projects_root], max_depth=5, names=DOC_NAMES):
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = read_text_limited(path)
        except OSError:
            continue
        for match in path_regex.finditer(text):
            raw = match.group("path")
            if raw.startswith("http") or raw.startswith("github.com"):
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = path.parent / raw
            if not candidate.exists() and any(part in raw for part in ("/", ".")):
                findings.append(
                    Finding(
                        "low",
                        "stale-doc",
                        str(path),
                        _line_for_offset(text, match.start()),
                        "Referenced path may be stale",
                        raw,
                        "Verify the path or update the project guidance.",
                    )
                )
                break
    return findings


def mcp_health(config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    findings = [f.to_dict() for f in scan_mcp_configs(config)]
    return {
        "ok": not any(f["severity"] in {"critical", "high"} for f in findings),
        "findings": findings,
    }


def doctor_report(config: WorkbenchConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    findings = [f.to_dict() for f in scan_all(config)]
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return {"summary": counts, "findings": findings}


def format_report(report: dict[str, Any]) -> str:
    lines = ["Agent Workbench Doctor", ""]
    summary = report.get("summary", {})
    if summary:
        lines.append("Summary: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    else:
        lines.append("Summary: no findings")
    for item in report.get("findings", []):
        loc = item["path"]
        if item.get("line"):
            loc += f":{item['line']}"
        lines.append("")
        lines.append(f"[{item['severity'].upper()}] {item['title']}")
        lines.append(f"  {loc}")
        lines.append(f"  {item['detail']}")
        lines.append(f"  Suggestion: {item['suggestion']}")
    return "\n".join(lines)


def report_json(report: dict[str, Any]) -> str:
    return dump_json(report)


def _line_for(path: Path, needle: str) -> int | None:
    try:
        return _line_for_text(read_text_limited(path), needle)
    except OSError:
        return None


def _line_for_text(text: str, needle: str) -> int | None:
    index = text.find(needle)
    if index < 0:
        return None
    return _line_for_offset(text, index)


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def _finding_sort_key(finding: Finding) -> tuple[int, str, str]:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return (severity_order.get(finding.severity, 9), finding.category, finding.path)
