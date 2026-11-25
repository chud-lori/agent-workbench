#!/usr/bin/env python3
"""Reject a subagent return whose records cannot name their evidence.

A subagent hands the parent prose, and prose reads the same whether a claim was
checked or guessed. Measured in this repo: across 211 local subagent
transcripts, 208 could reach the brain, 5 called recall, and 0 ever had a note
injected. The parent cannot see any of that from a confident paragraph.

So each agent type declares a schema in its own markdown, and the parent runs
this before it believes anything:

    python3 validate_return.py scout return.txt     # or - for stdin

The input may be the agent's raw reply; the last ```json fence in it is used.
Stdlib only, like the rest of the workbench. Exit 0 when every record holds up,
1 when any does not, 2 when the input or schema cannot be read.

A single bad record fails the whole return. Dropping it instead would lose work
silently, which is the exact failure this exists to prevent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

AGENTS_DIR = Path(__file__).resolve().parent

_SCHEMA_FENCE = re.compile(r"```returns-schema\s*\n(.*?)```", re.S)
_JSON_FENCE = re.compile(r"```json\s*\n(.*?)```", re.S)

SCHEMA_KEYS = ("record", "required", "evidence_any_of")


def load_schema(agent: str) -> dict[str, Any]:
    path = AGENTS_DIR / f"{agent}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no agent type named {agent!r} in {AGENTS_DIR}")
    match = _SCHEMA_FENCE.search(path.read_text())
    if not match:
        raise ValueError(f"{path.name} declares no ```returns-schema block")
    schema = json.loads(match.group(1))
    missing = [key for key in SCHEMA_KEYS if key not in schema]
    if missing:
        raise ValueError(f"{path.name} schema is missing {', '.join(missing)}")
    return schema


def extract_records(text: str) -> Any:
    """The payload, from raw JSON or from the last ```json fence in a reply."""
    text = text.strip()
    if not text:
        raise ValueError("empty return")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fences = _JSON_FENCE.findall(text)
    if not fences:
        raise ValueError("no JSON object and no ```json fence in the return")
    return json.loads(fences[-1])


def _filled(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and bool(value.strip())


def check_record(record: Any, index: int, schema: dict[str, Any]) -> list[str]:
    label = schema["record"]
    if not isinstance(record, dict):
        return [f"{label} {index}: must be an object, got {type(record).__name__}"]
    where = f"{label} {index}"
    errors: list[str] = []

    for field in schema["required"]:
        if not _filled(record.get(field)):
            errors.append(f"{where}: needs a non-empty {field!r}")

    for field, allowed in (schema.get("enums") or {}).items():
        value = record.get(field)
        if _filled(value) and value not in allowed:
            errors.append(f"{where}: {field}={value!r} is not one of {', '.join(allowed)}")

    evidence = schema["evidence_any_of"]
    if evidence and not any(_filled(record.get(field)) for field in evidence):
        errors.append(
            f"{where}: names no evidence — needs one of {', '.join(evidence)}. "
            "A claim the parent cannot trace is a guess with a sentence around it."
        )

    unknown = set(record) - set(schema["required"]) - set(schema.get("optional") or []) - set(evidence)
    unknown -= set((schema.get("enums") or {}))
    if unknown:
        errors.append(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")

    return errors


def validate(agent: str, text: str) -> list[str]:
    schema = load_schema(agent)
    payload = extract_records(text)
    if isinstance(payload, dict):
        records = payload.get("records")
        if records is None:
            return ['return object has no "records" key']
    else:
        records = payload
    if not isinstance(records, list):
        return [f'"records" must be a list, got {type(records).__name__}']
    if not records:
        if schema.get("allow_empty"):
            return []
        return [f"{schema['record']} list is empty, and this agent may not return nothing"]
    errors: list[str] = []
    for index, record in enumerate(records):
        errors.extend(check_record(record, index, schema))
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: validate_return.py <agent> <file|->", file=sys.stderr)
        return 2
    agent, source = argv
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text()
    except OSError as exc:
        print(f"cannot read {source}: {exc}", file=sys.stderr)
        return 2
    try:
        errors = validate(agent, text)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"cannot validate: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"{len(errors)} problem(s): the whole return is rejected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
