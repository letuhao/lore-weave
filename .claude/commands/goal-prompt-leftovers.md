# /goal-prompt-leftovers — emit the `/goal` condition for the run-state leftovers

Print the goal prompt for the current state of
[`docs/plans/2026-08-30-runstate-leftovers.md`](../../docs/plans/2026-08-30-runstate-leftovers.md),
ready to paste.

Sibling of [`/goal-prompt`](goal-prompt.md), which does the same for the archived
knowledge-architecture refactor. Same reasons, same shape; see that file for the two failure
modes (a prompt naming a finished row held a session on the wrong task for ten batches, and a
hand-written one overflowed the budget) that make this a command rather than a paragraph
anyone retypes.

## Run

```bash
python scripts/goal-prompt-leftovers.py --check && python scripts/goal-prompt-leftovers.py
```

`--check` first. It verifies the 4000-character budget, that every open row reaches the
emitted text, and that the plan's `RESUME:` line names a row that exists. Then print.

Give the user the output in a single fenced block, on its own, with no commentary inside it —
they select and paste it whole. **The output already begins with `/goal `**, so it is one
paste and not a paste plus a typed command. Say in one line above the block what the
character count is against the 4000 budget, and repeat any `WARN` line `--check` produced.

**Do not edit the output before showing it.** If it needs different content, the change
belongs in the plan (rows, `RESUME:`) or in `scripts/goal-prompt-leftovers.py` (the local
`STOP_BLOCK`, `DISCIPLINE`, `SCOPE`). Hand-editing the emitted text is how the drift the
sibling command documents got started.

## There is no stored copy, on purpose

The prompt is DERIVED on every run from two homes:

- the plan — the queue (open checkboxes) and the `RESUME:` line;
- `scripts/goal-prompt.py` — `RULES` and `CYCLE`, imported rather than copied, because those
  thirteen rules did not stop being true when the plan they were written for was archived.

A ticked row therefore leaves the prompt with nobody editing anything. Saving the emitted text
to a file would create exactly the second home this design exists to prevent, and it would go
stale on the first `[x]`.

**`DISCIPLINE` is deliberately NOT imported.** Its last line tells a session to keep the four
plan gates green — and all four resolve their subject through `plan_location.py`, which knows
only the ARCHIVED refactor. They stay green whatever happens on this plan. The local block
says so out loud instead: nothing audits this document, the row's own bite is the whole
verification.

## When it refuses

Over budget is a hard error naming the overage, never a truncation — a prompt silently cut to
fit is one whose last section is missing, and the last section is **STOP**. Fix it by
shortening a row title or the `RESUME:` line in the plan, then regenerate.

A `WARN` about headroom is not a failure. It is the number that predicts the next outage:
report it and carry on.

## Arguments

None. Everything is derived from the plan's current checkboxes and `RESUME:` line.
