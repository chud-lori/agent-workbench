---
name: brain-harvest
description: Weekly retrospective harvest for the agent-workbench brain — scan merged PRs, resolved Jira tickets, and the user's Slack activity for the past window, dedupe against existing brain notes, and propose new notes for the user to approve before storing. Use when the user runs /brain-harvest or asks to "harvest the week", "backfill the brain", or "catch the brain up". Approval-gated — never stores a note without explicit user approval.
---

# Brain Harvest

Turn the brain from write-on-remember into write-on-review: propose durable notes from work that happened **outside** agent sessions (PRs merged from other tools, incidents triaged in Slack, tickets closed without a Claude session). Interactive Claude work is already captured turn-by-turn by the Stop hook — the harvest exists to catch everything else, so dedupe aggressively.

**Hard rule: this skill only PROPOSES. Store nothing until the user explicitly approves each note.**

## 1. Window

Default: last **7 days**. The argument overrides: `/brain-harvest 14d`, `/brain-harvest 2026-07-01`. Compute `SINCE` as a `YYYY-MM-DD` date (use `date -v-7d +%F` on macOS).

## 2. Gather (run sources in parallel)

If a source is unavailable (gh unauthenticated, MCP absent), skip it and say so in the final summary — don't abort the harvest.

**Merged PRs (gh CLI):**

```bash
gh search prs --involves=@me --merged --merged-at=">SINCE" \
  --json title,repository,url,number,closedAt --limit 50
```

For PRs that look knowledge-bearing, pull the why: `gh pr view <url> --json body,comments,mergeCommit`. When a note will cite code, pin the permalink to the merge commit SHA (`repo@sha path:line`) — branch links rot.

**Resolved Jira:** resolve the cloud id once via `getAccessibleAtlassianResources`, then:

```jql
(assignee = currentUser() OR reporter = currentUser()) AND resolved >= -7d ORDER BY resolved DESC
```

Request minimal fields (`summary`, `status`, `resolution`, `project`, `updated`) — responses are verbose. Fetch full description/comments only for tickets that look knowledge-bearing.

**Slack:** search `from:me after:SINCE` (the `from:me` form is what works; searching by handle/email does not). Volume can be hundreds of messages — do NOT read them all. Skim in pages, cluster by channel/thread, and pull `slack_get_thread_replies` only for threads that smell like decisions, incidents, root causes, or ops changes. Resolve every raw user ID (U0…) to a real name via `slack_get_user` or the roster reference notes before showing anything to the user.

## 3. Filter — what counts as durable

Propose only what a future session would otherwise re-derive the hard way:

- decisions with a *why* (and who agreed)
- root causes / gotchas (incident triage conclusions, surprising API behavior, schema quirks)
- ops/infra changes that alter how services run or deploy (migrations, host changes, new alerts)
- new conventions or process rules

Skip: routine work (version bumps, "add test", mechanical fixes), anything trivially derivable from code, anything secret. A merged PR is not a note; the *lesson* in it might be.

## 4. Dedupe against the brain

For each candidate, `brain_recall` with keywords (plus `project` filter). Then:

- already covered → drop it
- extends/corrects an existing note → propose a `brain_amend` (or re-store with `supersedes=[ids]`) instead of a new note, and say which note id it touches
- genuinely new → draft a new note

Expect heavy overlap with recent notes — the week's interactive work is already stored. A good harvest often yields only 3–10 proposals; do not pad.

## 5. Propose and approve

Present the proposals as a numbered list, each showing the full draft: **kind** (decision|fact|gotcha|preference|todo|note|reference), **project** (repo dir name), **tags**, and the complete body **including its source reference** (ticket key, PR URL + `repo@sha` for code, Slack channel + date + permalink, doc name). Mark which are amend/supersede vs new.

Then collect approval with `AskUserQuestion` (multiSelect, batches of ≤4; option label = short title, description = one-line gist) or accept a free-text reply like "store 1, 3, 5". Unapproved drafts are discarded — never stored "for later".

## 6. Store and report

Store approved notes via `brain_remember` (or `brain_amend`/`supersedes` as proposed). If `brain_remember` returns `similar_notes` you missed, stop and reconcile rather than stacking a duplicate. Finish with a short summary: window covered, sources scanned (counts), proposed / stored / amended.
