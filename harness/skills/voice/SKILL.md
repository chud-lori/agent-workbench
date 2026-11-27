---
name: voice
description: Draft a message in the user's own voice, and learn that voice from the messages they actually sent. Use when the user asks for a Slack reply, DM, PR comment, QA request or any message "in my voice", and when a draft gets corrected. Harvests patterns from the user's own sent messages, stores them as audience-scoped rules, and checks every draft against the recipient's real thread before producing it.
---

# Voice

A draft in the wrong register gets corrected, the correction becomes a note nobody reads, and the next session makes the same mistake. The fix is not a better prompt. It is to read what the user actually sends, store it as a rule scoped to the recipient, and check the draft against that rule before handing it over.

**This skill owns the harvest and the gate. It does not own the storage.** Voice is one context — `audience:<person>`, `channel:<name>` — so a voice rule is an ordinary contextual rule and lives in the rule engine with every other one. Nothing here stores a profile of its own.

## What never gets stored

- **No raw message bodies**, yours or anyone else's. Store the pattern and at most a short phrase, never a copied message.
- **No Slack user IDs.** Resolve `U0…` to a display name first and scope on the name. An id in a rule is unreadable six months later and leaks a surface the user never sees.
- **No third-party content.** A rule describes how *the user* writes, not what a colleague said.

## 1. Harvest

Run when the user asks, or when a draft has just been corrected and the correction looks general.

1. **Read the user's own sent messages** through the Slack connector: `from:me` in the target DM or channel, most recent window first. Twenty messages tells you more than two hundred.
2. **Extract only patterns**, per recipient or channel:
   - language, and whether it switches by recipient
   - form of address: the exact name or nickname used, never a guessed honorific
   - typical length, and whether messages open with context or with the ask
   - sign-offs, recurring phrases, punctuation habits
   - for a channel: thread-title shape, and the request shape (context line, bullets, ask)
3. **Store each pattern as a rule**, one `brain_rule_remember` per pattern, scoped to `audience:<name>` or `channel:<name>`. Put the observed evidence in `example` as a short phrase, and the reason in `why` when the user gave one.
4. **Give each rule trigger words** — `draft`, `reply`, `message`, `msg`, `dm` — so `brain_rules_in_force`
   surfaces it when called with the draft request as `prompt`. The UserPromptSubmit hook matches on scope only,
   from the working directory's `repo:` and `branch:`, so a voice rule arrives when this skill asks for it.
5. **Merge existing corrections.** Recall `preference` notes tagged `communication` or `slack-draft` and store each as a rule in the narrowest scope that explains it. A rule restating one already in the same scope sharpens it rather than duplicating it, so re-harvesting is safe to repeat.

If the Slack connector is absent or unauthenticated, say so in one line and harvest from the brain's existing correction notes alone. A profile built from notes only is thinner, and the user should be told that rather than handed it silently. Never infer a pattern from a single message.

## 2. Gate

Before producing any message in the user's voice:

1. **Recall the rules in force** for the recipient: `brain_rules_in_force` with `context: ["audience:<name>"]`, plus `channel:<name>` when posting to a channel. Scope match means a rule arrives even when the request shares no words with the correction that created it.
2. **Read the recipient's real thread** — the last few messages the user sent *to this person or channel*. The thread outranks the rule: address and language copied from a live thread beat a pattern harvested weeks ago. When they disagree, follow the thread and say so.
3. **Check the draft** against what the rules forbid. Recurring offenders worth checking every time:
   - an emoji or politeness marker the user does not use
   - an em dash
   - headings, bold, or a long structured block in a chat message
   - a shortened ID where the reader needs the full one
   - internal or code vocabulary aimed at someone outside engineering
   - a form of address not seen anywhere in this thread
4. **Output the full draft text**, every time. Never point at "the draft above" — a message the user has to scroll for is a message they have to rewrite.

## 3. Learn

When the user corrects a draft, the correction is a rule, not a one-off fix.

- Store it with `brain_rule_remember` in the **narrowest** scope that explains it. If they corrected a form of address for one person, that is `audience:<that person>`, not every teammate. Propose the scope in one line and let them widen it.
- If a rule had already been surfaced and the draft was still wrong, record `brain_rule_feedback(id, "corrected")`. A rule corrected twice after being shown is wrong, and `brain_context` is the only place that becomes visible.
- Do not store the same correction as a fresh `preference` note as well. One correction, one rule.

## Reading the result

`brain_context audience:<name>` shows every rule governing messages to that person, which rules have never surfaced there (mis-scoped), and which keep being corrected after being shown (wrong). That page is the voice profile. There is no separate artifact to keep in sync.
