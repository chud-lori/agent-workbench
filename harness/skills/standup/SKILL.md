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

**Read `~/.config/agent-workbench/fan-out-and-verify.md` before gathering.** It holds the convention every evidence skill shares: resolve exact keys first, gather in parallel, name any source that is absent or unauthenticated, never surface raw Slack ids, verify before presenting, cite a surface for every line, and do not store the output.

**Git — commits across every local repo** (`agent-workbench` MCP, no network):

```
recent_activity(since="yesterday", until="yesterday")
recent_activity(since="yesterday", until="yesterday", repo="<each repo with commits>")
```

The first call returns per-repo commit counts; the second returns one repo's commits. Scans all branches, so unpushed work that `gh` cannot see still shows up. `subject` lines are noisy — use them to jog memory, never as standup lines verbatim.

**PRs (gh CLI)** — what actually landed, and what's on your plate:

```bash
gh search prs --author @me --created YYYY-MM-DD --json number,title,repository,url
gh search prs --author @me --merged  YYYY-MM-DD --json number,title,repository,url
gh search prs --review-requested @me --updated YYYY-MM-DD --json number,title,repository
```

**Slack — what you said:**

- `slack_search_messages("from:me on:YYYY-MM-DD")`. Use `from:me` — searching by handle or email does not work. Always bound with `on:`; a bare `after:` returns newest-first, caps results, and **silently drops the earlier day**.
- `from:me` returns only *your* messages, which is half a conversation. Decisions, approvals, and pushback from others are the half that matters — follow up with `slack_get_thread_replies` on threads that look like decisions, and `slack_get_channel_history` for DMs (`D…` ids surface in search results; there is no "list my DMs").

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

`from:me` shows what *you claimed*, not what was agreed: confirm in the thread who actually decided, and whether your proposal was accepted or is still open. Also:

- If `recent_activity` reports commits on a branch, that is not the same as shipped. Check whether it merged before putting it in Done.

## 4. Format

Group by **initiative, not by channel or repo** — the team cares about the work, not where it happened. Three buckets:

- **Done** — what shipped or moved, with the surface in parens (PR#, repo, channel, meeting)
- **Today** — next actions
- **Blockers / waiting** — who or what you're waiting on, and the open question

Keep it paste-ready and plain.

## 5. This is personal — do not store it

A standup is a summary of one day; the convention's storage rule applies as written.
