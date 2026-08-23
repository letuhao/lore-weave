# /goal-prompt — build the `/goal` condition that anchors a long run

Emit a `/goal` condition for the work named in `$ARGUMENTS`, ready to paste.

A `/goal` condition is not a task description. It is the thing an agent re-reads when it has
drifted, so it has to answer *what counts as done*, *how to work*, and *what must never happen* —
not just *what to work on*. This command exists to make that structure automatic and to keep the
open-item list from going stale.

## Arguments

`$ARGUMENTS` names the work: a plan path, a runbook, a loop name, or a sentence describing the
goal. If it also carries methodology ("investigate logs first", "prove with a real run"), that
belongs in **METHOD** and **EVIDENCE** below — carry it in, do not paraphrase it away.

If `$ARGUMENTS` is empty, ask what the goal is about. Do not guess from recent work: a goal
prompt aimed at the wrong target sends a whole session at the wrong task.

## The two failure modes this prevents

Both have happened in this repo, and both are general.

- **Stale.** A run-state audit found `T39` credited with 16 of 24 evidence blocks it did not own,
  and a hand-written `T17 (13/20)` six lines above a generated `12/20`. A goal naming finished
  work holds the resume pointer at it — `T17` held it for ten consecutive batches.
- **Over budget.** `/goal` caps the condition at **4000 characters** and refused a 4819-character
  draft. That refusal was luck. The natural repair under time pressure is to cut from the bottom,
  and whatever sits at the bottom is what silently stops being true.

The remedy is the same for both: **one home for the durable half, and derive the changing half
from whatever already knows it.** An item that gets finished then leaves the queue by itself.

## The sections a condition needs

Emit these in this order. The order is load-bearing — see *Budget* below.

| Section | Answers | Fails when |
|---|---|---|
| **OBJECTIVE** | What "done" means, in terms something can check | It is a topic, not a finish line |
| **UNIT** | What ONE cycle covers | Missing → the run sprawls across everything at once |
| **METHOD** | How to work a cycle | Missing → the agent invents a method per cycle and drifts |
| **EVIDENCE** | What proves a cycle done | It accepts assertion instead of a measurement |
| **STOP** | What ends the run, and what must never happen | Missing → an autonomous run has no brakes |
| **QUEUE** | The open items, derived not typed | It was typed, so it is already stale |
| **NEXT** | The single resume pointer | Ambiguous → each session picks a different item |

**STOP sits above QUEUE deliberately.** QUEUE is the elastic section — it grows and shrinks with
the work — so it must be last, where the budget bites. A condition that loses its tail loses
open items, which is recoverable. One that loses STOP loses its brakes, which is not.

Two things worth stating explicitly in **EVIDENCE**, because agents under time pressure drop them
first: that a fix is proven by a *real run*, not by the code looking right; and that a failed
attempt is *recorded*, not retried silently until it passes.

## Deriving the queue

If the work has machine-readable state — a plan's checkboxes, a ledger, a gate script, a test
run, an issue query — the queue **must** be read from it at emit time, and the command should
have a generator that does so. One generator per goal, living beside the goal's own artifacts;
"one home" means one per goal, not one for the repo.

If no generator exists yet for this target, write it as part of running this command. That is the
same rule as *do not hand-edit the output* — the fix belongs in the generator, not in the text.

If the work genuinely has no machine-readable state, say so in one line above the block, and
treat every item in QUEUE as a claim that needs re-checking next session.

## Emitting

Run the target's generator with its check first (budget, and that no open item is missing from
the queue), then emit.

Give the output in a **single fenced block, on its own, with no commentary inside it** — it gets
selected and pasted whole. The block already begins with `/goal `, so it is one paste, not a
paste plus a typed command. Above the block, in one line: the character count against 4000, and
any warning the check produced.

**Do not edit the output before showing it.** If it needs different content, change the generator
or the source the queue is read from. Hand-editing the emitted text is how the drift above
started.

## When it refuses

Over budget is a hard error naming what overflowed — never a silent truncation. Fix it by
shortening the *source* (a resume pointer too long for a goal prompt is too long to be read at
all), or by trimming QUEUE to the open items and linking the rest. Never fix it by cutting
upward from the bottom.
