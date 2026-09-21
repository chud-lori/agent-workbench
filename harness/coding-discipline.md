# Coding discipline

Four rules for *how* to make a change, as opposed to which tools to use. They
apply to any agent in any harness, in any repo.

`setup.sh` copies this file to `~/.config/agent-workbench/coding-discipline.md`
so it has a fixed path on every machine. Read it before a nontrivial change; the
shared standing instructions carry the one-line version.

**The tradeoff, stated up front:** these rules trade speed for caution. On a
one-line typo fix, obeying all four costs more than the change is worth — use
judgment. They earn their keep the moment a change touches code someone else
will read, extend, or debug.

---

## 1. Think before coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before the first edit:

- **State the assumptions you are acting on.** Not all of them — the ones that,
  if wrong, mean the work is wasted. "I'm assuming this runs once per request,
  not per row" is worth a line; "I'm assuming Python is installed" is not.
- **When a request has two plausible readings, present both.** Do not silently
  pick one and build it. Say which you would choose and why, then proceed with
  it if the cost of being wrong is low, or ask if it is high.
- **Push back when a simpler path exists.** Say what it is and what it gives up.
  Then do what was asked if the human still wants it — one clear objection, not
  repeated resistance.
- **When something is genuinely unclear, stop and name it.** "I don't know
  whether X" beats a confident guess. A question costs a minute; a wrong guess
  costs the review, the revert, and the trust.

The failure this prevents: plausible code built on an unstated wrong premise,
which is expensive precisely because it looks finished.

**Check before you start:** can you say, in one sentence, what "done" means and
what you are assuming to get there?

---

## 2. Simplicity first

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked, however obvious the next one seems.
- No abstraction for a single use. One implementation needs no interface, one
  caller needs no factory, one case needs no strategy.
- No configurability nobody requested. A constant is simpler than a setting, and
  a setting nobody sets is a setting nobody tests.
- No error handling for impossible states. Handle what can actually happen;
  a defensive branch that cannot execute is untested code that reads as tested.
- No premature generality. Write for the case in front of you; generalise on the
  second real case, not in anticipation of it.

If the result is 200 lines and 50 would do, rewrite it before showing it.

**Check before you finish:** would an experienced reviewer of this codebase call
this overcomplicated for what it does? If yes, cut.

---

## 3. Surgical changes

**Touch only what you must. Clean up only your own mess.**

- Do not improve adjacent code, comments, or formatting. A diff that mixes the
  fix with unrelated tidying is harder to review and harder to revert, and it
  hides the actual change.
- Do not refactor what is not broken, and not part of the request.
- Match the surrounding style even where you would write it differently:
  naming, error handling, comment density, test shape. Code that reads as
  foreign is a defect even when it works.
- Notice unrelated dead code? Mention it. Do not delete it — it may be load
  bearing in a way the local file does not show.
- Remove the orphans **your** change created: imports, variables, helpers that
  your edit made unused. Leave pre-existing dead code alone.

**Check before you finish:** does every changed line trace to something the
human asked for? If a line does not, remove it or say why it is there.

---

## 4. Goal-driven execution

**Define success criteria. Loop until verified.**

Turn the task into something you can check, then check it:

| Vague | Verifiable |
|---|---|
| "add validation" | write tests for the invalid inputs, then make them pass |
| "fix the bug" | write a test that reproduces it, then make it pass |
| "refactor X" | tests pass before and after, with no behaviour change |
| "make it faster" | measure it, state the number, beat it, measure again |

For multi-step work, state the plan as steps paired with their checks:

```
1. <step> -> verify: <the command or observation that proves it>
2. <step> -> verify: <...>
```

Then run the checks and report what they actually returned. "Should work" is not
a result; neither is a green test you did not run. If a check fails and you
cannot fix it within scope, report the failure with its output rather than
narrowing the task until it passes.

A strong criterion lets you finish without asking. A weak one ("make it work")
guarantees another round trip.

**Check before you finish:** what did you run, and what did it print?

---

## How this is enforced

These are instructions, so they hold only as far as the agent complies.
`/pr-review` checks the same ideas after the fact, where they are numbered and
citable: simplicity as CR-17…CR-21, surgical scope as CR-38 and CR-34,
verification as CR-11. A review can cite the rule; this file explains it.
