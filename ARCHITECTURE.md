# Architecture

How Agent Workbench is put together and why. For usage, see `README.md`; for agent
behavior rules, see `AGENTS.md`.

## 1. Purpose & design principles

Agent Workbench gives coding harnesses (Claude Code, Codex, Gemini CLI) three local
capabilities: a searchable code/product index, a persistent cross-tool memory
("brain"), and setup diagnostics.

- **Dependency-free stdlib Python** (≥3.10). No pip installs, no virtualenv. Everything
  runs from a clone via `run_mcp.py` / `run_cli.py`.
- **Deterministic retrieval, no LLM calls.** The workbench never talks to a model API.
  The harness LLM is the reasoning layer; the workbench returns the same output for the
  same input and state, every time.
- **Local-first state.** All persistent state is two SQLite files under `.state/`
  (`index.sqlite`, `brain.sqlite`). Nothing leaves the machine; backup is
  `brain_export` to markdown.
- **No credentials.** Connector secrets (Slack tokens, Google OAuth, Atlassian auth)
  live in their own sidecar MCPs (the work-mcp repo). The workbench only *reports*
  connector health (`work_sources_status`) — it detects whether a token file exists but
  never reads or stores secret values, and its `doctor_report` actively hunts for
  secrets that leaked into configs and docs.

## 2. Component map

```
 Claude Code        Codex          Gemini CLI            shell / hooks
      \               |               /                        |
       \              |              /                         |
        +--------- stdio (JSON-RPC lines) --------+     run_cli.py -> cli.py
        |                                         |     (argparse subcommands)
        |   run_mcp.py -> mcp_server.py           |            |
        |   (hand-rolled JSON-RPC loop,           |            |
        |    tools/list + tools/call)             |            |
        +--------------------+--------------------+            |
                             |                                 |
                             v                                 v
        +---------------------------------------------------------------+
        |                      domain modules                           |
        |  brain.py        persistent notes (FTS5, porter)              |
        |  code_index.py   repo index build/refresh/search (FTS5)       |
        |  knowledge.py    live doc search, brief_task orchestrator     |
        |  scanners.py     doctor: secrets/MCP/permissions/stale docs   |
        |  work_sources.py sidecar connector health (no secrets)        |
        |            (config.py = paths/env, util.py = fs/proc)         |
        +-------------------------------+-------------------------------+
                                        |
              +-------------------------+---------------------------+
              v                                                     v
   .state/index.sqlite   .state/brain.sqlite          scanned filesystem
   (code index, FTS5)    (brain notes, FTS5)          ~/repo, ~/Projects,
                                                      ~/.claude, ~/.codex,
                                                      work-mcp checkout
```

Both entry points call the same module functions with the same `WorkbenchConfig`; the
MCP server and CLI are thin transports, not separate implementations.

## 3. Data & retrieval

**This is lexical search, not embeddings/RAG.** There is no vector store and no
semantic similarity. The division of labor: the harness LLM does query expansion
(synonyms, ticket keys, alternate phrasings — just issue another cheap query), the
workbench does exact-ish term matching with bm25 ranking. Brain notes are required (by
standing instruction) to carry source references — Jira keys, Slack channel + date,
doc names, file paths — which the LLM follows up via the *other* MCP servers
(Atlassian, Slack, Google Workspace). The workbench stores breadcrumbs; the sidecars
dereference them.

### Code index (`code_index.py` → `.state/index.sqlite`)

| Aspect | Implementation |
|---|---|
| Storage | `repos` table + `documents` FTS5 virtual table (default unicode tokenizer) |
| Roots | `config.index_roots`, default `~/repo`; env-overridable; explicit `roots` arg wins |
| Repo discovery | one level: each root is a repo if it holds a marker (`.git`, `README.md`, `pyproject.toml`, `package.json`, `go.mod`), else its immediate children are checked |
| What's indexed | code suffixes (`.py .js .ts .go .java …`), `.md`, agent docs, package files; ≤256 KB per file, ≤5 dirs deep, vendor/build dirs skipped |
| Query | terms extracted by regex, quoted, joined with `AND`, ranked by `bm25(documents)`; falls back to `LIKE` substring scan on FTS errors |
| Rebuild | `rebuild_index` — wipe and re-insert everything |
| Refresh | `refresh_index` — incremental: per-file fingerprint of sha256 + mtime + size; unchanged files skipped, vanished files deleted |
| Freshness | `index_status` reports age; searches attach a warning when the index is >24 h old |

Per-repo metadata (dominant language by suffix count, present package files) feeds
`codebase_overview`.

### Brain (`brain.py` → `.state/brain.sqlite`)

