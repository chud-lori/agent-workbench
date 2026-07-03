# Agent Workbench

Local workbench for Codex/Claude: setup diagnostics, an FTS code index over `~/repo`, and a persistent "brain" of durable notes. It is intentionally dependency-free — Python ≥3.10 is the only requirement; the [work-mcp](https://github.com/chud-lori/work-mcp) sidecar (Slack/Google connector MCPs, expected at `~/Projects/work-mcp` or `AGENT_WORKBENCH_WORK_MCP_ROOT`) is optional and merely reported on by `work_sources_status`.

## Commands

```bash
python -m agent_workbench doctor --all
python -m agent_workbench mcp-check
python -m agent_workbench context ~/repo/99-api-v2
python -m agent_workbench search "home value pause resume"
python -m agent_workbench brief TSUN-19634
python -m agent_workbench index                # rebuild; defaults to ~/repo
python -m agent_workbench refresh-index        # incremental
python -m agent_workbench index-status
python -m agent_workbench code-search "pause resume package"
python -m agent_workbench remember "hvl Mongo collection is 'package' (singular)" --kind fact --project 99-home-value-leads
python -m agent_workbench recall "hvl collection"
python -m agent_workbench recall --all              # include resolved notes
python -m agent_workbench resolve 3                 # mark a todo/note resolved (kept, hidden from default recall)
python -m agent_workbench export --out brain.md    # dump all notes to markdown (backup)
python -m agent_workbench forget 3
python -m agent_workbench work-sources
python -m agent_workbench mcp-server
```

From outside this directory, use the launchers (`$WORKBENCH` = path to this repo's clone):

```bash
python3 "$WORKBENCH/run_cli.py" doctor --all
python3 "$WORKBENCH/run_mcp.py"
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

Then build the index: `python3 run_cli.py index`. Optionally install the SessionStart hook (`harness/hooks/session-start.sh`) so Claude Code auto-injects recent brain notes into every session and refreshes the index in the background — see AGENTS.md → "Harness setup" step 4 for the settings.json snippet. See AGENTS.md → "Harness setup" for the full walkthrough.

## Codex MCP Config

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.agent_workbench]
command = "python3"
args = ["<path-to-agent-workbench>/run_mcp.py"]
startup_timeout_sec = 20
tool_timeout_sec = 90
enabled = true
```

## Claude MCP Config

```bash
claude mcp add agent-workbench python3 "$WORKBENCH/run_mcp.py"
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
- `brain_recall`: FTS search over notes, or recent notes when no query is given. Resolved notes are hidden unless `include_resolved` is set.
- `brain_resolve`: mark a todo/note resolved — kept for history, hidden from default recall.
- `brain_forget`: delete a note by id.
- `brain_export`: dump all notes to a markdown file (the backup story).

Orchestrator:

- `brief_task`: one call that merges code index hits, agent-doc hits, matching brain notes, likely repos, and runnable commands from those repos — the task-start context pack. External Jira/Slack/Google lookups stay with their own MCP servers.

## Notes

This tool does not call any LLM API. Codex/Claude provide the reasoning layer; Agent Workbench provides deterministic retrieval, diagnostics, and durable memory.

State lives under `<path-to-agent-workbench>/.state/` (`index.sqlite` for the code index, `brain.sqlite` for notes). The index is a snapshot — run `refresh-index` periodically (or wire it into a cron/hook; the SessionStart hook does this automatically); `code_search` and `brief_task` warn when it is older than 24 hours. For backups, `brain_export` (CLI: `export [--out PATH]`) dumps every note to markdown — check that file into a private repo or sync it wherever your backups live.
