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
- **Local-first state.** All persistent state is SQLite under `.state/`:
  `index.sqlite`, `brain.sqlite`, and `ledger.sqlite` for in-flight session rows.
  Nothing leaves the machine; backup is `brain_export` to markdown.
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
        |  brain.py        persistent notes (FTS5, porter) + recall tally|
        |  rules.py        contextual rules, matched by scope not text   |
        |  code_index.py   repo index build/refresh/search (FTS5)       |
        |  activity.py     git evidence per window, all local repos     |
        |  repo_state.py   branch/baseline/worktree identity (git)      |
        |  knowledge.py    live doc search, brief_task orchestrator     |
        |  scanners.py     doctor: secrets/MCP/permissions/stale docs   |
        |  work_sources.py sidecar connector health (no secrets)        |
        |            (config.py = paths/env, util.py = fs/proc)         |
        +-------------------------------+-------------------------------+
                                        |
              +-------------------------+---------------------------+
              v                                                     v
   .state/index.sqlite   .state/brain.sqlite          scanned filesystem
   (code index, FTS5)    (notes + rules; one      )   the repo root, the
                         (file, several tables    )   clone's parent, the
                                                      harness config dirs,
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
| Storage | `notes` FTS5 table, `tokenize='porter'` (stemming: "resumed" matches "resume"), plus three plain tables beside it: `note_stats`, `note_seq`, and the rule tables below |
| Note shape | content, kind (`decision fact gotcha preference todo note`), project, tags, `created_at`, `resolved_at` |
| Query | terms joined with `OR` (recall-oriented, unlike the index's `AND`), ranked by `bm25(notes)`; no query = most recent first |
| Lifecycle | `resolve` stamps `resolved_at`; resolved notes are hidden from default recall (`include_resolved=true` shows them); `forget` deletes; identical content+project is deduped on insert |
| Identity | ids are allocated from a `note_seq` high-water mark and never reissued. SQLite frees the rowid of the highest row on delete, and a note id is a reference — cited by hand as `brain#42` and used as the key of every side table — so a reused id would silently rebind them. The mark seeds from the current maximum, so an existing brain adopts it with no migration |
| Recall tally | `note_stats(note_id, recall_count, last_recalled_at)`. Every hit increments it, including hits from a thread digest and from the prompt hook. A rehearsed note gets a capped boost off its `bm25` score, so it wins a tie against an equally-matching note nobody has opened. Date-ordered recall is deliberately not boosted: that ordering exists to preserve a timeline. The write swallows sqlite errors on purpose — a locked database must cost a count, not the lookup |
| Deletion | `forget` clears every table in `brain.NOTE_KEYED_TABLES`, not a hand-written list per caller. A test reads `sqlite_master` and fails if a table carries a `note_id` column without being registered |
| Migration | `_connect` detects a pre-porter or pre-`resolved_at` schema and rebuilds the table **preserving rowids**, so note ids stay stable across upgrades |
| Backup | `export` dumps everything (including resolved) to markdown, grouped by project |

### Session ledger (`ledger.py` → `.state/ledger.sqlite`)

| Aspect | Implementation |
|---|---|
| Storage | `sessions(session_id primary key, repo, branch, started_at)` in its own file, not the brain: a session row lives for hours, a note is meant to last |
| Writer | `session-start.sh` calls `session-register <session_id> --cwd "$PWD"`. `repo` is `git rev-parse --show-toplevel` and `branch` the current branch, both null outside a repo |
| Resume / compact | an upsert on `session_id`: repo and branch are refreshed, `started_at` keeps the first registration, so a resumed or compacted session stays one row |
| Readers | none yet. `transcript_path` is not recorded and rows are never garbage-collected; both wait for the first feature that reads the table |

### Contextual rules (`rules.py` → same `.state/brain.sqlite`)

A note records *what is true*; a rule records *how to behave here*. They are not interchangeable, because the same situation needs different behaviour in different contexts.

| Aspect | Implementation |
|---|---|
| Storage | plain `rules` table, not the FTS one: a rule is found by **scope match, not text similarity**. That is the point — a correction stored while preparing a test handoff must come back on "is this ready for QA?", which shares no words with it |
| Rule shape | statement, why, example, scope, trigger, source, timestamps, `surfaced_count`, `corrected_count`, `retired_at` |
| Scope | a set of `type:value` keys. A rule applies when **every** key in its scope is active, which doubles as inheritance: declaring `repo:svc` and `workstream:runtime-upgrade` together inherits the rules of each, with no parent pointers |
| Precedence | more matched keys wins; a tie falls to the key type (`repo` > `workstream` > `task` > `audience` > `channel`), then to the newest rule |
| Lookup | `rule_scope(rule_id, key)` and `rule_trigger(rule_id, token)` mirror the text columns and carry the indexes. The candidate query is a union of indexed sources, so rows examined follow the number of rules that *could* match, not the number stored — `prompt-recall.sh` runs it on every turn. A global rule carries a `@global` sentinel key so even that branch is indexed, and a test asserts the query plan holds no `SCAN rules` |
| Conflicts | reported, never resolved silently, and only when rules are equally specific **and** their statements overlap. Two equally-specific rules that say unrelated things are two rules, not a conflict |
| Feedback | there is no `applied` outcome. Whether the model obeyed a rule is self-reported, and self-reported compliance is not evidence; what is measured is that a rule was surfaced and that the output still had to be corrected |
| Migration | a brain holding rules written before the index tables existed backfills itself on first use |

### Repository identity (`repo_state.py`)

A linked git worktree is a second *view* of one repository, not a second
repository: it has its own working directory and its own `.git` **file**, but
shares the `.git` common dir with the main checkout. Every component that
counts, names, or indexes repos therefore keys on
`git rev-parse --git-common-dir` (`git_common_dir()`), not on the directory
path:

- `activity.py` groups by common dir and reports the main checkout once, listing
  folded worktrees and their branches — scanning both trees double-counted every
  commit.
- `code_index.py` keeps one checkout per repository (`_dedupe_worktrees`), so a
  search cannot return whichever branch was indexed last. An orphaned worktree
  whose main checkout is gone is still indexed, being the only view left.
- `repo_state.py` reports `worktree: true` with `main_worktree`, and reads
  `FETCH_HEAD` from the common dir — the naive `<repo>/.git/FETCH_HEAD` path
  never exists in a worktree, so staleness checks silently no-opped.

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
- Every result is capped at `RESULT_BYTE_CAP` (10 KB): over it, whole items are popped
  from the largest lists (never emptying one) and the result gains `truncated`,
  `dropped_items`, and a hint to narrow the query. `brain_export` and `doctor_report`
  are exempt, because neither takes an argument that could narrow a cut list.
- `brain_recall` and `brief_task` swap note bodies for one-line summaries when a list
  holds more than `SUMMARY_THRESHOLD` (5) notes; `brain_recall ids=[...]` returns full
  bodies. `recent_activity` drops commit lists unless `repo` is named. All three are
  shaped here, so the domain functions keep returning full results to internal callers.

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
- Every hook reads its stdin payload through `harness/hooks/lib/hook-input.sh`,
  which sets `HOOK_PAYLOAD` and `HOOK_SESSION_ID` (the top-level `session_id`,
  kept only when it is a plain `[A-Za-z0-9_-]{1,64}` token, else empty).
- `harness/hooks/session-start.sh`, wired as a Claude Code `SessionStart` hook:
  records the session in the ledger (below), prints the 5 most recent brain notes to stdout (auto-injected into session context)
  and kicks `refresh-index` as a detached background process. Resolves the workbench
  root from its own path, is best-effort at every step, and always exits 0 so it can
  never break session start.
- `harness/hooks/prompt-recall.sh`, wired as `UserPromptSubmit`: passes the prompt
  and `session_id` to `recall-brief`, which (`prompt_recall.py`) keeps a note only
  when `-bm25 / (sqrt(distinct terms) * ln(note count))` clears `RELEVANCE_FLOOR`
  and this session has not already been shown it at that strength or more
  (`.state/prompt-recall-sessions.json`, 24-hour expiry, 50 sessions max). Then
  `rules-brief` injects global rules and rules whose scope keys are all among the
  working directory's `repo:` and `branch:`; trigger words are not consulted.
- `harness/hooks/subagent-recall.sh`, wired as `PreToolUse` (matcher `Agent`) and
  `SubagentStart`, through the `subagent-brief` CLI command. The first stashes the
  spawn prompt in `.state/spawn-prompts/` and prints nothing; the second claims it
  (unlinking the file is the claim, so parallel starts never share one) and returns
  `recall-brief` without session dedupe plus `rules-brief` as `additionalContext`,
  capped at 2000 characters. The stash exists because the `SubagentStart` payload
  has no prompt.

**Prompt-scoped (Claude Code only).**
- `harness/skills/*/SKILL.md` — symlinked into `~/.claude/skills/`. Skills answer
  what a store of durable facts cannot: `/standup` (activity, not memory),
  `/brain-harvest`, `/postmortem`, `/why`, `/meeting-prep`, `/pr-review`, and
  `/voice`. Most share one shape: resolve named entities to exact keys, gather
  from every source in parallel, verify before presenting, cite a surface per
  line. `/voice` is the exception worth
  noting — it drafts in the user's own voice and stores what it learns as
  audience-scoped contextual rules rather than a profile of its own, so
  `brain_context audience:<name>` *is* the profile and there is no second
  artifact to keep in sync.
- `harness/commands/*.md` — symlinked into `~/.claude/commands/`. A command is for
  behaviour that should be opt-in per turn, where a hook would fire on every turn
  in every project. `/say` is the first.
- `harness/agents/*.md` — symlinked into `~/.claude/agents/`. A subagent receives
  no SessionStart or UserPromptSubmit hooks (a spawn is neither a session start
  nor a user prompt) and none of the parent's context. `subagent-recall.sh` gives
  it the notes matching its spawn prompt once, at start; recall that follows the
  task as it unfolds must live in its own system prompt: `scout` recalls before
  searching, `implementer` recalls conventions before editing, `adversary` recalls
  known failure modes before reviewing.
  `implementer` has no spawn tool and is told never to request its own review:
  the parent runs `adversary` on the diff without the implementer's summary, so
  the review is not anchored on the author's framing.
  Recall itself goes through Bash, via the launcher setup.sh installs at
  `~/.config/agent-workbench/bin/aw`: an agent's `tools:` allowlist holds no MCP
  tool, and unknown allowlist names are dropped silently, so the MCP path is not
  reachable from a restricted agent.
  Each type also declares a `returns-schema` block in its own markdown, and
  `harness/agents/validate_return.py` checks the reply against it before the
  parent acts: every record must name evidence (`path`, `brain_id`, `commit`, a
  `command` with its real output, or an implementer's verification command and
  its real output), and `scout` and `adversary` records may say what they were
  `verified_against` (`repo@ref sha`, or `local checkout only`). One bad record
  rejects the whole return rather than being dropped. Prose reads the same
  whether a claim was checked or guessed, which is the gap this closes.

`setup.sh` also raises Claude Code's `cleanupPeriodDays` to 3650 when unset —
the 30-day default silently prunes `~/.claude/projects` transcripts.

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
| `AGENT_WORKBENCH_PROJECTS_ROOT` | the clone's parent directory | secondary root for doc search, service lookup, doctor scans (not indexed by default) |
| `AGENT_WORKBENCH_INDEX_ROOTS` | `[$REPO_ROOT]` | colon- or comma-separated roots the code index scans; explicit `roots` args override |
| `AGENT_WORKBENCH_STATE_DIR` | `<clone>/.state` | where `index.sqlite` and `brain.sqlite` live |
| `AGENT_WORKBENCH_CLAUDE_HOME` | `~/.claude` | Claude settings scanned by doctor (permissions, secrets) |
| `AGENT_WORKBENCH_CODEX_HOME` | `~/.codex` | Codex `config.toml` scanned by doctor and work-sources; large-state checks |
| `AGENT_WORKBENCH_WORK_MCP_ROOT` | `work-mcp/` beside the clone | sidecar connector checkout inspected by `work_sources_status` |

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
