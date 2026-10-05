#!/usr/bin/env python3
"""Reject review findings that do not carry the evidence their rule demands.

`rules.md` says every rule names its required evidence, but saying it is not
enforcing it: an unchecked rule decays into taste one review at a time. This
reads the findings a review produced and fails when a record cannot support
itself.

    python3 validate_findings.py findings.json        # or - for stdin

Stdlib only, like the rest of the workbench. Exit 0 when every record holds up,
1 when any does not, 2 when the input cannot be read.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RULES = Path(__file__).with_name("rules.md")

# Borrowed verdict vocabulary: a finding either stands with a trace, names the
# single fact that would settle it, or records something disproved.
VERDICTS = ("confirmed", "needs_validation", "rejected")

REQUIRED = {
    "confirmed": ("rule", "path", "line", "failure", "fix"),
    "needs_validation": ("rule", "path", "unresolved"),
    "rejected": ("rule", "path", "disproved_by"),
}


def known_rules(text: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^\|\s*(CR-\d{2})\s*\|", text, re.M)}


def check(record: dict, index: int, rules: set[str]) -> list[str]:
    where = record.get("path") or f"record {index}"
    errors = []

    verdict = record.get("verdict")
    if verdict not in VERDICTS:
        return [f"{where}: verdict must be one of {', '.join(VERDICTS)}, got {verdict!r}"]

    for field in REQUIRED[verdict]:
        value = record.get(field)
        if not (isinstance(value, str) and value.strip()) and not isinstance(value, int):
            errors.append(f"{where}: {verdict} record needs a non-empty {field!r}")

    rule = record.get("rule")
    if isinstance(rule, str) and rule not in rules:
        errors.append(f"{where}: cites {rule}, which is not defined in rules.md")

    # A severity on an unresolved record reads as a judgement nobody has earned.
    if verdict == "needs_validation" and record.get("severity"):
        errors.append(f"{where}: needs_validation must not carry a severity")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: validate_findings.py <findings.json|->", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text()
        records = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"cannot read findings: {exc}", file=sys.stderr)
        return 2
    if not isinstance(records, list):
        print("findings must be a JSON array (use [] for a clean review)", file=sys.stderr)
        return 2

    rules = known_rules(RULES.read_text()) if RULES.exists() else set()
    errors = [e for i, r in enumerate(records) if isinstance(r, dict) for e in check(r, i, rules)]
    errors += [f"record {i}: not an object" for i, r in enumerate(records) if not isinstance(r, dict)]

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} problem(s) in {len(records)} finding(s)", file=sys.stderr)
        return 1
    print(f"{len(records)} finding(s) validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
