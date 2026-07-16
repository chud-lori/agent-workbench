---
name: standup
description: Build a personal standup for a day (default yesterday) by merging git commits, PRs, Slack, calendar, and brain notes into a paste-ready Done / Today / Blockers summary. Use when the user runs /standup or asks "what did I do yesterday?", "what did I work on Monday?", or wants a standup written. Read-only — reconstructs the day from primary sources, never invents it.
---

# Standup

Answer "what did I do?" from **evidence**, not memory. The brain stores durable facts, not an activity log — `brain_recall` alone cannot answer this, and neither can any single source:

- **git** = what you *shipped* (including unpushed branch work)
- **Slack** = what you *said and decided*
- **calendar** = where your hours *went* (a day of meetings looks like an empty day in git)
- **PRs** = what's *landed* and what's *waiting on you*

Miss one and the standup lies. A day with zero commits is not a day with zero work.

## 1. Window

Default: **yesterday**. Arguments override: `/standup today`, `/standup 2026-07-13`, `/standup 3d`.

Watch the weekend and the boundary:

- On a **Monday**, "yesterday" is Sunday — widen to Friday and say you did.
- Work announced late the previous evening ("I'll include X in tomorrow's deploy") belongs to the next day's story but falls outside a strict window. Widen by a day when an item references something flagged earlier.

## 2. Gather — all sources, in parallel

Run these concurrently. If a source is unavailable (gh unauthenticated, an MCP absent), skip it and **say so in the summary** — a silently missing source reads as "nothing happened there."

**Git — commits across every local repo** (`agent-workbench` MCP, no network):

```
recent_activity(since="yesterday", until="yesterday")
```

Scans all branches, so unpushed work that `gh` cannot see still shows up. `subject` lines are noisy — use them to jog memory, never as standup lines verbatim.

**PRs (gh CLI)** — what actually landed, and what's on your plate:

```bash
gh search prs --author @me --created YYYY-MM-DD --json number,title,repository,url
gh search prs --author @me --merged  YYYY-MM-DD --json number,title,repository,url
gh search prs --review-requested @me --updated YYYY-MM-DD --json number,title,repository
```

**Slack — what you said:**

- `slack_search_messages("from:me on:YYYY-MM-DD")`. Use `from:me` — searching by handle or email does not work. Always bound with `on:`; a bare `after:` returns newest-first, caps results, and **silently drops the earlier day**.
- `from:me` returns only *your* messages, which is half a conversation. Decisions, approvals, and pushback from others are the half that matters — follow up with `slack_get_thread_replies` on threads that look like decisions, and `slack_get_channel_history` for DMs (`D…` ids surface in search results; there is no "list my DMs").
- **Never surface raw user IDs (U0…).** Resolve to real names with `slack_get_user` before quoting or summarizing anyone.

**Calendar — where the hours went:**

```
calendar_list_events(timeMin=<day start ISO>, timeMax=<day end ISO>)
```

Meetings are work. A design review or an incident call belongs in **Done**. Skip declined events and solo focus blocks unless they carry real content.

**Brain — decisions you already recorded that day:**

```
brain_recall(since="yesterday", until="yesterday")
```

Not an activity log, but notes stored that day often carry the *why* behind a commit, and name who agreed.

## 3. Verify before presenting

**Never present a raw search as fact.** `from:me` shows what *you claimed*, not what was agreed. Before a line goes in:

- Read the thread. Confirm who actually decided, and whether your proposal was accepted or is still open.
- The two failure modes are **misattribution** (crediting the wrong person for a decision) and **stale claims** (reporting as done something still under discussion). The thread is the source of truth; your sent messages are not.
- If `recent_activity` reports commits on a branch, that is not the same as shipped. Check whether it merged before putting it in Done.

## 4. Format

Group by **initiative, not by channel or repo** — the team cares about the work, not where it happened. Three buckets:

- **Done** — what shipped or moved, with the surface in parens (PR#, repo, channel, meeting)
- **Today** — next actions
- **Blockers / waiting** — who or what you're waiting on, and the open question

Keep it paste-ready and plain. Cite a surface for every Done line so anyone can trace it.

## 5. This is personal — do not store it

A standup is a summary of one day, not durable knowledge. **Do not `brain_remember` the standup itself**, and do not promote it to shared references. If the day surfaced something genuinely durable — a root cause, a decision with a why, a gotcha — that is a normal `brain_remember` with its own source reference, separate from the standup.
