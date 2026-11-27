# Fan out and verify

The convention every evidence skill shares (`/standup`, `/brain-harvest`,
`/postmortem`, `/why`, `/meeting-prep`). Each skill points here instead of
restating it, and keeps its own prose only where it differs.

`setup.sh` copies this file to `~/.config/agent-workbench/fan-out-and-verify.md`
so an installed skill can read it at a fixed path.

## 1. Resolve exact keys first

**Resolve exact keys first.** Before searching in parallel or briefing a subagent, resolve each named person, repo, ticket and channel to an exact key (account id, author email, `org/repo`, ticket key, channel id), say how you confirmed it, and use only that key in every search and brief, never a looser name match. If a key returns a different count than the name did, find out why before going on.

## 2. Gather from every source in parallel

Run the skill's sources concurrently, not one after another. No single source
answers the question; a skill that reads one and stops reports a fraction as
the whole.

If a source is absent or unauthenticated (`gh` not logged in, a connector not
installed), skip it, keep going with the rest, and **name it in what you hand
the user**. A silently missing source reads as "nothing happened there."

## 3. Never surface raw Slack user IDs

Resolve every `U0…` id to a real name with `slack_get_user`, or a roster
reference note in the brain, before anyone appears in the output.

## 4. Verify before presenting

A search hit is a claim, not a fact. Before a line goes in:

- Read the thread. Your own sent message shows what you proposed, not what was
  agreed; a decision is only decided when the replies show agreement.
- Guard against the two failure modes: **misattribution** (crediting the wrong
  person for a decision or position) and **stale claims** (reporting as done
  something still under discussion). Attribute by name.

## 5. Cite a surface for every line

Every line you present names where it came from: PR number, commit SHA, ticket
key, channel + date, meeting, or `brain#id`, so anyone can trace it.

## 6. Do not store the output

The summary, brief, or document a skill produces is not durable knowledge. Do
not `brain_remember` it and do not promote it to shared references. A durable
fact it surfaced (a root cause, a decision with a why, a gotcha) is a separate
note with its own source reference. A skill that says to ask before storing, or
whose job is storing, follows its own rule here.
