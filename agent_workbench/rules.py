"""Contextual rules: behaviour learned from a correction, replayed when the context returns.

A brain note answers "what is true". A rule answers "how to behave here", and
"here" is the point: the same situation can need a different rule in a
different context. Rules are therefore retrieved by scope match, never by text
similarity, which is why they live in a plain table rather than the FTS one.
"""

from __future__ import annotations

import re
import sqlite3
import time
from typing import Any

from .brain import _connect, _iso
from .config import WorkbenchConfig, default_config


# Ordering declared in issue #22: a repo rule beats a workstream rule, which
# beats a global one. Only used to break a tie between rules that matched the
# same number of keys.
KEY_PRECEDENCE = ("repo", "workstream", "task", "audience", "channel")

GLOBAL_SCOPE = "global"
FEEDBACK_OUTCOMES = ("corrected", "retire")

# Two statements this close are the same rule restated, so a repeat correction
# sharpens the existing rule instead of stacking a near-duplicate beside it.
_SIMILAR_RATIO = 0.6
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*:[^\s]+$")

RULES_SCHEMA = """
        create table if not exists rules(
            id integer primary key,
            statement text not null,
            why text,
            example text,
            scope text not null default 'global',
            trigger text,
            source text,
            created_at integer not null,
            updated_at integer,
            surfaced_count integer not null default 0,
            last_surfaced_at integer,
            corrected_count integer not null default 0,
            last_corrected_at integer,
            retired_at integer
        )
"""


def remember_rule(
    statement: str,
    scope: list[str] | str | None = None,
    why: str | None = None,
    example: str | None = None,
    trigger: list[str] | str | None = None,
    source: str | None = None,
    config: WorkbenchConfig | None = None,
) -> dict[str, Any]:
    """Store a rule, or sharpen the one it restates.

    A correction repeated in the same context is evidence about one rule, not
    two, so it amends: the example is kept and the rule is re-dated.
    """
    statement = (statement or "").strip()
    if not statement:
        return {"stored": False, "error": "statement is required"}
    config = config or default_config()
    keys, bad = _normalise_scope(scope)
    if bad:
        return {
            "stored": False,
            "error": f"scope keys must look like type:value (got {', '.join(bad)})",
            "known_types": list(KEY_PRECEDENCE),
        }
    scope_text = " ".join(keys) if keys else GLOBAL_SCOPE
    trigger_text = " ".join(_tokens(trigger)) or None
    now = int(time.time())
    config.workbench_home.mkdir(parents=True, exist_ok=True)
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(RULES_SCHEMA)
        twin = _find_twin(conn, statement, scope_text)
        if twin is not None:
            merged_example = twin["example"] or example
            if twin["example"] and example and example.strip() not in twin["example"]:
                merged_example = f"{twin['example']}\n{example.strip()}"
            conn.execute(
                "update rules set statement=?, why=coalesce(?, why), example=?, "
                "trigger=coalesce(?, trigger), source=coalesce(?, source), updated_at=? where id=?",
                (statement, why, merged_example, trigger_text, source, now, twin["id"]),
            )
            conn.commit()
            return {
                "id": twin["id"],
                "stored": True,
                "amended": True,
                "scope": scope_text,
                "note": "a rule this close already governed this scope, so it was sharpened rather than duplicated",
            }
        cursor = conn.execute(
            "insert into rules(statement, why, example, scope, trigger, source, created_at, updated_at) "
            "values (?, ?, ?, ?, ?, ?, ?, ?)",
            (statement, why, example, scope_text, trigger_text, source, now, now),
        )
        conn.commit()
        result: dict[str, Any] = {
            "id": cursor.lastrowid,
            "stored": True,
            "amended": False,
            "scope": scope_text,
            "specificity": len(keys),
        }
        if not keys:
            result["warning"] = (
                "stored as global, so it applies everywhere. If the correction only holds in one repo, "
                "workstream or audience, re-store it with that scope — a global rule that is wrong "
                "somewhere gets ignored everywhere."
            )
        return result
    finally:
        conn.close()