| Aspect | Implementation |
|---|---|
| Storage | single `notes` FTS5 table, `tokenize='porter'` (stemming: "resumed" matches "resume") |
| Note shape | content, kind (`decision fact gotcha preference todo note`), project, tags, `created_at`, `resolved_at` |
| Query | terms joined with `OR` (recall-oriented, unlike the index's `AND`), ranked by `bm25(notes)`; no query = most recent first |
| Lifecycle | `resolve` stamps `resolved_at`; resolved notes are hidden from default recall (`include_resolved=true` shows them); `forget` deletes; identical content+project is deduped on insert |
| Migration | `_connect` detects a pre-porter or pre-`resolved_at` schema and rebuilds the table **preserving rowids**, so note ids stay stable across upgrades |
| Backup | `export` dumps everything (including resolved) to markdown, grouped by project |

### Live doc search (`knowledge.py`, no index)

`search_knowledge` scans agent/project docs (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
`SKILL.md`, `README.md`, …) on the filesystem at query time — always fresh, term-count
scored per line. `context_for_path` lists nearby docs and extracts runnable commands
from fenced code blocks. `brief_task` is the one-call orchestrator: it merges
`code_search` + `search_knowledge` + `brain_recall`, votes on likely repos from hit
paths, and pulls commands from the top two — the task-start context pack.

## 4. MCP protocol layer (`mcp_server.py`)

Hand-rolled JSON-RPC 2.0 over stdio — no MCP SDK, one JSON object per line:

- `serve()` reads stdin line by line, writes compact JSON responses to stdout.
- Protocol version `2025-06-18`; `initialize` echoes the client's version if it
  matches, otherwise states its own, and returns server `instructions` (a nudge toward
  `brief_task` / `brain_remember`).
- Handled methods: `initialize`, `ping`, `tools/list`, `tools/call`. Requests without
  an `id` (notifications) are silently ignored; unknown methods/tools get standard
  JSON-RPC errors; handler exceptions become `-32603` responses instead of killing the
  loop.
- `TOOLS` is a static name → `{description, inputSchema}` dict; `handlers` maps the
  same names to lambdas over the domain functions. 16 tools total.
- Results are returned twice per the MCP spec: pretty-printed JSON in
  `content[0].text` and the raw dict in `structuredContent`.

## 5. Harness integration

Two layers, with different guarantees:

**Instruction-based (the LLM chooses to comply).**
- In-repo docs: `AGENTS.md` (canonical), `CLAUDE.md` (imports it via `@AGENTS.md`),
  `SKILL.md` — picked up automatically by any agent working *in* this repo.
- `harness/standing-instructions.md` — a shared snippet appended to each harness's
  global config (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`)
  so *every* session on the machine knows the workflow: `brief_task` at task start,
  `brain_remember` for durable knowledge (with mandatory source breadcrumbs),
  `brain_recall` before re-deriving, `refresh_code_index` on stale warnings.

**Hook-enforced (runs regardless of what the LLM decides).**
- `harness/hooks/session-start.sh`, wired as a Claude Code `SessionStart` hook:
  prints the 5 most recent brain notes to stdout (auto-injected into session context)
  and kicks `refresh-index` as a detached background process. Resolves the workbench
  root from its own path, is best-effort at every step, and always exits 0 so it can
  never break session start.

The MCP server itself is registered per harness: `claude mcp add` (name
`agent-workbench`), `~/.codex/config.toml` (`agent_workbench`), or Gemini
`settings.json` — all launching `python3 <clone>/run_mcp.py`.

## 6. Config & environment variables (`config.py`)

All settings are paths resolved once at import time; the frozen `WorkbenchConfig`
dataclass carries them into every function (CLI flags `--repo-root`/`--projects-root`
can override the first two per invocation).

| Variable | Default | Affects |
|---|---|---|
| `AGENT_WORKBENCH_REPO_ROOT` | `~/repo` | primary work-repo root: default index root, doc search, service lookup, doctor scans |
| `AGENT_WORKBENCH_PROJECTS_ROOT` | `~/Projects` | secondary root for doc search, service lookup, doctor scans (not indexed by default) |
| `AGENT_WORKBENCH_INDEX_ROOTS` | `[$REPO_ROOT]` | colon- or comma-separated roots the code index scans; explicit `roots` args override |
| `AGENT_WORKBENCH_STATE_DIR` | `<clone>/.state` | where `index.sqlite` and `brain.sqlite` live |
| `AGENT_WORKBENCH_CLAUDE_HOME` | `~/.claude` | Claude settings scanned by doctor (permissions, secrets) |
| `AGENT_WORKBENCH_CODEX_HOME` | `~/.codex` | Codex `config.toml` scanned by doctor and work-sources; large-state checks |
| `AGENT_WORKBENCH_WORK_MCP_ROOT` | `~/Projects/work-mcp` | sidecar connector checkout inspected by `work_sources_status` |

Non-env knobs on `WorkbenchConfig`: `max_text_bytes` (256 000 — per-file read/index
cap) and `max_search_results` (50 — default `search_knowledge` limit).

## 7. Extension points & non-goals

**Extension points**
- *New MCP tool*: add a `TOOLS` entry + handler lambda in `mcp_server.py`, a subcommand
  in `cli.py`, and the logic in a domain module. The static dict is the whole registry.
- *New doctor rule*: add a `scan_*` function in `scanners.py` returning `Finding`s and
  call it from `scan_all`.
- *New work source*: add a `_<name>_status` helper in `work_sources.py` — existence and
  config checks only, never credential values.
- *New index roots / file types*: `AGENT_WORKBENCH_INDEX_ROOTS`, or extend
  `CODE_SUFFIXES` / `DOC_NAMES` / `PACKAGE_FILES` in `code_index.py`.

**Non-goals (deliberate)**
- **No embeddings/vector search** until scale demands it — FTS5 bm25 plus LLM-side
  query expansion is enough at the current corpus size, and it stays deterministic and
  dependency-free.
- **No credential storage or proxying.** Secrets stay in sidecar MCPs; the workbench
  reports health and flags leaks, nothing more.
- **One-level repo discovery.** Roots and their immediate children only — no recursive
  repo hunting across the disk.
- **No LLM calls, no network calls.** Purely local filesystem + SQLite (the only
  subprocesses are `git` status reads in `work_sources`).
- **No daemon.** The index is a snapshot refreshed on demand (CLI, MCP tool, or the
  SessionStart hook), not a file watcher.
