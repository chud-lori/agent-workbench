# Review rules

Numbered so a finding can be cited rather than asserted: `foo.py:120 — CR-14`.
A reader can look the rule up and disagree with it; an unnumbered opinion gives
them nothing to argue with.

Three tiers, by what they cost if shipped:

- **Gate** — merging is wrong until fixed. Wrong output, lost data, exposure.
- **Justify** — allowed only with a reason on the PR. Usually a shape problem:
  the code works but costs more than the problem does.
- **Lock** — fix before merge unless the change is trivial or the file is
  already consistently the other way.

Every rule states the **evidence it demands**. A finding without that evidence
is taste, and taste goes in a comment, not a review.

## Security — tier: Gate

| id | rule | evidence required |
|---|---|---|
| CR-01 | No untrusted input reaches an interpreter (SQL, shell, template, eval, deserializer) without parameterisation or escaping | the input's entry point, and the line it reaches |
| CR-02 | No secret, token, key, or credential in source, config, logs, or error text | the literal's location; never quote the value itself |
| CR-03 | Every state-changing path checks authorisation, not just authentication | the path, and the identity check that is missing |
| CR-04 | No PII in logs, metrics, analytics, or exception messages | the field, and where it is emitted |
| CR-05 | User-controlled paths are confined; no traversal past the intended root | the input, and the unvalidated join |
| CR-06 | Crypto is a vetted primitive with adequate parameters — no home-rolled scheme, no broken hash for a security purpose | the algorithm and its use |

## Correctness and data — tier: Gate

| id | rule | evidence required |
|---|---|---|
| CR-07 | A destructive operation (delete, truncate, overwrite, migration) is bounded, reversible, or gated | the operation, and what stops it running wide |
| CR-08 | Boundary cases behave: empty, null, zero, one item, duplicate, maximum, timezone edge, non-ASCII | the specific input and the wrong result it yields |
| CR-09 | Failures are not silently swallowed — no bare `except: pass`, no ignored error return, no empty catch | the handler, and the failure it hides |
| CR-10 | Concurrency and ordering assumptions hold, or are enforced | the interleaving that breaks it |
| CR-11 | A behaviour change is covered by a test, where the project tests at all | the changed behaviour, and the absent test |

## Efficiency — tier: Justify

| id | rule | evidence required |
|---|---|---|
| CR-12 | No query per item where one query would do (N+1) | the loop, and the per-iteration call |
| CR-13 | Work that does not vary is not repeated inside a loop | the invariant expression |
| CR-14 | Iteration over a collection that grows is not nested without bound | **the scale where it hurts** — current row/item count, not a hypothetical |
| CR-15 | Unbounded reads are paginated or capped; unbounded memory is bounded | the missing limit, and the realistic size |
| CR-16 | A filtered or sorted column is indexed | the query, and the index that is absent |

Constant-factor micro-optimisation is **not** a finding. Neither is an
efficiency claim without a number attached.

## Overengineering — tier: Justify

| id | rule | evidence required |
|---|---|---|
| CR-17 | An abstraction has more than one real implementation, or is deleted | **the simpler alternative, concretely** ("one product — call the constructor") |
| CR-18 | Configuration exists for something that actually varies | the setting, and the single value it ever takes |
| CR-19 | No layer that only forwards calls | the pass-through, and what it would look like removed |
| CR-20 | Generality is paid for when needed, not in advance | the unused axis of flexibility |
| CR-21 | The change is the smallest one that solves the stated problem | the parts of the diff the problem does not require |
| CR-38 | No change to code the request does not require: no drive-by refactor, reformat, or comment tidy of adjacent code, and no deletion of pre-existing dead code (report it instead) | the changed line, and the absence of anything in the request that asks for it |

Without the named alternative, CR-17 to CR-21 and CR-38 are opinions. State them as
questions instead.

## Comment hygiene — tier: Lock

| id | rule | evidence required |
|---|---|---|
| CR-22 | No comment that restates the code it sits on | the comment and the line |
| CR-23 | No commented-out code — delete it; history keeps it | the block |
| CR-24 | No comment contradicted by the code beside it | both, quoted |
| CR-25 | No docstring that only repeats the signature | the docstring |
| CR-26 | No decorative banners, section dividers, or scaffolding notes left behind | the lines |

**Never flag** a comment that explains *why*, records a non-obvious
constraint, names a workaround and its cause, or cites a ticket. Those are
load-bearing: deleting them loses knowledge the code cannot express.

## Readability and maintainability — tier: Lock

| id | rule | evidence required |
|---|---|---|
| CR-27 | Nesting is flattened where an early return or guard clause would do | the depth, and the guard that removes it |
| CR-28 | A function does one thing; unrelated responsibilities are separated | the two jobs it holds |
| CR-29 | No boolean parameter that switches behaviour — separate functions | the call sites, showing what `True` means |
| CR-30 | Names say what the thing is; no misleading or stale name | the name, and what it actually holds |
| CR-31 | One concept is handled one way across the change | the two inconsistent sites |
| CR-32 | No copy-paste with small mutations where a parameter would serve | the duplicated blocks |
| CR-33 | Magic values are named | the literal and its meaning |
| CR-34 | New code matches the surrounding file's style, idiom, and comment density | the surrounding convention it breaks |

## Recorded-knowledge rules — tier: Gate

These outrank everything above, because they encode what this project already
learned the hard way:

| id | rule | evidence required |
|---|---|---|
| CR-35 | The change does not re-enter a recorded `gotcha` for this project | the note id, and the line that repeats it |
| CR-36 | The change does not contradict a recorded `decision` without saying so | the note id, and the contradiction |
| CR-37 | A recorded `preference` or house convention is followed over a generic default | the note id |

A recurrence is more urgent than a novelty: the project has already paid for
that lesson once.

## What is never a finding

Formatting, import order, line length, and anything a linter or formatter
owns — unless it changes behaviour. Style preferences the file already
contradicts consistently. Missing tests in a project that does not test.
Praise.
