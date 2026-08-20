# /goal-prompt — emit the `/goal` condition for the knowledge-architecture refactor

Print the goal prompt for the current state of
[`docs/plans/2026-08-09-knowledge-architecture-refactor.md`](../../docs/plans/2026-08-09-knowledge-architecture-refactor.md),
ready to paste after `/goal`.

## Why this is a command and not a paragraph you retype

`/goal` takes a **4000-character** condition, and it was being retyped every session. Both
failure modes have already happened here:

- **Stale.** The 2026-08-14 run-state audit found `T39` credited with 16/24 evidence blocks it
  did not own, and a hand-written `T17 (13/20)` sitting six lines above a generated `12/20`.
  A goal prompt naming a finished row sends a whole session at the wrong task — which is
  precisely how `T17` held the RESUME pointer for ten consecutive batches.
- **Over budget.** The first hand-written version was 4819 characters and `/goal` refused it.
  That refusal was luck: the natural repair under time pressure is to cut from the bottom, and
  the bottom is the **STOP** list — the half that makes a long autonomous run safe.

So the invariant half lives in `scripts/goal-prompt.py` as a constant (one home, edited once)
and the variable half — which rows are still open, what the plan's `RESUME:` line says — is
read off the plan on every invocation. **A row that gets ticked leaves the queue by itself.**

## Run

```bash
python scripts/goal-prompt.py
```

Then give the user the output in a single fenced block, on its own, with no commentary inside
it — they are going to select and paste it. Say in one line above the block that it is ready
to paste after `/goal`, and mention the character count against the 4000 budget.

**Do not edit the output before showing it.** If it needs different content, the change belongs
in `scripts/goal-prompt.py` (the rules, the queue) or in the plan's `RESUME:` line (what comes
next) — those are the two homes, and hand-editing the emitted text is how the drift above got
started.

## When it refuses

Over budget is a hard error naming the RESUME line's length, never a truncation. A prompt
silently cut to fit is one whose last section is missing. Fix it by shortening the plan's
`RESUME:` line — a RESUME that will not fit in a goal prompt is too long to be read anyway —
and regenerate.

## Arguments

None. The prompt is derived entirely from the plan's current checkboxes and `RESUME:` line;
there is nothing to parameterise, and a flag that changed the rules would defeat the point of
having one home for them.
