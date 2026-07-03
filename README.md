# Agent Workbench

Local workbench for Codex/Claude setup health and task context. It is intentionally dependency-free for the MVP.

## Commands

```bash
python -m agent_workbench doctor --all
python -m agent_workbench mcp-check
python -m agent_workbench context /Users/nurchudlori/repo/99-api-v2
python -m agent_workbench search "home value pause resume"
python -m agent_workbench brief TSUN-19634
python -m agent_workbench index /Users/nurchudlori/repo/99-home-value-leads
python -m agent_workbench refresh-index
python -m agent_workbench code-search "pause resume package"
python -m agent_workbench work-brief TSUN-19634
python -m agent_workbench work-sources
python -m agent_workbench work-bridge TSUN-19634
python -m agent_workbench mcp-server
```

From outside this directory, use the launchers:

```bash
python3 /Users/nurchudlori/Projects/agent-workbench/run_cli.py doctor --all
python3 /Users/nurchudlori/Projects/agent-workbench/run_mcp.py
```

## Codex MCP Config

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.agent_workbench]
command = "python3"
args = ["/Users/nurchudlori/Projects/agent-workbench/run_mcp.py"]
startup_timeout_sec = 20
tool_timeout_sec = 90
enabled = true
```

Run from this project directory, or install editable:

```bash
python3 -m pip install -e /Users/nurchudlori/Projects/agent-workbench
```

## Claude MCP Config

```bash
claude mcp add agent-workbench python3 /Users/nurchudlori/Projects/agent-workbench/run_mcp.py
```

## MCP Tools

- `doctor_report`: local setup diagnostics.
- `mcp_health`: MCP command/config checks.
- `search_knowledge`: search repo docs and assistant context files.
- `brief_task`: return a task-ready context brief for a query or ticket.
- `find_service_context`: summarize likely context for a repo/service.
- `rebuild_code_index`: rebuild local SQLite FTS index for code/product docs.
- `refresh_code_index`: incrementally refresh local SQLite FTS index and skip unchanged files.
- `code_search`: search the local code/product index.
- `codebase_overview`: summarize indexed repos, package files, and docs.
- `brief_work_item`: combine indexed local context with a Jira/Slack/Google MCP query plan.
- `work_sources_status`: inspect configured work MCP sources without exposing secrets.
- `work_mcp_bridge`: inspect the `work-mcp` sidecar repo, connector commands, and external MCP query plan.
- `external_source_plan`: return recommended Jira/Slack/Google MCP calls for a query.

## work-mcp Bridge

Agent Workbench intentionally stays separate from `/Users/nurchudlori/Projects/work-mcp`.

```text
Codex/Claude
  -> agent_workbench: local repo/product index, task briefs, MCP health
  -> slack: Slack connector from work-mcp
  -> google_workspace_local: Google Workspace connector from work-mcp
  -> atlassian: hosted Jira/Confluence MCP
```

This keeps connector credentials in the existing sidecar MCP setup. Agent Workbench only reports connector health, launch commands, git remote status, and recommended external MCP calls. It does not copy Slack tokens, Google OAuth files, or Atlassian auth state.

## Notes

This tool does not call any LLM API. Codex/Claude provide the reasoning layer through your logged-in session; Agent Workbench provides deterministic retrieval and diagnostics through CLI/MCP.

The index is a local, source-aware retrieval layer, not a generic LLM RAG service. It stores repo/product docs and selected code files in SQLite FTS under `/Users/nurchudlori/Projects/agent-workbench/.state/index.sqlite`. Use Codex/Claude to synthesize the retrieved context.
