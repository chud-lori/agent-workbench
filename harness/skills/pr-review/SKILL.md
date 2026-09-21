---
name: pr-review
description: Review a GitHub PR, branch, or working diff against this project's recorded conventions and six quality axes — comment noise, overengineering, security, algorithmic efficiency, simplicity, and maintainability. Use when the user runs /pr-review, asks to "review this PR", "review PR 123", pastes a GitHub PR link, or asks whether code is over-engineered / insecure / too complex. Reports findings with evidence and a concrete fix; posting to GitHub is approval-gated.
---

# PR review

Find what is wrong and say how to make it simpler. A review that lists no
findings is a valid result; a review that praises, restates the diff, or pads
with nitpicks is a wasted one.

Claude Code's built-in `/code-review` hunts correctness bugs. This one is
opinionated about **shape**: is the code simpler than the problem allows, and
does it match what this project already decided?

**Read `rules.md` next to this file before reviewing.** It holds the numbered
rules (CR-01 … CR-38) in three tiers — Gate / Justify / Lock — and, for each,
the evidence that rule demands. Cite the id in every finding so the author can
look the rule up and argue with it; an unnumbered opinion gives them nothing to
push back on.

## 1. Load the project's memory first

Generic review advice is worthless next to a recorded convention. Before
reading a single line of the diff:

- `brain_recall` on the repo/project name with `kind=gotcha` — this project's
  past bugs. Code that walks back into a recorded trap is the highest-value
  finding you can make, and the cheapest to justify.
- `brain_recall` with `kind=decision` and `kind=preference` on the repo and the
  feature keywords. A change that contradicts a recorded decision is a finding
  even when the code itself is fine.
- When a note decides a point, cite it: `brain#42 — this repo ships without
  unit tests, so "add tests" is not a finding here.`

Recorded conventions **outrank** your defaults. If the project consistently
does something you would not, that is the house style, not a defect.

## 2. Get the diff

```bash
gh pr view <n> --json title,body,url,headRefName,baseRefName,additions,deletions
gh pr diff <n>                       # the actual change
gh pr view <n> --json files --jq '.files[].path'
```

Branch or local work instead: `git diff <base>...HEAD`, or `git diff` for
uncommitted. A pasted PR URL gives you the number.

**Review the diff, not the repo.** Pre-existing problems in untouched code are
out of scope unless the change makes them worse — say so explicitly if you
mention one at all.

Read enough surrounding code to judge the change fairly: a function that looks
over-abstracted may have three callers you cannot see in the diff.

## 3. The six axes

For each, the bar is a **specific, checkable claim** — not a smell. The rule
ids in `rules.md` are grouped the same way: security CR-01…06, correctness and
data CR-07…11, efficiency CR-12…16, overengineering CR-17…21 plus CR-38, comment hygiene
CR-22…26, readability and maintainability CR-27…34, plus the recorded-knowledge
rules CR-35…37 that outrank all of them.

**Comment noise.** Comments that restate the code (`// increment i`), commented-out
code, stale comments contradicting the code beside them, docstrings repeating the
signature, banner/decoration comments. Keep comments that explain *why*, name a
non-obvious constraint, or cite a ticket. A comment explaining a workaround is
load-bearing — never flag it.

**Overengineering.** Abstractions with exactly one implementation, config for
things that never vary, layers that only forward calls, premature generality,
patterns imported for their own sake, options nobody asked for. **A finding here
must name the simpler alternative concretely** ("this factory has one product —
call the constructor"). Without that, it is taste, not a finding.

**Security.** Injection (SQL/shell/template), secrets or tokens in code or logs,
missing authorization on a state-changing path, unsafe deserialization, path
traversal, weak crypto, unvalidated redirects, PII in logs or error messages.
State the attacker's input and what it reaches — a security claim without a
path is noise. Real ones outrank everything else.

**Algorithmic efficiency.** N+1 queries, work inside a loop that belongs outside,
nested iteration over collections that grow, repeated recomputation, unbounded
memory, missing pagination or index on a queried column. **Name the scale where
it hurts** ("fine at 10 rows, this table has 68M"). Constant-factor
micro-optimisation is not a finding.

**Simplicity and readability.** Deep nesting that an early return would flatten,
functions doing several unrelated things, boolean parameters that switch
behaviour, names that mislead, clever one-liners that need a second read,
inconsistent handling of the same concept. Prefer straightforward over compact.

**Maintainability.** Copy-paste with small mutations, hidden coupling, swallowed
errors (`except: pass`), missing handling for a failure the code can actually
hit, magic values without a name, behaviour changes with no test where the
project does test.

## 4. Verify before reporting

Every finding needs evidence someone can check:

- Open the file and confirm — a diff hunk hides context that can make a finding
  wrong.
- For a bug, give inputs or state that produce the wrong result. If you cannot
  construct it, downgrade to a question rather than asserting a defect.
- Say what is verified versus suspected. A confident wrong finding costs the
  author more time than silence.
- Skip formatting, import order, and anything a linter owns — unless it changes
  behaviour.

## 5. Report

One line per finding, worst first, each citing its rule:

```
path:line — CR-14 — what is wrong, under what condition. Fix: <the concrete change>.
```

Cite `brain#id` too wherever a recorded note decided the call (CR-35…37).

Then close with an explicit gate — not a summary, a verdict:

```
Gate:    FAIL — CR-01, CR-07        (or: none)
Justify: 2 open — CR-14, CR-17      (or: none)
Lock:    3 open                     (or: none)
Verdict: FAIL / PASS WITH FIXES / PASS
```

The verdict follows mechanically, so it cannot drift into diplomacy:

- **FAIL** — any Gate-tier finding stands. Merging is wrong until it is fixed.
- **PASS WITH FIXES** — no Gate findings, but Justify or Lock findings are open.
  Name which must be resolved before merge and which are follow-ups.
- **PASS** — nothing stands. Say it in one line and stop; do not manufacture a
  finding to look thorough, and do not pad with praise.

A review that reaches PASS honestly is more useful than one that reaches it
with three invented nits.

Say "no findings" plainly when that is true. Do not restate the diff, do not
open with praise, and do not invent a finding per axis — most changes trip two
or three at most.

## 6. Posting to GitHub is approval-gated

Never post automatically. Show the review, then ask. On approval:

```bash
gh pr comment <n> --body-file <file>          # one summary comment
gh pr review <n> --comment --body-file <file> # a review, not an approval
```

Never `--approve` a PR on the user's behalf. Posting is public and permanent —
one confirmation, every time.

## 7. Store what is durable

The review itself is not durable knowledge — do not store it. A root cause worth
remembering, a convention the team just settled, or a trap that will recur is a
normal `brain_remember` with its source (`repo@sha path:line`, PR number),
proposed to the user rather than stored silently.
