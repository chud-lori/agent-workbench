---
name: agent-workbench
description: Use the agent-workbench MCP for task-start context briefs, persistent cross-tool memory (brain_remember/brain_recall/brain_amend), contextual rules learned from corrections (brain_rule_remember/brain_rules_in_force), local code search, git activity across every local repo, deployed-vs-local checks, and AI-setup diagnostics. Trigger at the start of any nontrivial ticket/feature task, when a durable fact/decision/gotcha is learned, before claiming how production behaves, or when local MCP/agent setup misbehaves.
---

# Agent Workbench Skill

Local MCP server (`agent-workbench` in Claude, `agent_workbench` in Codex) providing deterministic retrieval and durable memory. No LLM calls.

## Workflow

1. **Task start** — call `brief_task` with the ticket key or feature phrase. Returns likely repos, code hits, agent-doc hits, matching brain notes, and runnable commands in one call. Prefer this over manual grepping across repos.
2. **During work** — when you learn something durable (schema quirk, deploy step, API behavior, decision), persist it:
   `brain_remember(content, kind=decision|fact|gotcha|preference|todo|note, project=<repo-dir-name>, tags=[...])`.
   Every note must include a source reference: ticket key, Slack channel + date, doc name, file path, or a GitHub permalink pinned to a commit SHA (`repo@sha path:line`). Never store secrets or facts trivially derivable from code.
3. **Recall** — before re-deriving past decisions or conventions: `brain_recall(query)`, or filter by `project`/`kind`. Every hit is counted: a note's `recall_count` and `last_recalled_at` are stamped, and a note that keeps proving useful outranks an equally-matching note nobody has opened. `thread=<key>` gives a chronological digest of one storyline; `since=`/`until=` bound by when a note was stored. Mark finished todos with `brain_resolve(id)` (hidden from default recall; `include_resolved` shows them). Back up all notes with `brain_export`.
4. **A correction about behaviour is a rule, not a fact** — when the user corrects *how you acted* rather than what you knew, store it with
   `brain_rule_remember(statement, scope=[...], why, example, trigger, source)`. Scope it as narrowly as the correction warrants: `repo:x`, `workstream:y`, `task:z`, `audience:qa`, `channel:c`. A global rule applies everywhere, and one that is wrong somewhere gets ignored everywhere. Restating a rule already in the same scope sharpens it instead of duplicating it.
5. **Rules arrive by context, not by wording** — `brain_rules_in_force(prompt, context=[...], project)` returns the rules governing where you are, most specific first. A rule applies when *every* key in its scope is active, which is also how one context inherits another's rules. Equally specific rules whose statements overlap come back as `conflicts`: follow the first and say which. `brain_context(key)` shows one context's rules plus which have never surfaced there (mis-scoped) or keep being corrected after being shown (wrong). Record a failure with `brain_rule_feedback(id, "corrected")`.
6. **Correct, don't contradict** — when new knowledge corrects an earlier note, `brain_amend(id, ...)` (dated addendum or replace) or re-store with `supersedes=[ids]`. Never stack contradicting notes. `brain_promote` moves a proven personal note into a team playbook.
7. **Activity, not memory** — the brain holds durable facts, *not* an activity log. "What did I do yesterday?" is `recent_activity` (commits across every local repo, all branches, so unpushed work still shows; linked worktrees fold into their main checkout so nothing is double-counted) merged with Slack, calendar, and PRs — that is what the `/standup` skill does.
8. **Before prod claims** — run `repo_state` on the repo. Local checkouts often sit on feature branches with undeployed changes, and it will tell you when you are standing in a linked worktree whose branch differs from the indexed checkout.
9. **Index hygiene** — on a stale-index warning, run `refresh_code_index`. Check freshness with `index_status`.
10. **Troubleshooting** — `doctor_report` (setup/secrets/permissions), `mcp_health` (MCP configs), `work_sources_status` (connector health).

## Delegating to subagents

A subagent gets **no** hooks — no brain priming, no prompt-recall injection — and inherits none of your context, so it re-derives what you already know unless you hand it over. Paste established findings as evidence (`file:line`, the actual snippet, `brain#id`), say what is settled and off-limits, and prefer the brain-primed agent types (`scout`, `implementer`, `adversary`) which recall before they act.

**Check the return before you believe it.** Each type declares a `returns-schema` block in its own markdown and ends its reply with a matching `json` block. Validate it before acting on anything in it:

```bash
python3 harness/agents/validate_return.py scout - <<< "$reply"
```

Every record must name its evidence — `path`, `brain_id`, `commit`, or for an implementer the verification command and what it actually printed. A record that names none is rejected, because a claim you cannot trace is a guess with a sentence around it. One bad record rejects the whole return rather than being dropped quietly. An empty record list is legal only for `adversary`, where finding no bug is a real answer.

## CLI equivalents

Run from the agent-workbench repo root (or use its absolute path):

```bash
python3 run_cli.py brief "TICKET-1234"
python3 run_cli.py remember "..." --kind fact --project my-api
python3 run_cli.py recall "pause resume"
python3 run_cli.py rule "only test what the upgrade changed" --scope workstream:runtime-upgrade
python3 run_cli.py rules --context audience:qa
python3 run_cli.py rule-context audience:qa
python3 run_cli.py activity --since yesterday
python3 run_cli.py refresh-index
```

## Machine not set up yet?

Follow **Harness setup** in AGENTS.md: register the MCP (`claude mcp add` / Codex `config.toml` / Gemini `settings.json`), then append `harness/standing-instructions.md` to your global instruction file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or `~/.gemini/GEMINI.md`), then run `python3 run_cli.py index`.
