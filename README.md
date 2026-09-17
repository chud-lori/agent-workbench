<p align="center">
  <img src="assets/logo.svg" alt="Agent Workbench logo" width="140">
</p>

<h1 align="center">Agent Workbench</h1>

<p align="center">
  <b>A local, dependency-free memory and context layer for AI coding agents<br>(Claude Code, Codex, Gemini CLI).</b>
</p>

<p align="center">
  <a href="https://chud-lori.github.io/agent-workbench/">Website</a> ·
  <a href="AGENTS.md">Agent guide</a> ·
  <a href="ARCHITECTURE.md">Architecture</a>
</p>

<p align="center">
  <img alt="Python ≥3.10, stdlib only" src="https://img.shields.io/badge/python-%E2%89%A53.10%20stdlib--only-3776AB?logo=python&logoColor=white">
  <img alt="MCP server" src="https://img.shields.io/badge/MCP-stdio%20server-6d28d9">
  <img alt="No LLM calls" src="https://img.shields.io/badge/LLM%20calls-none-2ea043">
</p>

Every agent session starts from zero: no memory of yesterday's decisions, no view across your repos, and no idea whether its own setup is broken. Agent Workbench puts three stores on the machine to fix that:

- **A persistent brain.** Durable notes (decisions, facts, gotchas, preferences, todos, references) in SQLite FTS5 with the porter tokenizer, in one file every harness on the machine reads. What Claude Code stores today, Codex recalls tomorrow.
- **A local code index.** One bm25 query across every indexed repo, with incremental refresh. No embeddings and no API calls, so the same query returns the same rows; your agent does the semantic reasoning on top.
- **Setup diagnostics.** Five local scans: MCP config files, assistant permission allowlists, secrets on disk, oversized state, and stale doc paths.

It is a single stdio MCP server plus CLI in stdlib-only Python (3.10 or newer, the sole requirement). It makes **no LLM calls and no network calls**: the package imports only the standard library, and none of those imports opens a socket. Git is shelled out to; nothing else leaves the machine. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Quickstart

```bash
git clone https://github.com/chud-lori/agent-workbench.git
cd agent-workbench
./setup.sh
```

`setup.sh` detects your harnesses (Claude Code / Codex / Gemini CLI), registers the MCP server, installs the standing instructions in a marker-fenced block so re-runs refresh in place, wires the four Claude Code hooks, links the skills and agent types, raises Claude Code's transcript retention off its 30-day default, and builds the code index. It is idempotent, so re-run it anytime. `./uninstall.sh` reverses all of it but never touches `.state/`, so the brain and the index survive.

`setup.sh` is a bash script that writes symlinks, so it targets a Unix shell. Manual per-harness steps are in [AGENTS.md → Harness setup](AGENTS.md).

## Configuration

Environment variables with defaults. Nothing is hardcoded to a particular machine layout except the state directory default, which is noted below:

| Env var | Default | Purpose |
|---|---|---|
| `AGENT_WORKBENCH_REPO_ROOT` | `~/repo` | Where your work repos live |
| `AGENT_WORKBENCH_INDEX_ROOTS` | repo root | Roots to index (colon/comma-separated) |
| `AGENT_WORKBENCH_PROJECTS_ROOT` | `~/Projects` | Secondary root scanned by diagnostics and activity |
| `AGENT_WORKBENCH_STATE_DIR` | `~/Projects/agent-workbench/.state` | SQLite state location (index + brain). A fixed path, not one relative to the clone, so set this if you cloned elsewhere |
| `AGENT_WORKBENCH_WORK_MCP_ROOT` | `~/Projects/work-mcp` | Optional connector sidecar (see below) |
| `AGENT_WORKBENCH_CLAUDE_HOME` / `_CODEX_HOME` | `~/.claude` / `~/.codex` | Harness config locations for diagnostics |

## MCP tools

Twenty tools, each with a CLI twin. The reference below mirrors the `TOOLS` table in `agent_workbench/mcp_server.py`.

**Task start:**

- `brief_task` (CLI `brief`) - one call for a ticket key or feature phrase: code hits, doc hits, matching brain notes, pinned references, likely repos, and runnable repo commands. On a prod- or deploy-flavored query it also checks the likely repo against its origin baseline and warns on divergence

**Brain (persistent cross-tool memory):**

