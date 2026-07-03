# Agent Workbench (local MCP: `agent-workbench` / `agent_workbench`)

Local MCP with a code index over your repo root, persistent cross-tool memory ("brain"), and AI-setup diagnostics. Full guide: `AGENTS.md` in the agent-workbench repo. CLI fallback: `python3 <path-to-agent-workbench>/run_cli.py`.

- At the start of a nontrivial ticket/feature task, call `brief_task` with the ticket key or feature phrase — it returns likely repos, code/doc hits, saved brain notes, and repo commands in one call.
- When you learn a durable fact, decision, or gotcha during work (schema quirks, deploy steps, API behaviors, conventions), store it with `brain_remember` (kind: decision|fact|gotcha|preference|todo|note; project: repo dir name; short tags). Never store secrets or facts trivially derivable from code.
- Before re-deriving past decisions or cross-repo conventions, check `brain_recall`.
- On a stale-index warning from `code_search`/`brief_task`, run `refresh_code_index`.
- Setup misbehaving? `doctor_report` (secrets/config/permissions), `mcp_health` (MCP configs), `work_sources_status` (work connector health).
