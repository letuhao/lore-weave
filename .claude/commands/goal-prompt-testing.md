# /goal-prompt-testing — emit the `/goal` condition for v0.1.0's testing phase

Print the goal prompt for the testing-technique-focused slice of
[`docs/plans/2026-09-06-v0.1.0-go-live.md`](../../docs/plans/2026-09-06-v0.1.0-go-live.md) —
`/human-sim` blind-spot discovery, a live computer-vision GUI review, and the fix-and-reverify
loop those two find work for. Ready to paste.

Sibling of [`/goal-prompt`](goal-prompt.md), which does the same generically for any plan. This
one is scoped rather than generic: the go-live plan has 17 open rows across 6 phases (changelog
draft, scratch-infra testing, checklist, merge, tag), and pooling all of them into one goal would
dilute the testing discipline this command exists to state. The plan's own
` ```goal-prompt ` block (a `## Goal (testing-technique focus — Phase 2–4 only)` section) declares
`excluded: [T0.1..T0.6, T1, T2, T13..T17]`, so the emitted queue is exactly T3→T12 — scratch infra,
regression, `/human-sim`, the computer-vision pass, and the bug-fix loop those two feed.

## Run

```bash
python scripts/goal-prompt.py --plan docs/plans/2026-09-06-v0.1.0-go-live.md --check && python scripts/goal-prompt.py --plan docs/plans/2026-09-06-v0.1.0-go-live.md
```

`--check` first: budget, headroom, whether every open row in the testing lane reaches the
emitted text, and whether any row is unreachable. Then print.

Give the user the output in a single fenced block, on its own, with no commentary inside it —
they select and paste it whole. **The output already begins with `/goal `**, so it is one paste
and not a paste plus a typed command. Say in one line above the block what the character count
is against the 4000 budget, and repeat any `WARN` line `--check` produced.

## Why a scoped sibling instead of plain `/goal-prompt`

`/goal-prompt` reads whatever the plan's board says, unmodified — correct for "finish this
plan," wrong for "run just the testing loop inside this plan." Two things this scoped goal
states that the plan's generic rules don't:

- **A blind spot is not a finding until it's fixed.** `/human-sim` and a screenshot review both
  produce candidates, not verdicts — the goal's own `RULES` (rule 2) make "found" and "done"
  different states on purpose, because a testing pass that stops at "logged" is the exact outcome
  this command exists to prevent.
- **Computer vision here means the acting agent's own eyes, not a separate paid call.** Reading a
  screenshot with the `Read` tool is a normal, already-included capability of this session's
  model — rule 4 requires looking at the real rendered image rather than trusting a passing testid,
  and the `stop:` block explicitly treats "this needs a paid/cloud vision model" as a STOP, not
  a default, matching this repo's $0-local-first discipline everywhere else.

## When it refuses

Same failure modes as `/goal-prompt` (see that file): over budget names the overage rather than
truncating (the lost section would be STOP); an open testing row with no lane/exclusion entry is
reported as unreachable rather than silently dropped.

## Do not edit the emitted text

If the goal needs different content, the change belongs in the plan's `goal-prompt` block (the
`## Goal (testing-technique focus)` section) — not in this file, and not by hand-editing what
gets printed. This command is a fixed pointer at one plan's one declared block, same shape as
`/goal-prompt-leftovers`.

## Arguments

None. Everything is derived from the plan's current checkboxes, its `goal-prompt` block, and its
`RESUME:` line.
