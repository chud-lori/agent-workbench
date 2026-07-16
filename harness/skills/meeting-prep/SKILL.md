---
name: meeting-prep
description: Build a one-page brief for an upcoming meeting by merging the calendar event with related Slack threads, Jira tickets, PRs, and brain notes. Use when the user runs /meeting-prep, asks "prep me for my next meeting", "what's this meeting about?", or "what should I bring to <meeting>?". Read-only — briefs from evidence, never invents agenda items.
---

# Meeting prep

Walking into a meeting having re-read the thread beats walking in with a good memory. This skill assembles that re-read: what the meeting is, what changed since last time, and what you owe or are owed.

## 1. Pick the event

`calendar_list_events` from now to end of day (default). Take the **next non-declined event**; skip solo focus blocks. Arguments override: `/meeting-prep 15:00`, `/meeting-prep "roadmap review"`, `/meeting-prep tomorrow`. Multiple matches: show the candidates and ask.

From the event, extract the topic keywords (title + description), the attendee list, and any linked docs.

## 2. Gather — all sources, in parallel

Skip an unavailable source and **say so in the brief**.

- **The event itself:** agenda in the description; linked Google Docs via `docs_get_text` / `workspace_get_from_url` — an agenda doc with comments is often the whole prep.
- **Last time** (recurring meetings): `calendar_list_events` over the past few weeks for the same title, then search Slack around that date for notes or follow-ups. "What we said last time" is the most valuable section of the brief.
- **Slack:** `slack_search_messages` with the topic keywords, bounded to the recent window (`after:`); plus threads involving the organizer on the topic. **Never surface raw user IDs (U0…)** — resolve every name with `slack_get_user` before it appears in the brief. Attendee emails from the calendar resolve to Slack names the same way.
- **Jira:** JQL on the topic/project for tickets moved recently or blocked — the tickets attendees are likely to bring up.
- **Git/PRs** (when the meeting is about a workstream): `recent_activity` and `gh search prs` scoped to the topic since the last occurrence — what actually shipped versus what was promised.
- **Brain:** `brain_recall` on the topic keywords (add `thread=` if the storyline has a tag) — recorded decisions and open todos about this exact topic, with who agreed.

## 3. Verify

The brief states facts people will act on in front of each other — the embarrassment cost of a wrong line is high:

- A decision is only "decided" if the thread shows agreement — your own sent message proposing it does not count. Read replies before writing "we agreed".
- Check ticket status live rather than trusting a Slack claim from last week.
- Attribute positions to the right person, by name.

## 4. Format — one page, five sections

- **What this meeting is** — one line: purpose, who called it, recurring or one-off.
- **Since last time** — what shipped, what moved, what stalled (recurring meetings only). Cite a surface per line (PR#, ticket, channel + date).
- **You owe / owed to you** — commitments in either direction, with where they were made.
- **Likely topics** — from the agenda, recent tickets, and active threads; one line each with the current state.
- **Open questions** — things worth raising, including stale decisions that were never closed.

Plain text, paste-ready, no fluff. If a section has nothing, drop it.

## 5. Do not store the brief

A brief is about one hour of one day. If prep surfaces something durable — a decision you'd forgotten was made, a commitment with a date — that is a normal `brain_remember` with its source thread, separate from the brief.
