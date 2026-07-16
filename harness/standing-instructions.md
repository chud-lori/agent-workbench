# Agent Workbench (local MCP: `agent-workbench` / `agent_workbench`)

Local MCP with a code index over your repo root, persistent cross-tool memory ("brain"), and AI-setup diagnostics. Full guide: `AGENTS.md` in the agent-workbench repo. CLI fallback: `python3 <path-to-agent-workbench>/run_cli.py`.

- At the start of a nontrivial ticket/feature task, call `brief_task` with the ticket key or feature phrase — it returns likely repos, code/doc hits, saved brain notes, pinned references, and repo commands in one call (and warns when a likely repo diverges from origin/main on prod-flavored queries).
- When you learn a durable fact, decision, or gotcha during work (schema quirks, deploy steps, API behaviors, conventions), store it with `brain_remember` (kind: decision|fact|gotcha|preference|todo|note|reference; project: repo dir name; short tags). Never store secrets or facts trivially derivable from code.
- Every `brain_remember` note must include a source reference — a ticket key, Slack channel + date, doc name, file path, or for code on GitHub a permalink pinned to a commit SHA (`repo@sha path:line`; branch links rot). Notes without breadcrumbs are dead ends.
- When new knowledge corrects or extends an earlier note, use `brain_amend` (dated addendum or replace) or re-store with `supersedes=[ids]` — never stack contradicting notes; superseded ones are hidden from default recall. Review `similar_notes` in the `brain_remember` result before storing near-duplicates.
- Pin canonical sources (runbooks, wiki pages, dashboards) as `kind=reference` notes with title, key sections, and URL/page id.
- When a personal note proves general (a gotcha others will hit, a team convention), `brain_promote` it into the team's shared reference file/playbook; evidence and one-offs stay personal.
- When a stored note or convention decides something, attribute it in one short line (`brain#42: <the rule>`) so the human knows a recorded rule applied — one line, no lecture.
- Scale verification to the diff (proportional diligence): a small isolated fix needs one proving grep/check, not an audit; save the full checklist for schema/shared/cross-service changes.
- When a stored todo is done, mark it with `brain_resolve` (do not forget it — history matters). Resolved notes are hidden from default `brain_recall`; pass `include_resolved` to see them.
- Before re-deriving past decisions or cross-repo conventions, check `brain_recall`; pass `thread=<tag/key/keyword>` for a chronological digest of one storyline, or `since=`/`until=` (`'yesterday'`, `'2026-07-15'`, `'7d'`) to bound by when notes were stored.
- The brain holds durable facts, not an activity log — never answer "what did I do yesterday / this week?" from `brain_recall`. Use `recent_activity` (commits across every local repo, all branches) for the git evidence, and merge it with Slack, calendar, and PRs (the `/standup` skill does this). A day with no commits is not a day with no work.
- Before claiming how production behaves or writing prod patch queries, run `repo_state` on the repo — local checkouts often sit on feature branches with undeployed changes; verify against `origin/main`.
- Back up the brain periodically with `brain_export` (dumps all notes to markdown).
- On a stale-index warning from `code_search`/`brief_task`, run `refresh_code_index`.
- Setup misbehaving? `doctor_report` (secrets/config/permissions), `mcp_health` (MCP configs), `work_sources_status` (work connector health).
- When reading Slack via any connector, never surface raw user IDs (U0…) to the user — resolve them to real names first (Slack user lookup, or a pinned roster reference note in the brain).
- Claude Code users: the repo's `harness/hooks/` has a SessionStart hook (primes recent brain notes + refreshes the index), a UserPromptSubmit hook (injects top note hits matching each prompt — involuntary recall), and a Stop hook (blocks turn-end once to enforce storing durable knowledge) — install all three per AGENTS.md "Harness setup" so recall and store are harness-enforced, not judgment-based.
