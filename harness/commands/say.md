---
description: Answer, then speak the answer aloud with the macOS `say` command
argument-hint: [prompt]
allowed-tools: Write, Bash(say:*)
---

Answer this: $ARGUMENTS

Then speak it, once, at the end of your reply:

1. Write the spoken version to `spoken.txt` in your scratchpad directory. Plain sentences, no markdown, no code, no URLs, under 400 characters. Not a transcript of your reply — the point you would say out loud, because a stripped-down reply read aloud is mostly punctuation names and path fragments.
2. Run `say -r 210 -f` against that file's absolute path, with a trailing `&` so a twenty-second utterance does not hold the turn open.

`say` is macOS-only and ships with the OS. If it is missing, say so in one line and skip step 2 rather than failing the turn.

Speaking is the last thing you do. If the answer needs tool calls, make them first — speech that starts before the work is finished describes an answer you do not have yet.