- `brain_remember` (CLI `remember`) - store a durable note (`decision` / `fact` / `gotcha` / `preference` / `todo` / `note` / `reference`) with project and tags. Pass `supersedes=[ids]` to hide the notes it corrects; the result may carry `similar_notes`, which is the prompt to amend instead of stacking a near-duplicate. Convention (not enforced by the store): every note carries a source reference, such as a ticket key, a Slack thread, a doc name, or a SHA-pinned permalink
- `brain_recall` (CLI `recall`) - FTS search with porter stemming; recent notes when no query; `thread=<key>` digests one storyline chronologically; `since`/`until` bound by when a note was stored (`'yesterday'`, `'2026-07-15'`, `'7d'`). Resolved and superseded notes stay hidden unless asked for
- `brain_amend` (CLI `amend`) - correct a note in place: append a dated addendum, or replace the body
- `brain_promote` (CLI `promote`) - append a proven personal note to a shared, git-versioned markdown file, and stamp it so it promotes once
- `brain_resolve` / `brain_forget` (CLI `resolve` / `forget`) - mark done (kept, hidden from default recall) / delete
- `brain_export` (CLI `export`) - dump all notes to markdown. The index is rebuildable; the brain is not, so this is the backup

**Code index and docs:**

- `code_search` (CLI `code-search`) - bm25 keyword search across every indexed repo at once
- `refresh_code_index` / `rebuild_code_index` / `index_status` (CLI `refresh-index` / `index` / `index-status`) - incremental refresh (the one to run on a stale-index warning) / full rebuild (after changing index roots) / freshness report
- `codebase_overview` (CLI `overview`) - languages, package files, docs per repo
- `search_knowledge` (CLI `search`) - live search over agent docs (CLAUDE.md, AGENTS.md, SKILL.md, READMEs), read from disk at query time
- `find_service_context` (CLI `service`) - locate the repo and commands for a service name

**Repo and activity:**

- `repo_state` (CLI `repo-state`) - branch, ahead/behind `origin/main` or `origin/master`, dirty files, fetch staleness, and whether the path is a linked worktree. Run it before claiming how production behaves from local code
- `recent_activity` (CLI `activity`) - commits you made in a time window across every local repo; scans all branches, so unpushed work `gh` cannot see still shows up. Commits only, since the server has no network access: the `/standup` skill merges it with Slack, calendar, and PRs, because the brain stores durable facts, not an activity log

**Diagnostics:**

- `doctor_report` (CLI `doctor`) - findings from five scans: MCP configs, permission allowlists, secrets on disk, oversized state, stale doc paths
- `mcp_health` / `work_sources_status` (CLI `mcp-check` / `work-sources`) - MCP config checks / connector sidecar health, with no secrets printed

Three CLI commands have no MCP twin: `context` summarises one path, `recall-brief` returns the compact note lines the prompt hook injects, and `mcp-server` is what the MCP registration runs.

## Hooks (Claude Code)

Standing instructions make an agent *likely* to use the brain. The hooks make most of the loop happen whether or not the model cooperates, because the harness runs them. `harness/install_hooks.py` wires them, recognises its own entries even if the clone moved, and upgrades in place rather than duplicating.

| Event | Script | Does |
|---|---|---|
| `SessionStart` | `session-start.sh` | Prints up to five recent brain notes (trimmed, with ids) into the session. Matcher `startup\|resume\|compact`, so the brain re-primes after a context compaction. Then detaches a background job that refreshes the index and fast-forwards the clone with `git pull --ff-only`, but only when the working tree is clean |
| `UserPromptSubmit` | `prompt-recall.sh` | FTS-matches the prompt and injects up to five one-line hits with ids; bodies stay pull-based via `brain_recall`. Threshold-gated, so a trivial prompt injects nothing |
| `Stop` | `stop-memory-checkpoint.sh` | Blocks the stop once and tells the model to store anything durable from the turn. It cannot loop: the hook stays silent when the model is already continuing from its own previous block |
| `PreToolUse` | `pretooluse-guard.sh` | Forces explicit human approval for Bash commands matching your regex patterns. Inert by default: the patterns file is per-machine and untracked, and a missing or empty file makes the hook a silent no-op |

All four are best-effort by design and always exit zero. A hook that can break session start is worse than a hook that occasionally does nothing.

## Commit attribution guard

Two plain git hooks in `harness/git-hooks/` keep commits attributed to the human who owns the repo, for any assistant rather than one vendor:

- `commit-msg` strips `Co-Authored-By:` and "Generated with" attribution lines (and robot-emoji trailers) from the message, and says what it removed
- `pre-commit` refuses a commit authored or committed under an assistant or bot identity, or with no email set

