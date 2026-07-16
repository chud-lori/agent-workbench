---
name: why
description: Code archaeology — answer "why does this code exist?" for a file, function, or line by climbing the evidence chain git blame → commit → PR → ticket → Slack → brain notes. Use when the user runs /why <target>, asks "why is this here?", "what's the history of this code?", or "who decided this and why?". Read-only — reports the recorded why, and says plainly when no why was recorded.
---

# Why

Code answers *what*; only history answers *why*. The why lives somewhere along a chain of surfaces, each one richer than the last:

```
blame → commit message → PR discussion → ticket → Slack thread → brain note
```

Climb only as far as needed — when the commit message already explains it, stop there. But **verify, don't trust**: a commit message says what the author believed; the PR review says what the team actually debated.

## 1. Locate the target

Resolve the argument to `repo + file + line range`. A bare symbol name: find it with `code_search` (agent-workbench MCP) or grep. Ambiguous (multiple matches, no line): show the candidates and ask.

## 2. Blame — but blame lies

`git blame` on the range names the *last* commit to touch each line, which after a refactor or format pass is noise. Get past it:

- `git blame -w -C` ignores whitespace and follows copied/moved code.
- `git log --follow -p -- <file>` walks renames; use it to find the **origin commit** (where the logic first appeared) and any **major rewrites** — those are the commits that carry intent, not the last cosmetic touch.
- `git log -S"<distinctive string>"` (pickaxe) finds when a specific expression was introduced or removed, even across files.

## 3. Climb the chain

For each shaping commit, in parallel where possible:

- **Commit → PR:** `gh api "repos/<org>/<repo>/commits/<sha>/pulls"` (quote the URL — unquoted `?`/`=` break zsh). The PR body and review comments are where the alternatives-considered live.
- **PR/branch/commit → ticket:** extract the ticket key from the title, branch name, or message; pull it via the Jira MCP. The ticket carries the *requirement*; the PR carries the *implementation choice*. Both are halves of the why.
- **Ticket/date → Slack:** `slack_search_messages` with the ticket key or distinctive keywords, bounded with `on:`/`after:`/`before:` around the commit date. Decisions that never made it into the PR live here. **Never surface raw user IDs (U0…)** — resolve names with `slack_get_user` first.
- **Brain:** `brain_recall` with the ticket key, file name, and topic — a stored decision note may answer the question in one hop and name who agreed.

## 4. Answer

Lead with the why in one or two sentences. Then:

- **Evidence chain** — each hop with its surface (SHA, PR#, ticket key, channel + date, brain#id) so the reader can verify any link.
- **Confidence** — say which links are recorded fact versus your inference. If the chain dead-ends (commit says "fix", no PR, no ticket), report that honestly: *"no recorded reason survives; the code dates to <sha> by <name> on <date>"* is a legitimate answer, and better than a plausible invention.
- **Still true?** — if the original reason references something that has since changed (a workaround for a bug long fixed, a limit for a system since retired), flag that the why may have expired.

## 5. Storing

Read-only by default. If the dig surfaced a durable, non-obvious why that took real effort to reconstruct, offer to store it as a brain note with the SHA-pinned permalink — ask first, never automatic.