def rules_in_force(
    prompt: str | None = None,
    context: list[str] | str | None = None,
    project: str | None = None,
    limit: int = 10,
    config: WorkbenchConfig | None = None,
) -> dict[str, Any]:
    """The rules that govern the active context, most specific first.

    A rule applies when every key in its scope is active, so a context that
    declares both `repo:x` and `workstream:y` inherits the rules of each. That
    is the whole inheritance mechanism: no parent pointers, just the key set.
    """
    config = config or default_config()
    active, bad = _normalise_scope(context)
    if project:
        active = sorted(set(active) | {f"repo:{project}"})
    if bad:
        return {"rules": [], "error": f"context keys must look like type:value (got {', '.join(bad)})"}
    if not config.brain_path.exists():
        return {"active_context": active, "rules": [], "warning": "no rules stored yet"}
    prompt_tokens = set(_tokens(prompt))
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(RULES_SCHEMA)
        rows = conn.execute("select * from rules where retired_at is null").fetchall()
        scored: list[tuple[tuple[int, int], dict[str, Any]]] = []
        active_set = set(active)
        for row in rows:
            keys = [] if row["scope"] == GLOBAL_SCOPE else row["scope"].split()
            scope_hit = all(key in active_set for key in keys)
            trigger_hit = bool(prompt_tokens & set((row["trigger"] or "").split()))
            if not (scope_hit or trigger_hit):
                continue
            scored.append((_specificity(keys), _rule_dict(row, scope_hit=scope_hit, trigger_hit=trigger_hit)))
        scored.sort(key=lambda pair: (pair[0], pair[1].get("updated_at") or 0), reverse=True)
        chosen = [rule for _, rule in scored[:limit]]
        _record_surfaced(conn, [rule["id"] for rule in chosen])
        result: dict[str, Any] = {"active_context": active, "rules": chosen}
        if chosen:
            # Every rule returned is in force; they govern different things. The
            # ordering only decides between rules about the SAME situation, so
            # that is the only case reported as a conflict.
            result["precedence"] = "most specific scope first; a tie falls to the highest-ranked key type, then the newest rule"
            clashes = _clashes(scored[:limit])
            if clashes:
                result["conflicts"] = clashes
                result["hint"] = (
                    "these rules are equally specific and say overlapping things — follow the one listed first, "
                    "say so, and narrow the scope of the other"
                )
        return result
    finally:
        conn.close()


