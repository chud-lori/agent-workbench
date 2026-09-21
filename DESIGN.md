# DESIGN.md

Design direction for the Agent Workbench GitHub Pages site (`docs/index.html`).

Nothing here is invented. Every value is pulled from something the repo already
decided, with the source cited. Line references to `docs/index.html` point at the
file as it stood **before** this rewrite, at commit `e8a2197`; read them with
`git show e8a2197:docs/index.html`. Anything the repo has not decided sits under
**Open** as a question for the owner, not as a guess.

---

## Identity

Agent Workbench is a local, dependency-free MCP server plus CLI: an FTS code
index over your repos, a persistent cross-tool "brain", and local AI-setup
diagnostics. It makes no LLM calls and no network calls.

- Source: `AGENTS.md:3` ("Local, dependency-free MCP server + CLI: FTS code index over `~/repo`, persistent cross-tool memory ("brain"), and local AI-setup diagnostics. No LLM calls; deterministic retrieval only.")
- Source: `pyproject.toml:4` (`description`), `pyproject.toml:14` (`dependencies = []`)
- Source: verified by inspection, `agent_workbench/*.py` imports only `argparse, dataclasses, datetime, hashlib, json, os, pathlib, re, shutil, sqlite3, subprocess, sys, time, typing`. No `urllib`, `socket`, `http`, or `requests`.

The audience is one person: the developer who installed it, reading it as
reference while their agent is running. It is not a product being sold.

