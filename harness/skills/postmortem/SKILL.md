---
name: postmortem
description: Reconstruct an incident from evidence — Slack, git commits across every local repo, deploys, PRs, tickets — into a timeline, a blameless five-whys, and a draft postmortem with action items. Use when the user runs /postmortem, asks to "write a postmortem", "do an incident review", or "what actually happened with <incident>". Evidence-first — never writes the story from memory; storing the root cause in the brain is proposed, never automatic.
---

# Postmortem

Write the incident from **evidence**, not recollection. Memory of an incident is written by adrenaline; the timeline in Slack and git is written by clocks. Where they disagree, the clocks win.

## 1. Scope

Establish three anchors before gathering — ask the user for whatever is missing:

- **What broke** (service, feature, symptom)
- **When** (detection time and rough duration; widen the gather window to one day *before* detection through one day after resolution — causes precede symptoms)
- **Where it was discussed** (incident channel, thread, or ticket)

## 2. Gather — all sources, in parallel

Skip any unavailable source and **say so in the draft** — a silently missing source reads as "nothing happened there."

**Slack — the human timeline:**

- `slack_get_channel_history` on the incident channel for the window; `slack_get_thread_replies` on every thread that contains a decision, a page, or a "fixed it" claim.
- `slack_search_messages` with the service name and error strings bounded by `on:`/`before:`/`after:` to catch discussion outside the incident channel — early warnings often live in a team channel days earlier.
- **Never surface raw user IDs (U0…).** Resolve every participant to a real name with `slack_get_user` before they appear in the timeline.

**Git — what changed and when** (`agent-workbench` MCP):

```
recent_activity(since=<day before detection>, until=<day after resolution>)
```

All local repos, all branches — the change that caused an incident is frequently in a repo nobody suspected. Note commits that land suspiciously close to detection time.

**Deploys:** if a gitops/deploy repo exists locally, its commit log in the window *is* the deploy history — read it directly. Otherwise ask the user where deploys are recorded.

**PRs and reverts (gh CLI):**

```bash
gh search prs --merged --repo <org/repo> "merged:YYYY-MM-DD..YYYY-MM-DD" --json number,title,url,mergedAt
```

Reverts and hotfixes in the window mark the mitigation moment.

**Tickets:** the incident ticket plus anything linked to it (Jira MCP).

**Brain:** `brain_recall` with the service name, plus `since`/`until` over the window — prior gotchas about the same component are candidate contributing factors, and a recorded near-miss is gold.

## 3. Timeline

One list, one timezone (state it), every entry cited to a surface: Slack channel + timestamp, commit SHA, PR number, deploy commit. Mark the four milestones explicitly: **cause introduced → detected → mitigated → resolved**. The gap between the first two is the finding that most often changes behavior.

Verify before an entry goes in:

- A "this is fixed" message is a claim; the metric recovering or the revert merging is the fact.
- Match clock skew: Slack timestamps are wall time, commit author dates can be hours older than push/deploy time. When causality matters, prefer merge/deploy timestamps over author timestamps.

## 4. Analysis — blameless

Five-whys from the symptom down. Name systems, gaps, and process — a person's action is never a root cause; the condition that made the action reasonable is. Separate three things that always get conflated:

- **Trigger** — the change or event that set it off
- **Root cause** — the pre-existing condition that made the trigger harmful
- **Contributing factors** — what widened the blast radius or slowed detection/mitigation

## 5. Draft

Sections: **Impact** (who/what/how long, numbers where evidence supports them) · **Timeline** · **Root cause & trigger** · **What went well / What went poorly** · **Action items**. Every action item gets an owner and a verifiable done-condition — "improve monitoring" is not an action item; "alert when X exceeds Y" is. Skipped sources are listed at the bottom.

## 6. Store the lesson, not the document

The postmortem document belongs wherever the team keeps postmortems — do not `brain_remember` it. What *does* belong in the brain is one `gotcha`: the root cause, the fix, and the source references (incident channel + date, ticket key, fixing commit SHA). **Propose the note text and ask before storing.** If the same component already has a gotcha, extend it with `brain_amend` instead of stacking a near-duplicate.
