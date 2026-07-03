---
name: agent-workbench
description: Use the agent-workbench MCP for task-start context briefs, persistent cross-tool memory (brain_remember/brain_recall), local code search over ~/repo, and AI-setup diagnostics. Trigger at the start of any nontrivial ticket/feature task, when a durable fact/decision/gotcha is learned, or when local MCP/agent setup misbehaves.
---

# Agent Workbench Skill

Local MCP server (`agent-workbench` in Claude, `agent_workbench` in Codex) providing deterministic retrieval and durable memory. No LLM calls.

## Workflow

1. **Task start** — call `brief_task` with the ticket key or feature phrase. Returns likely repos, code hits, agent-doc hits, matching brain notes, and runnable commands in one call. Prefer this over manual grepping across repos.
2. **During work** — when you learn something durable (schema quirk, deploy step, API behavior, decision), persist it:
   `brain_remember(content, kind=decision|fact|gotcha|preference|todo|note, project=<repo-dir-name>, tags=[...])`.
   Every note must include a source reference: ticket key, Slack channel + date, doc name, file path, or a GitHub permalink pinned to a commit SHA (`repo@sha path:line`). Never store secrets or facts trivially derivable from code.
3. **Recall** — before re-deriving past decisions or conventions: `brain_recall(query)` or filter by `project`/`kind`. Mark finished todos with `brain_resolve(id)` (hidden from default recall; `include_resolved` shows them). Back up all notes with `brain_export`.
4. **Index hygiene** — on a stale-index warning, run `refresh_code_index`. Check freshness with `index_status`.
5. **Troubleshooting** — `doctor_report` (setup/secrets/permissions), `mcp_health` (MCP configs), `work_sources_status` (Slack/Google/Atlassian connector health).

## CLI equivalents

Run from the agent-workbench repo root (or use its absolute path):

```bash
python3 run_cli.py brief "TICKET-1234"
python3 run_cli.py remember "..." --kind fact --project my-api
python3 run_cli.py recall "pause resume"
python3 run_cli.py refresh-index
```

## Machine not set up yet?

Follow **Harness setup** in AGENTS.md: register the MCP (`claude mcp add` / Codex `config.toml` / Gemini `settings.json`), then append `harness/standing-instructions.md` to your global instruction file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or `~/.gemini/GEMINI.md`), then run `python3 run_cli.py index`.