def rule_feedback(rule_id: int, outcome: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """Record that a rule failed, or retire it.

    There is deliberately no "applied" outcome. Whether the model truly obeyed
    a rule is self-reported, and self-reported compliance is not evidence; what
    can be measured is that the rule was surfaced and that the user then had to
    correct the output anyway.
    """
    if outcome not in FEEDBACK_OUTCOMES:
        return {"id": rule_id, "recorded": False, "error": f"outcome must be one of {', '.join(FEEDBACK_OUTCOMES)}"}
    config = config or default_config()
    if not config.brain_path.exists():
        return {"id": rule_id, "recorded": False, "warning": "no rules stored yet"}
    now = int(time.time())
    conn = _connect(config)
    try:
        conn.execute(RULES_SCHEMA)
        if outcome == "retire":
            cursor = conn.execute("update rules set retired_at=? where id=? and retired_at is null", (now, rule_id))
        else:
            cursor = conn.execute(
                "update rules set corrected_count = corrected_count + 1, last_corrected_at=? where id=?",
                (now, rule_id),
            )
        conn.commit()
        return {"id": rule_id, "recorded": cursor.rowcount > 0, "outcome": outcome}
    finally:
        conn.close()


def context_view(key: str, config: WorkbenchConfig | None = None) -> dict[str, Any]:
    """Everything the workbench knows about behaving in one context.

    Health flags are the reason this view exists: a rule nobody has ever been
    shown is probably mis-scoped, and one that keeps being corrected after it
    was shown is probably wrong.
    """
    key = (key or "").strip()
    if not _KEY_RE.match(key):
        return {"context": key, "error": "context key must look like type:value, e.g. repo:my-service"}
    config = config or default_config()
    if not config.brain_path.exists():
        return {"context": key, "rules": [], "warning": "no rules stored yet"}
    conn = _connect(config)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(RULES_SCHEMA)
        rows = conn.execute("select * from rules where retired_at is null").fetchall()
        rules = [
            _rule_dict(row, scope_hit=True, trigger_hit=False)
            for row in rows
            if row["scope"] == GLOBAL_SCOPE or key in row["scope"].split()
        ]
        rules.sort(key=lambda rule: (rule["specificity"], rule.get("updated_at") or 0), reverse=True)
        never = [rule["id"] for rule in rules if not rule.get("surfaced_count")]
        failing = [rule["id"] for rule in rules if rule.get("corrected_count", 0) >= 2]
        result: dict[str, Any] = {"context": key, "rules": rules}
        if never:
            result["never_surfaced"] = never
            result["never_surfaced_hint"] = "never shown in this context — likely scoped to keys that never co-occur"
        if failing:
            result["failing"] = failing
            result["failing_hint"] = "corrected more than once after being shown — the rule itself is probably wrong"
        return result
    finally:
        conn.close()


def _normalise_scope(scope: list[str] | str | None) -> tuple[list[str], list[str]]:
    raw = _tokens(scope)
    keys = [item for item in raw if item != GLOBAL_SCOPE]
    bad = [item for item in keys if not _KEY_RE.match(item)]
    return sorted(set(keys)), bad


def _tokens(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    items = value.split() if isinstance(value, str) else [str(item) for item in value]
    return [item.strip().lower() for item in items if item and item.strip()]


def _specificity(keys: list[str]) -> tuple[int, int]:
    """More matched keys wins; a tie falls to the highest-ranked key type."""
    if not keys:
        return (0, -1)
    ranks = [
        len(KEY_PRECEDENCE) - KEY_PRECEDENCE.index(key.split(":", 1)[0])
        if key.split(":", 1)[0] in KEY_PRECEDENCE
        else 0
        for key in keys
    ]
    return (len(keys), max(ranks))


def _find_twin(conn: sqlite3.Connection, statement: str, scope_text: str) -> sqlite3.Row | None:
    wanted = set(_tokens(statement))
    if not wanted:
        return None
    for row in conn.execute("select * from rules where scope=? and retired_at is null", (scope_text,)):
        existing = set(_tokens(row["statement"]))
        if not existing:
            continue
        overlap = len(wanted & existing) / max(len(wanted), len(existing))
        if overlap >= _SIMILAR_RATIO:
            return row
    return None


def _clashes(scored: list[tuple[tuple[int, int], dict[str, Any]]]) -> list[list[int]]:
    """Groups of equally-specific rules whose statements overlap.

    Two rules of equal standing that say different things are not a conflict,
    they are two rules. Only an overlapping statement is ambiguous.
    """
    groups: list[list[int]] = []
    for index, (score, rule) in enumerate(scored):
        tokens = set(_tokens(rule["statement"]))
        rivals = [
            other["id"]
            for other_score, other in scored[index + 1 :]
            if other_score == score
            and tokens
            and len(tokens & set(_tokens(other["statement"]))) / max(len(tokens), len(set(_tokens(other["statement"])))) >= _SIMILAR_RATIO
        ]
        if rivals:
            groups.append([rule["id"], *rivals])
    return groups


def _record_surfaced(conn: sqlite3.Connection, rule_ids: list[int]) -> None:
    """Count an exposure, best effort — same discipline as recall telemetry."""
    if not rule_ids:
        return
    now = int(time.time())
    try:
        conn.executemany(
            "update rules set surfaced_count = surfaced_count + 1, last_surfaced_at=? where id=?",
            [(now, rule_id) for rule_id in rule_ids],
        )
        conn.commit()
    except sqlite3.Error:
        pass


def _rule_dict(row: sqlite3.Row, *, scope_hit: bool, trigger_hit: bool) -> dict[str, Any]:
    keys = [] if row["scope"] == GLOBAL_SCOPE else row["scope"].split()
    rule = {
        "id": row["id"],
        "statement": row["statement"],
        "scope": row["scope"],
        "specificity": len(keys),
        "matched_by": "scope" if scope_hit else "trigger",
    }
    for field in ("why", "example", "source", "trigger"):
        if row[field]:
            rule[field] = row[field]
    for field in ("surfaced_count", "corrected_count"):
        if row[field]:
            rule[field] = row[field]
    for field in ("updated_at", "last_surfaced_at", "last_corrected_at"):
        if row[field]:
            rule[field] = row[field]
            rule[f"{field}_iso"] = _iso(row[field])
    if trigger_hit and not scope_hit:
        rule["note"] = "matched on a trigger word, not on the active context"
    return rule
