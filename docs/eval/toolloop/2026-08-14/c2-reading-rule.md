# How cycle 2's evidence will be read — committed BEFORE the file exists

Written while `c2-verify.json` was still being produced, so the reading cannot be fitted to the
result. The loop already has a rule for this in its DATA bar: *"a prediction edited once the result
is known is a description, not a falsifier."* The same standard applies to how a batch is graded.

## The bars, as gate.py enforces them

- **LIVE** — `called >= 1` of 5. A gated **confirm card counts**: the tool ran and its gate held.
  A tool never invoked has not been exercised, whatever else the turn did.
- **DATA** — every run carries the owning store BEFORE and AFTER, plus a falsifier that was not
  back-dated.
- **CODE** — falsifier RED on an original instance, full suite green, deployed image md5-verified.
  *Already satisfied for this cycle and independent of this batch.*
- **SHIP** — refusals/gates/tenancy/empty EXERCISED. *Already satisfied by direct probe, including
  the two op-dispatch tools the generic probe could not reach.*

## Cleared condition 3, verbatim

> EVERY tool in the cluster has been re-run LIVE at K>=5 and now reads `proven`, **or reads
> `blocked` on a DIFFERENT, NAMED cause** — which moves it to another problem and is recorded as
> such.

So a tool that still fails does **not** block the cycle *provided* its cause is named, measured, and
different from this cycle's invariant. A tool that fails for the SAME reason does block it.

## What I expect, and what would refute the cycle

From the interim (non-gate-grade) run, 7 of 8 surfaced 5/5 and 6 of 8 were called. Two are doubtful
and I am naming their expected causes now:

| tool | expected | if it fails, the cause I expect |
|---|---|---|
| `composition_arc_template_edit` | uncertain | `ReadTimeout` — the retry-storm scenario exceeded 300s; re-run at 600s |
| `composition_generate` | uncertain | the model never CALLS it (4/5 proposed `book_chapter_save_draft` with self-written prose), so no refusal fires and the reactive arming never gets a chance — a **sibling-substitution** cause, i.e. P5, not P3 |

**The cycle is REFUTED if** a tool still fails because a refusal named a supplier the turn could not
see. That is this cycle's invariant, and no amount of movement elsewhere would rescue it.

**The cycle is NOT cleared by** the interim numbers: that run wrote no evidence file, and a batch
whose result exists only in terminal scrollback advances nothing.