Enable them for one repo through `.git/hooks`, or for every repo with `git config --global core.hooksPath <clone>/harness/git-hooks`; `setup.sh` offers both. They chain to any repo-local hooks, keep real human co-authors, and leave prose that merely mentions these tools alone.

## Skills (Claude Code)

Six skills under `harness/skills/` share one pattern: gather from every work source in parallel, verify threads before presenting, cite a surface for every line. setup.sh symlinks them into `~/.claude/skills/`.

- `/standup` - "what did I do yesterday?" from git, PRs, Slack, calendar, and brain notes, as paste-ready Done / Today / Blockers
- `/brain-harvest` - weekly backfill: scan merged PRs, resolved tickets, and Slack for durable knowledge the hooks missed, deduped against existing notes and approval-gated
- `/postmortem` - incident reconstruction: evidence timeline, blameless five-whys, action items with owners; proposes one root-cause gotcha for the brain
- `/why` - code archaeology: blame to commit to PR to ticket to Slack to brain, answering "why does this code exist" with a cited chain, and saying so plainly when no reason was recorded
- `/pr-review` - reviews a PR, branch, or diff against the project's recorded conventions plus six axes (comment noise, overengineering, security, efficiency, simplicity, maintainability), citing numbered rules and closing on a Gate/Justify/Lock verdict
- `/meeting-prep` - one-page brief for the next calendar event: what changed since last time, what you owe and are owed, likely topics

## Agent types (Claude Code)

Subagents get no hooks and none of the parent's context, so brain recall has to live in their own system prompt. They also run with a restricted toolset that holds no MCP tools, so they recall through Bash with the CLI launcher setup.sh installs at `~/.config/agent-workbench/bin/aw`. `harness/agents/` ships three types that do it, symlinked into `~/.claude/agents/`:

- `scout` - read-only investigator; recalls notes before searching the filesystem, cites `path:line` and `brain#id`
- `implementer` - implements against recorded decisions, gotchas, and preferences, matches surrounding style, verifies with the project's own checks
- `adversary` - loads known failure modes first, then reviews a diff for findings with a concrete failure scenario

## CLI

Every MCP tool has a CLI equivalent for shells, cron jobs, and hooks:

```bash
python3 run_cli.py brief "TICKET-1234"
python3 run_cli.py remember "orders API paginates at 50, per TICKET-1234" --kind fact --project my-api
python3 run_cli.py recall "pagination"
python3 run_cli.py resolve 7          # mark a todo done (kept, hidden from default recall)
python3 run_cli.py export --out brain-backup.md
python3 run_cli.py index && python3 run_cli.py index-status
python3 run_cli.py code-search "rate limiter"
python3 run_cli.py repo-state my-api
python3 run_cli.py doctor --all
python3 run_cli.py mcp-server         # what the MCP registration runs
```

## Optional: connector sidecar

[work-mcp](https://github.com/chud-lori/work-mcp) is a companion project holding Slack and Google Workspace connector MCPs. Agent Workbench does not need it: `work_sources_status` simply reports whether it is present and healthy. The separation is deliberate, so connector credentials never live in (or flow through) this project.

## Design notes

- **Lexical, not RAG.** Retrieval is SQLite FTS5 plus bm25: exact, explainable, zero-dependency, and reproducible. A miss is a query problem you can see rather than a distance threshold you cannot. Query expansion and synthesis are the LLM's job, and brain notes carry source breadcrumbs the agent can follow into Jira, Slack, or GitHub via their own MCPs.
- **Worktree-aware.** Repos are identified by their shared git dir, so a linked worktree folds into its main checkout: commits are counted once, the index keeps one checkout per repository, and `repo_state` tells an agent when it is standing in a worktree.
- **State is local and mostly disposable.** Everything lives in `.state/` (gitignored). `index.sqlite` is rebuildable at any time; `brain.sqlite` is the only thing worth backing up, which is what `brain_export` is for.
- **The brain is personal, playbooks are shared.** Notes stay in your state directory; teams share through git-versioned markdown via `brain_promote`. Evidence and one-off details stay personal.
- **Instruction-based vs hook-enforced.** Standing instructions make agents *likely* to use the brain; the SessionStart hook makes recall *guaranteed*. Use both.

## Design direction

`DESIGN.md` holds the sourced design direction for the website in `docs/`: identity, palette, typography, the liveliness dials, and the open questions the repo has not answered. Any change to `docs/index.html` should be checked against it, and user-facing doc changes land in both this README and the site.

## License

Currently unlicensed (all rights reserved). Open an issue if you want to use it and this matters to you.
