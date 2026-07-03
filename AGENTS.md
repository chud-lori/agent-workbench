# Agent Workbench — Agent Guide

Local, dependency-free MCP server + CLI: FTS code index over `~/repo`, persistent cross-tool memory ("brain"), and local AI-setup diagnostics. No LLM calls; deterministic retrieval only.

Registered MCP names: `agent-workbench` (Claude Code), `agent_workbench` (Codex).
CLI fallback: `python3 <path-to-agent-workbench>/run_cli.py <command>` (this repo's root).

New machine? See **Harness setup** below to register the MCP and install the standing instructions into your own harness configs.

## Standing instructions (any harness, any repo)

1. **Task start**: for a nontrivial ticket/feature/bug, call `brief_task` with the ticket key or feature phrase first. It returns likely repos, code hits, doc hits, saved brain notes, and runnable repo commands in one call — use it before grepping manually.
2. **Store durable knowledge**: when you learn something durable during work — schema quirks, deploy steps, API behaviors, tricky conventions, decisions made with the user — save it with `brain_remember`:
   - `kind`: `decision` | `fact` | `gotcha` | `preference` | `todo` | `note`
   - `project`: repo directory name (e.g. `99-home-value-leads`)
   - `tags`: short keywords for recall
   - Every note must include a source reference — a ticket key, Slack channel + date, doc name, or file path. Notes without breadcrumbs are dead ends.
   - Never store secrets, tokens, or anything trivially derivable from the code itself.
3. **Recall before re-deriving**: before answering questions about past decisions or cross-repo conventions, check `brain_recall` (query, or filter by `project`/`kind`). When a stored todo is done, mark it with `brain_resolve` (do not forget it — history matters); resolved notes are hidden from default recall unless you pass `include_resolved`. Back up the brain with `brain_export`.
4. **Index freshness**: if `code_search`/`brief_task` warn the index is stale, run `refresh_code_index` (incremental, fast). `rebuild_code_index` only after changing index roots.
5. **Diagnostics**: `doctor_report` when local AI setup misbehaves (secrets hygiene, MCP config, permissions); `mcp_health` for MCP config checks; `work_sources_status` when the Slack/Google/Atlassian connector MCPs misbehave.

## Tool map

| Tool | Use |
|---|---|
| `brief_task` | one-call task context pack (code + docs + brain + commands) |
| `brain_remember` / `brain_recall` / `brain_forget` | persistent cross-session, cross-tool memory |
| `brain_resolve` | mark a todo/note resolved (hidden from default recall; `include_resolved` shows it) |
| `brain_export` | dump all brain notes to markdown (backup) |
| `code_search` | bm25 keyword search over indexed repos |
| `codebase_overview` | languages/package files/docs per indexed repo |
| `search_knowledge` | live search over CLAUDE.md/AGENTS.md/SKILL.md/READMEs |
| `find_service_context` | locate repo + commands for a service name |
| `rebuild_code_index` / `refresh_code_index` / `index_status` | manage the index |
| `doctor_report` / `mcp_health` / `work_sources_status` | diagnostics |

## Harness setup (per user machine)

Everything below assumes this repo is cloned at `$WORKBENCH` (e.g. `~/Projects/agent-workbench`).

**1. Register the MCP server:**

```bash
# Claude Code (user scope = all projects)
claude mcp add --scope user agent-workbench python3 "$WORKBENCH/run_mcp.py"

# Codex — add to ~/.codex/config.toml
[mcp_servers.agent_workbench]
command = "python3"
args = ["<WORKBENCH>/run_mcp.py"]
startup_timeout_sec = 20
tool_timeout_sec = 90
enabled = true

# Gemini CLI — add to ~/.gemini/settings.json under "mcpServers"
"agent-workbench": { "command": "python3", "args": ["<WORKBENCH>/run_mcp.py"] }
```

**2. Install the standing instructions** so every session uses the workbench without being asked. Append `harness/standing-instructions.md` to your harness's global instruction file:

```bash
cat "$WORKBENCH/harness/standing-instructions.md" >> ~/.claude/CLAUDE.md   # Claude Code
cat "$WORKBENCH/harness/standing-instructions.md" >> ~/.codex/AGENTS.md   # Codex
cat "$WORKBENCH/harness/standing-instructions.md" >> ~/.gemini/GEMINI.md  # Gemini CLI
```

**3. Point it at your code and build the index:**

```bash
export AGENT_WORKBENCH_REPO_ROOT=~/repo            # where your work repos live (default ~/repo)
export AGENT_WORKBENCH_INDEX_ROOTS=~/repo          # optional: extra roots, colon-separated
python3 "$WORKBENCH/run_cli.py" index
```

Set the env vars in your shell profile if you change the defaults; the MCP server reads them at launch.

**4. Install the SessionStart hook (Claude Code):** auto-injects the 5 most recent brain notes into every session's context and refreshes the code index in the background. Add to `~/.claude/settings.json` (replace `<WORKBENCH>` with your clone path):

```json
{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "bash <WORKBENCH>/harness/hooks/session-start.sh"}]}]}}
```

The script resolves the workbench root from its own location, prints nothing if the brain is empty, and always exits 0 so it can never break session start.

## Project conventions (when editing this repo)

- Python ≥3.10, stdlib only — do not add dependencies.
- State lives in `.state/` (`index.sqlite`, `brain.sqlite`); never commit it.
- Index roots default to `~/repo`; override via `AGENT_WORKBENCH_INDEX_ROOTS` (colon/comma-separated) or explicit `roots` args. Doctor intentionally also scans `~/Projects`.
- Smoke test after changes: pipe `initialize` + `tools/list` JSON-RPC lines into `run_mcp.py` and check the reply.
