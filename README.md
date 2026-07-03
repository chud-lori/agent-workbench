# Agent Workbench

Local workbench for Codex/Claude: setup diagnostics, an FTS code index over `~/repo`, and a persistent "brain" of durable notes. It is intentionally dependency-free.

## Commands

```bash
python -m agent_workbench doctor --all
python -m agent_workbench mcp-check
python -m agent_workbench context /Users/nurchudlori/repo/99-api-v2
python -m agent_workbench search "home value pause resume"
python -m agent_workbench brief TSUN-19634
python -m agent_workbench index                # rebuild; defaults to ~/repo
python -m agent_workbench refresh-index        # incremental
python -m agent_workbench index-status
python -m agent_workbench code-search "pause resume package"
python -m agent_workbench remember "hvl Mongo collection is 'package' (singular)" --kind fact --project 99-home-value-leads
python -m agent_workbench recall "hvl collection"
python -m agent_workbench forget 3
python -m agent_workbench work-sources
python -m agent_workbench mcp-server
```

From outside this directory, use the launchers:

```bash
python3 /Users/nurchudlori/Projects/agent-workbench/run_cli.py doctor --all
python3 /Users/nurchudlori/Projects/agent-workbench/run_mcp.py
```

## Index roots

The code index scans **only `~/repo`** by default. Override with:

- `AGENT_WORKBENCH_INDEX_ROOTS` — colon- or comma-separated list of roots, e.g. `~/repo:~/Projects`
- explicit `roots` argument to `index` / `refresh-index` (CLI) or `rebuild_code_index` / `refresh_code_index` (MCP)

`AGENT_WORKBENCH_REPO_ROOT` still moves the repo root itself. The doctor scan intentionally keeps covering both `~/repo` and `~/Projects` for secrets/config hygiene.

## Harness setup

Agent guidance ships with the repo: `AGENTS.md` (canonical guide, incl. per-machine setup), `CLAUDE.md` (imports AGENTS.md), and `SKILL.md`. Any agent working *in* this repo picks these up automatically.

To make **every** session on a machine use the workbench (any repo, any harness), register the MCP server (below) and append the shared snippet to your global instruction file:

```bash
cat harness/standing-instructions.md >> ~/.claude/CLAUDE.md   # Claude Code
cat harness/standing-instructions.md >> ~/.codex/AGENTS.md    # Codex
cat harness/standing-instructions.md >> ~/.gemini/GEMINI.md   # Gemini CLI
```

Then build the index: `python3 run_cli.py index`. See AGENTS.md → "Harness setup" for the full walkthrough.

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

## Claude MCP Config

```bash
claude mcp add agent-workbench python3 /Users/nurchudlori/Projects/agent-workbench/run_mcp.py
```

## MCP Tools

Diagnostics:

- `doctor_report`: local setup diagnostics (secrets, MCP config, broad permissions, stale docs).
- `mcp_health`: MCP command/config checks.
- `work_sources_status`: connector health for Slack/Google/Atlassian MCPs without exposing secrets.

Code index (SQLite FTS over `~/repo`):

- `rebuild_code_index` / `refresh_code_index`: full or incremental index build.
- `index_status`: repo/document counts and index age.
- `code_search`: bm25 keyword search across indexed repos (warns when the index is stale).
- `codebase_overview`: languages, package files, and docs per indexed repo.
- `search_knowledge`: live search over agent docs (CLAUDE.md, AGENTS.md, SKILL.md, READMEs).
- `find_service_context`: likely repo/service context and commands for a service name.

Brain (persistent memory in `.state/brain.sqlite`):

- `brain_remember`: store a durable note (`decision`, `fact`, `gotcha`, `preference`, `todo`, `note`) with optional project/tags.
- `brain_recall`: FTS search over notes, or recent notes when no query is given.
- `brain_forget`: delete a note by id.

Orchestrator:

- `brief_task`: one call that merges code index hits, agent-doc hits, matching brain notes, likely repos, and runnable commands from those repos — the task-start context pack. External Jira/Slack/Google lookups stay with their own MCP servers.

## Notes

This tool does not call any LLM API. Codex/Claude provide the reasoning layer; Agent Workbench provides deterministic retrieval, diagnostics, and durable memory.

State lives under `/Users/nurchudlori/Projects/agent-workbench/.state/` (`index.sqlite` for the code index, `brain.sqlite` for notes). The index is a snapshot — run `refresh-index` periodically (or wire it into a cron/hook); `code_search` and `brief_task` warn when it is older than 24 hours.