- Source: `README.md` "License" section ("Currently unlicensed (all rights reserved)")
- Source: `agent_workbench/config.py:19` (state defaults to a path under the author's own `~/Projects`)

The site therefore has to work as documentation. The tool reference, the
configuration table, and the install steps are the page; there is nothing to
convert a visitor to.

## Personality

Taken from how the repo already writes about itself: plain, evidence-first,
willing to name its own limits in the same sentence as a capability.

- "Notes without breadcrumbs are dead ends." (`AGENTS.md`, standing instruction 2)
- "The brain is a store of durable facts, **not an activity log**." (`AGENTS.md`, standing instruction 4)
- "Instruction-based vs hook-enforced. Standing instructions make agents *likely* to use the brain; the SessionStart hook makes recall *guaranteed*." (`README.md`, Design notes)
- "Missing/empty file = guard inactive (hook is a silent no-op)." (`harness/hooks/pretooluse-guard.sh:11`)

That last habit is the voice: every claim arrives with the condition under
which it is false. The site copy keeps it. No superlatives, no adjectives the
code cannot back.

## Palette

The brand colors already exist in the logo, which predates the site and is
committed in two places (`assets/logo.svg`, `docs/logo.svg`, byte-identical).
They are an established identity, not a color picked for the page.

| Token | Value | Source |
|---|---|---|
| Indigo | `#4f46e5` | `docs/logo.svg:4` (badge gradient stop 0) |
| Violet | `#6d28d9` | `docs/logo.svg:5` (badge gradient stop 0.55) |
| Purple | `#9333ea` | `docs/logo.svg:6` (badge gradient stop 1) |
| Amber (core node) | `#f59e0b` | `docs/logo.svg:10` (core gradient stop 1) |
| Amber (light) | `#fde68a` | `docs/logo.svg:9` (core gradient stop 0) |

The existing page already translated those into UI tokens, and those carry
over:

| Token | Dark | Light | Source |
|---|---|---|---|
| `--bg` | `#0b0b14` | `#fafaff` | `docs/index.html:11`, `:24` |
| `--bg-soft` | `#14141f` | `#f1f1f8` | `docs/index.html:12`, `:25` |
| `--card` | `#181826` | `#ffffff` | `docs/index.html:13`, `:26` |
| `--border` | `#2a2a3d` | `#e3e3ef` | `docs/index.html:14`, `:27` |
| `--text` | `#e7e7f0` | `#1c1c2e` | `docs/index.html:15`, `:28` |
| `--muted` | `#9d9db3` | `#5d5d75` | `docs/index.html:16`, `:29` |
| `--accent` | `#8b7bf7` | `#5b48d9` | `docs/index.html:17`, `:30` |
| `--code-bg` | `#101018` | `#f4f4fa` | `docs/index.html:19`, `:32` |
| `--amber` | `#f5b942` | (dark only in the old file) | `docs/index.html:20` |

Structure of the palette for the rewrite: two core colors (the violet family
as the interactive/structural color, the neutral ink-to-paper ramp as the
ground) plus **one** accent, amber. Amber is the logo's core node, the single
lit element in a white mesh, so the site uses it the same way: one marked thing
per screen, never as a second link color.

Amber is used as a mark and a rule, never as body text on a light ground, since
`#f59e0b` on `#fafaff` does not reach 4.5:1.

Both themes ship complete. The old file set `--amber` only inside the dark
block (`docs/index.html:20`), which is a gap the rewrite closes.

## Typography

Two stacks, both already chosen by the repo, both kept for the same reason the
product exists: zero dependencies, so no webfont is fetched.

- Sans: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`. Source: `docs/index.html:39`. Reason: the product's hard constraint is no network calls at runtime; a site that loads a Google font to describe it would contradict its own subject.
- Mono: `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace`. Source: `docs/index.html:87`. Reason: every tool name, env var, and CLI command on the page is a literal string the reader will type. Mono marks "this is copyable text", not "this is a tech product".

Mono is never used for headings or display text. Uppercase with wide tracking
(`docs/index.html:96`, `text-transform: uppercase; letter-spacing: .06em`) is
dropped: it was decoration on table headers and step labels.

## Mood

Reference material, read at a desk with an agent running in the next window.
Close to a man page that happens to be legible. The page should be scannable
by someone looking for one env var name, and readable start to finish by
someone deciding whether to install it.

The mood follows the product's own promise: deterministic, local, boring in the
way infrastructure should be boring.

- Source: `README.md`, Design notes ("Lexical, not RAG. Retrieval is SQLite FTS5 + bm25 - exact, explainable, zero-dependency.")

## Dial

`Dial: ENERGY 1 / RHYTHM 2 / MOTION 1`

Derived, not stated by the owner. Awaiting the owner's confirmation.

- ENERGY 1: the product sells determinism and states its own failure modes in its docs. A page that says hello loudly would misrepresent it. Anchor: closer to GOV.UK than to Stripe.
- RHYTHM 2: consistent with a few breaks, because the content genuinely differs in shape. A 20-row tool reference, a 6-row env var table, a 4-item hook sequence, and a two-line install block are not the same object and should not be drawn as the same card.
- MOTION 1: hover and focus states only. The product makes no network calls and does nothing asynchronous on this page; motion would be asserting activity that does not exist. No scroll reveals, no loops.

## Constraints

Hard constraints, all sourced from how the thing is already built:

1. Single self-contained HTML file with inline CSS and JS. No CDN, no build step, no external font or script. Source: `docs/index.html` is one file with an inline `<style>` and no `<script>` or external `<link>` except `logo.svg`.
2. The only other asset is `docs/logo.svg`, which must stay byte-identical to `assets/logo.svg` (verified with `diff`).
3. Published from `docs/` on GitHub Pages at `https://chud-lori.github.io/agent-workbench/`. Source: `README.md` header link.
4. No version number anywhere on the page. `git tag` is empty (no releases), and the repo itself disagrees with itself: `pyproject.toml:3` says `0.2.0` while `agent_workbench/mcp_server.py` `serverInfo` says `0.5.0`. Printing either would be publishing a number the repo has not settled.
5. Every tool, skill, agent type, hook, and env var on the page must be readable back out of the source. The tool list comes from `TOOLS` in `agent_workbench/mcp_server.py`, not from prose.
6. No screenshots of tool output. Brain notes, search results, and index counts are exactly the content that looks real and is easy to fabricate. If sample output is ever added, it has to be visibly labeled as a sample.
7. User-facing doc changes land in both `README.md` and `docs/index.html`. Source: owner's standing rule.

## Open

Questions the repo does not answer. Not guessed on the page.

1. **Confirm the dial.** `ENERGY 1 / RHYTHM 2 / MOTION 1` is derived from the repo's voice, not stated anywhere. Is that the intent?
2. **Version.** `pyproject.toml:3` says `0.2.0`, `agent_workbench/mcp_server.py` `serverInfo.version` says `0.5.0`, and there are no git tags. Which is real? Until that is settled the site shows no version. (Fixing those files is outside the docs-only scope of this change.)
3. **Supported platforms.** `setup.sh` is bash and uses `ln -s`, `$HOME`, and `command -v`, so it is a macOS/Linux install path, but no file states a supported-OS policy. Is Windows (WSL only? not at all?) a supported target? The page currently says only what the install script requires and does not claim an OS list.
4. **License.** `README.md` says "Currently unlicensed (all rights reserved)" and `pyproject.toml:8` says `license = { text = "Private" }`, while the site is public and invites cloning. Should the page repeat the unlicensed status? It currently does not mention licensing at all.
5. **`AGENT_WORKBENCH_STATE_DIR` default.** `agent_workbench/config.py:19` defaults to `~/Projects/agent-workbench/.state`, a fixed absolute path, not "next to the clone". A clone at another path silently uses that directory. Is that intended, or a portability bug? The docs now state the real default.
6. **Logo alt text and name.** The logo is a neural mesh over a bench. No file records what it is meant to depict, so the page uses a plain descriptive alt attribute rather than inventing a concept.
7. **Is there a real screenshot** of `brief_task` or `brain_recall` output the owner is willing to publish? One real, redacted terminal capture would be stronger than the current text-only reference, but fabricating one is not an option.
