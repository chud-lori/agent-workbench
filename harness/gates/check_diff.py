#!/usr/bin/env python3
"""Script-enforced Gate checks over the ADDED lines of a diff.

Checks only what a pattern can decide with few false positives:
  CR-02  a secret in code: private key header, AWS key id, GitHub token,
         Slack token
  CR-09  a swallowed failure: bare `except`/`except Exception` whose body is
         `pass`, an empty catch block, an empty `.catch(() => {})`, Go `_ = err`
         or an empty `if err != nil {}`

Override a known false positive with `gate-allow: CR-NN` on the flagged line.

Usage:
    check_diff.py                     # staged changes (git diff --cached)
    check_diff.py <range>             # e.g. origin/main...HEAD
    check_diff.py -                   # read a unified diff from stdin (gh pr diff)
    check_diff.py -C <repo> ...       # run git in another directory

Exit 0 = clean, 1 = findings, 2 = could not read the diff. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import NamedTuple

ALLOW = re.compile(r"gate-allow:\s*(CR-\d\d(?:\s*,\s*CR-\d\d)*)")

SECRET_PATTERNS = [
    ("private key", re.compile(r"-{5}BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-{5}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b(?<!EXAMPLE)")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[0-9]{6,}-[0-9A-Za-z-]{6,}")),
]

PY_BROAD_EXCEPT = re.compile(
    r"^\s*except(?:\s*\(?\s*(?:Exception|BaseException)\s*\)?(?:\s+as\s+\w+)?)?\s*:\s*(?P<body>.*?)\s*$"
)
PY_PASS = re.compile(r"^(?:pass|\.\.\.)\s*(?:#.*)?$")
CATCH_EMPTY = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}")
CATCH_OPEN = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*$")
PROMISE_CATCH_EMPTY = re.compile(r"\.catch\(\s*(?:\(\s*\w*\s*\)|\w+)\s*=>\s*\{\s*\}\s*\)")
GO_DISCARD_ERR = re.compile(r"^\s*_\s*=\s*err\s*$")
GO_EMPTY_ERR_IF = re.compile(r"\bif\s+err\s*!=\s*nil\s*\{\s*\}")

CATCH_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".kt", ".cs", ".swift")


class Line(NamedTuple):
    number: int
    text: str
    added: bool


class Finding(NamedTuple):
    path: str
    line: int
    rule: str
    message: str


def parse_diff(diff: str) -> dict[str, list[Line]]:
    """New-side lines of each file, in order, marked added or context."""
    files: dict[str, list[Line]] = {}
    path = None
    number = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            if path is not None:
                files.setdefault(path, [])
            continue
        if raw.startswith("@@"):
            match = re.match(r"@@ -\S+ \+(\d+)", raw)
            number = int(match.group(1)) if match else 0
            continue
        if path is None or raw.startswith(("--- ", "\\")):
            continue
        if raw.startswith("+"):
            files[path].append(Line(number, raw[1:], True))
            number += 1
        elif raw.startswith(" "):
            files[path].append(Line(number, raw[1:], False))
            number += 1
    return files


def _allowed(rule: str, *lines: Line) -> bool:
    for line in lines:
        match = ALLOW.search(line.text)
        if match and rule in re.split(r"\s*,\s*", match.group(1)):
            return True
    return False


def _swallowed(path: str, line: Line, following: Line | None) -> str | None:
    """A single-line swallow counts when its line was added; a two-line one when either was."""
    pair = following is not None and following.number == line.number + 1
    pair_touched = pair and (line.added or following.added)
    if path.endswith(".py"):
        match = PY_BROAD_EXCEPT.match(line.text)
        if match:
            body = match.group("body")
            if line.added and PY_PASS.match(body):
                return "broad except whose body is only pass"
            if not body and pair_touched and PY_PASS.match(following.text.strip()):
                return "broad except whose body is only pass"
    elif path.endswith(CATCH_EXTS):
        if line.added and (CATCH_EMPTY.search(line.text) or PROMISE_CATCH_EMPTY.search(line.text)):
            return "empty catch block"
        if pair_touched and CATCH_OPEN.search(line.text) and following.text.strip().startswith("}"):
            return "empty catch block"
    elif path.endswith(".go") and line.added:
        if GO_DISCARD_ERR.match(line.text):
            return "error discarded with _ = err"
        if GO_EMPTY_ERR_IF.search(line.text):
            return "empty if err != nil block"
    return None


def check(diff: str) -> list[Finding]:
    findings: list[Finding] = []
    for path, lines in parse_diff(diff).items():
        for i, line in enumerate(lines):
            following = lines[i + 1] if i + 1 < len(lines) else None
            if line.added and not _allowed("CR-02", line):
                for label, pattern in SECRET_PATTERNS:
                    if pattern.search(line.text):
                        findings.append(Finding(path, line.number, "CR-02", f"possible secret: {label}"))
            message = _swallowed(path, line, following)
            if message and not _allowed("CR-09", line, *([following] if following else [])):
                findings.append(Finding(path, line.number, "CR-09", f"swallowed failure: {message}"))
    return findings


def read_diff(target: str | None, repo: str | None) -> str:
    if target == "-":
        return sys.stdin.read()
    git = ["git"] + (["-C", repo] if repo else [])
    spec = [target] if target else ["--cached"]
    proc = subprocess.run(
        git + ["diff", "-U0", "--no-color", "--no-ext-diff", *spec],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", help="git diff range, or - for stdin; default: staged changes")
    parser.add_argument("-C", dest="repo", help="repository to run git in")
    args = parser.parse_args(argv)
    try:
        diff = read_diff(args.target, args.repo)
    except (OSError, RuntimeError) as exc:
        print(f"check_diff: cannot read diff: {exc}", file=sys.stderr)
        return 2
    findings = check(diff)
    for f in findings:
        print(f"{f.path}:{f.line}: {f.rule} {f.message}")
    if findings:
        print("Override a false positive with `gate-allow: CR-NN` in a comment on that line.", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
