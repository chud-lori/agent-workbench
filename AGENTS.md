# Agent Workbench — Agent Guide

Local, dependency-free MCP server + CLI: FTS code index over `~/repo`, persistent cross-tool memory ("brain"), and local AI-setup diagnostics. No LLM calls; deterministic retrieval only.

Registered MCP names: `agent-workbench` (Claude Code), `agent_workbench` (Codex).
CLI fallback: `python3 <path-to-agent-workbench>/run_cli.py <command>` (this repo's root).

New machine? See **Harness setup** below to register the MCP and install the standing instructions into your own harness configs.

## Standing instructions (any harness, any repo)

1. **Task start**: for a nontrivial ticket/feature/bug, call `brief_task` with the ticket key or feature phrase first. It returns likely repos, code hits, doc hits, saved brain notes, and runnable repo commands in one call — use it before grepping manually.
2. **Store durable knowledge**: when you learn something durable during work — schema quirks, deploy steps, API behaviors, tricky conventions, decisions made with the user — save it with `brain_remember`:
   - `kind`: `decision` | `fact` | `gotcha` | `preference` | `todo` | `note` | `reference`
   - `project`: repo directory name (e.g. `my-api`)
   - `tags`: short keywords for recall
   - Every note must include a source reference — a ticket key, Slack channel + date, doc name, file path, or for code on GitHub a permalink pinned to a commit SHA (`repo@sha path:line`; branch links rot). Notes without breadcrumbs are dead ends.
   - Never store secrets, tokens, or anything trivially derivable from the code itself.
3. **Correct, don't contradict**: when new knowledge corrects or extends an earlier note, use `brain_amend` (append a dated addendum, or replace the body) or re-store with `supersedes=[ids]` — superseded notes are hidden from default recall so stale claims can't resurface as truth. `brain_remember` returns `similar_notes` when it spots likely overlap; review them before stacking a near-duplicate.
4. **Recall before re-deriving**: before answering questions about past decisions or cross-repo conventions, check `brain_recall` (query, or filter by `project`/`kind`). Pass `thread=<tag/key/keyword>` for a chronological digest of one storyline (superseded collapsed to stubs), or `since=`/`until=` (`'yesterday'`, `'2026-07-15'`, `'7d'`) to bound by when notes were stored. When a stored todo is done, mark it with `brain_resolve` (do not forget it — history matters); resolved notes are hidden from default recall unless you pass `include_resolved`. Back up the brain with `brain_export`.
   - The brain is a store of durable facts, **not an activity log**. "What did I do yesterday?" is not a recall question: use `recent_activity` for the git evidence and the `/standup` skill to merge it with Slack, calendar, and PRs.
5. **Pin canonical sources**: store runbooks, wiki pages, dashboards as `kind=reference` notes (title + key sections + URL/page id). They surface in `brain_recall` and as `pinned_references` in `brief_task`.
5b. **Promote what proves general**: the brain is personal; teams share through git-versioned markdown. When a personal note proves broadly useful (a gotcha others will hit, a convention), `brain_promote` it into the team's reference file/playbook and open a PR there. Evidence and one-off details stay personal.
5c. **Attribute rules**: when a stored note or convention decides something in your work, say so in one short line — `brain#42: this repo ships without unit tests` — so the human knows it was a recorded rule, not a whim.
6. **Check deployed reality**: before claiming how production behaves or writing prod patches, run `repo_state` on the repo — local checkouts often sit on feature branches with undeployed changes. `brief_task` runs this automatically when the query mentions prod/deploy and warns on divergence.
7. **Index freshness**: if `code_search`/`brief_task` warn the index is stale, run `refresh_code_index` (incremental, fast). `rebuild_code_index` only after changing index roots.
8. **Diagnostics**: `doctor_report` when local AI setup misbehaves (secrets hygiene, MCP config, permissions); `mcp_health` for MCP config checks; `work_sources_status` when the Slack/Google/Atlassian connector MCPs misbehave.

## Tool map

| Tool | Use |
|---|---|
| `brief_task` | one-call task context pack (code + docs + brain + pinned references + commands; warns on prod-divergent repos) |
| `brain_remember` / `brain_recall` / `brain_forget` | persistent cross-session, cross-tool memory (`supersedes=[ids]` retires corrected notes; `thread=` digests a storyline; `since=`/`until=` bounds by when a note was stored) |
| `brain_amend` | correct/extend an existing note in place (append a dated addendum or replace) |
| `brain_promote` | append a proven note to a shared, git-versioned markdown reference (team playbook); stamps the note so it promotes once |
| `brain_resolve` | mark a todo/note resolved (hidden from default recall; `include_resolved` shows it) |
| `brain_export` | dump all brain notes to markdown (backup) |
| `repo_state` | branch + ahead/behind origin/main|master + dirty/staleness for a repo — run before prod-behavior claims |
| `recent_activity` | commits you made in a time window across every local repo (all branches, so unpushed work shows) — the git half of "what did I do yesterday?" |
| `code_search` | bm25 keyword search over indexed repos |
| `codebase_overview` | languages/package files/docs per indexed repo |
| `search_knowledge` | live search over CLAUDE.md/AGENTS.md/SKILL.md/READMEs |
| `find_service_context` | locate repo + commands for a service name |
| `rebuild_code_index` / `refresh_code_index` / `index_status` | manage the index |
| `doctor_report` / `mcp_health` / `work_sources_status` | diagnostics |

## Harness setup (per user machine)

Everything below assumes this repo is cloned at `$WORKBENCH` (e.g. `~/Projects/agent-workbench`). The only requirement is Python ≥3.10 — the [work-mcp](https://github.com/chud-lori/work-mcp) sidecar (Slack/Google connector MCPs) is optional; without it, `work_sources_status` simply reports it absent and everything else works. To set up the connectors too, clone work-mcp to `~/Projects/work-mcp` (or set `AGENT_WORKBENCH_WORK_MCP_ROOT`) and follow its README/setup.sh.

**Recommended: run `./setup.sh`** — it does every numbered step below in one idempotent pass: detects your harnesses (Claude Code / Codex / Gemini CLI), registers the MCP server, installs the standing instructions into the right global instruction file (marker-fenced `<!-- agent-workbench:start/end -->` block, refreshed in place on re-run), wires all four Claude Code hooks via `harness/install_hooks.py` (re-runs upgrade existing entries instead of duplicating), optionally seeds guard patterns, offers optional companion plugins from upstream (caveman for concise output; prints ponytail's in-app install prompts — neither is vendored here), and builds the index. `./uninstall.sh` reverses all of it but never touches `.state/` — the brain survives. The steps below are the manual equivalent.

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

**4. Install the SessionStart hook (Claude Code):** auto-injects the 5 most recent brain notes into every session's context, self-updates the workbench (background `git pull --ff-only`, only on a clean working tree), and refreshes the code index in the background. The matcher includes `resume|compact` so the brain **re-primes after a context compaction** instead of fading mid-session. Add to `~/.claude/settings.json` (replace `<WORKBENCH>` with your clone path):

```json
{"hooks": {"SessionStart": [{"matcher": "startup|resume|compact", "hooks": [{"type": "command", "command": "bash <WORKBENCH>/harness/hooks/session-start.sh"}]}]}}
```

The script resolves the workbench root from its own location, prints nothing if the brain is empty, and always exits 0 so it can never break session start. (All four hook snippets here are what `harness/install_hooks.py` writes for you.)

**5. Install the Stop hook (Claude Code):** enforces the "store durable knowledge" instruction instead of leaving it to model judgment. At every turn end it blocks the stop once and tells the model to save any decisions, gotchas, run results, or new conventions from the turn with `brain_remember` (or end immediately if nothing durable was learned). The `stop_hook_active` flag guarantees it can never loop, and the script always exits 0.

```json
{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "bash <WORKBENCH>/harness/hooks/stop-memory-checkpoint.sh"}]}]}}
```

**6. Install the UserPromptSubmit hook (Claude Code):** approximates involuntary human recall. On every user prompt it FTS-matches the prompt against brain notes and injects up to 5 one-line hits (ids + hooks) into the turn's context; full bodies stay pull-based via `brain_recall`. Threshold-gated — trivial prompts ("yes", "go") inject nothing — and always exits 0.

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bash <WORKBENCH>/harness/hooks/prompt-recall.sh"}]}]}}
```

**7. Install the PreToolUse guard (Claude Code, optional):** forces explicit human approval for any Bash command matching your guard patterns — enforcement outside the model, for the commands that must never run on autopilot (prod hosts, destructive infra). The mechanism is generic; patterns are per-machine and untracked: copy `harness/guard-patterns.example.txt` to `.state/guard-patterns.txt` and add your org's regexes (or point `AGENT_WORKBENCH_GUARD_PATTERNS` elsewhere). No patterns file = silent no-op.

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "bash <WORKBENCH>/harness/hooks/pretooluse-guard.sh"}]}]}}
```

Together the hooks close the second-brain loop at the harness level: SessionStart primes, UserPromptSubmit recalls per-turn, Stop stores, PreToolUse guards. Cost: one extra short model pass per turn plus a few injected lines per prompt.

**8. Install the brain-harvest skill (Claude Code):** the hooks capture knowledge from *interactive agent work*; `/brain-harvest` backfills everything else. Run it weekly: it scans your merged PRs (`gh`), resolved Jira tickets, and Slack activity for the past window, dedupes against existing brain notes, and proposes new notes — nothing is stored without your approval. Works with any model. Skill source: `harness/skills/brain-harvest/SKILL.md`; setup.sh symlinks it, or manually:

```bash
mkdir -p ~/.claude/skills && ln -s "$WORKBENCH/harness/skills/brain-harvest" ~/.claude/skills/brain-harvest
```

Requires the `gh` CLI (authenticated) plus the Atlassian and Slack MCPs for full coverage; missing sources are skipped with a note.

**9. Install the standup skill (Claude Code):** `/standup` answers "what did I do yesterday?" — the one question the brain cannot answer, because it stores durable facts rather than an activity log. It merges four sources the model fans out over: `recent_activity` (git, incl. unpushed branches), `gh` PRs, Slack, and Google Calendar, then verifies threads before writing a paste-ready Done / Today / Blockers summary. setup.sh symlinks every directory under `harness/skills/`, so it installs alongside brain-harvest; manually:

```bash
mkdir -p ~/.claude/skills && ln -s "$WORKBENCH/harness/skills/standup" ~/.claude/skills/standup
```

Degrades cleanly: any missing source is skipped and called out, since a silently absent source reads as "nothing happened there."

**10. Install the evidence skills (Claude Code):** three more skills follow the same fan-out-and-verify pattern as `/standup` — gather from every source in parallel, verify threads before presenting, cite a surface for every line:

- `/postmortem` — reconstruct an incident from Slack + `recent_activity` + deploys + PRs + tickets into a timeline (cause introduced → detected → mitigated → resolved), a blameless five-whys, and a draft with owned action items. Ends by *proposing* one root-cause `gotcha` for the brain — approval-gated.
- `/why` — code archaeology: climb blame → commit → PR → ticket → Slack → brain to answer "why does this code exist", with a cited evidence chain and an honest "no recorded reason survives" when the chain dead-ends.
- `/meeting-prep` — one-page brief for the next calendar event: agenda + what changed since last occurrence + what you owe / are owed + likely topics, from calendar, Slack, Jira, PRs, and brain notes.

setup.sh symlinks every directory under `harness/skills/`, so these install with the rest; manually:

```bash
mkdir -p ~/.claude/skills
for s in postmortem why meeting-prep; do ln -s "$WORKBENCH/harness/skills/$s" ~/.claude/skills/$s; done
```

**11. Install the brain-primed agent types (Claude Code):** a subagent receives **no** hooks — not SessionStart priming, not prompt-recall injection — and none of the parent's context. Measured over 211 local subagent transcripts: 208 could reach the brain, 5 called `brain_recall`, and 0 ever got a note injected. So recall has to live in the subagent's own system prompt or it never happens. `harness/agents/` ships three types that recall before they act:

- `scout` — read-only investigator: `brain_recall`/`brief_task` first, filesystem second; reports `path:line` and `brain#id`, and flags notes the code contradicts.
- `implementer` — writes to the project's recorded conventions (decisions, gotchas, preferences), matches surrounding style, and proves the change with the project's own checks.
- `adversary` — loads the project's known failure modes (`kind=gotcha`) before reading a diff, then reports only findings with a concrete failure scenario.

setup.sh symlinks every `harness/agents/*.md` into `~/.claude/agents/`; manually:

```bash
mkdir -p ~/.claude/agents
for a in "$WORKBENCH"/harness/agents/*.md; do ln -s "$a" ~/.claude/agents/"$(basename "$a")"; done
```

The parent's half of the job is a standing instruction: hand a subagent *evidence* (file:line, the snippet, `brain#id`), not conclusions it must re-derive.

**12. Transcript retention (Claude Code):** setup.sh sets `cleanupPeriodDays: 3650` in `~/.claude/settings.json` when unset. Claude Code otherwise prunes `~/.claude/projects` after **30 days**, silently deleting session history on a rolling basis. An existing value is left alone.

## Measuring the brain (blind replay)

To prove (or debug) the memory's value, replay a task the team already finished: check out the repo pinned to just before the real fix (single branch, no remote), give the same prompt to the same model twice — once with the workbench MCP/hooks disabled, once enabled — and score both against the shipped fix and your conventions (correctness, rules followed, tool calls, tokens, wall time). Run it blind (no session memory of the original work). This also audits the brain itself: a replay that contradicts a stored note means the note needs `brain_amend`.

## Worktrees

A linked worktree shares its history and its `.git` common dir with the main
checkout — it is a second *view* of one repo, not a second repo. Everything that
counts, names, or indexes repositories keys on `git rev-parse --git-common-dir`
(`repo_state.git_common_dir`) so that:

- `recent_activity` counts each commit once, reports the main checkout as the
  repo, and lists the folded worktrees and their branches under `worktrees` —
  scanning both trees used to double every commit.
- the code index keeps **one checkout per repository**, so a search cannot
  return whichever branch happened to be indexed last. An orphaned worktree
  (main checkout gone) is still indexed, since it is then the only view.
- `repo_state` flags `worktree: true` with `main_worktree`, and warns that other
  repo tooling may be describing the main checkout's branch rather than this
  one. It also reads `FETCH_HEAD` from the common dir — a worktree's `.git` is a
  file, so the old `.git/FETCH_HEAD` path silently never existed.

Regression tests live in `tests/test_worktree.py` and build a real worktree.

## Project conventions (when editing this repo)

- Python ≥3.10, stdlib only — do not add dependencies.
- State lives in `.state/` (`index.sqlite`, `brain.sqlite`); never commit it.
- Index roots default to `~/repo`; override via `AGENT_WORKBENCH_INDEX_ROOTS` (colon/comma-separated) or explicit `roots` args. Doctor intentionally also scans `~/Projects`.
- Smoke test after changes: pipe `initialize` + `tools/list` JSON-RPC lines into `run_mcp.py` and check the reply.
