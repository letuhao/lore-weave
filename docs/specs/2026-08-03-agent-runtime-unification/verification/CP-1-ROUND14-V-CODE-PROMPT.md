# CP-1 · round 14 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R13's delta**, which is deliberately narrower than R13's finding list. R13 measured the
loop: membrane converging, instrument scope flat, **closure ~10% per round**. So this round fixed
**the production-reachable set only** and left the adversarial-only set recorded OPEN — patching
everything in one pass is the cadence R11 convicted.

**Grade that choice as well as the code.** If the production-reachable set is not actually closed,
say so. If something in the OPEN set has become production-reachable because of these changes, that
is the most valuable thing you can find.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read.** **Verify each injection took effect** — patch every binding and print the
  check. R13's verifier lost three rows to a stale scratch tree whose counts matched baseline
  exactly; three meaningless green rows are indistinguishable from three real ones.
* **A fix without a red-able test is not a closed finding.**
* **Put a reachability verdict on every finding**: production-reachable, or adversarial-input only.
* The builder's record across five rounds: five crashes recreated inside their own fixes; four
  findings fixed at what a verifier pointed **at** rather than what it **meant**; a headline fix that
  closed a shape nobody had reported; and **three defects introduced by the fixes themselves, two of
  them production-reachable**.

---

## Verifier A — the instrument, whose finding count is FLAT

R13 measured your scope's production-reachable count at 13 → 17 → 22 → 13 with **no downward
trend**, and it is 93% of that scope's findings. **That is the number this round has to move, so
prefer depth over breadth.**

1. **The terminal-write gate** was rewritten again: a `withheld*` local must be assigned from a
   recorder call or derived from a conduit's parameter, and the conduit's call sites are scanned for
   literals. **Defeat it**, and say whether your route is an ordinary refactor or a contrivance.
2. **`[]`-not-cached now has a test.** Check the user door for the same shape, and check what happens
   on the second call after a *failed* fetch.
3. **`_as_text`, the container drain, the dead branch, `arm_turn_surface` not raising** — all four
   were guarded this round. For each: can it red, and for its stated reason?
4. **The recursive `app/` sweep.** Find route eighteen. Then ask the question the sweep cannot: is
   there a turn entry point that does not *look* like one — no `async def`, or reached only through
   a framework registration?
5. **The flag has no live consumer** (R13-A): every production read precedes every drain. Is that
   still true, and does it mean the fix is inert or merely untriggered?

## Verifier B — the membrane, which is converging

1. **Every row field is now bounded** (`rows_of`), not only `id`. Find the field or the door that
   still admits an operand. Include `validate_document`, `load`, `declarations`, `discover`,
   `SurfaceAssembler`, and the drift gate.
2. **The 5th and 6th TOCTOUs** (`dict(r)` storage-copy, `{**doc}` re-reading stamps) were recorded
   OPEN and are **not** fixed. Confirm they are still there and confirm the reachability you gave
   them. Then say whether this round's `rows_of` change makes either reachable in plain JSON.
3. **`.get("declarations", [])`** is refused. Find the remaining shape of the same class.
4. **The `r.get("id")` / `r["id"]` split** is still OPEN. Measure what it permits now.
5. **The P4 test on a `generate()`-landing mechanism** is still OPEN. Confirm, and say whether the
   builder's claim that it reds on `build()`-landing mechanisms still holds.
6. **Convergence, again, with this round added.** Same three buckets, same table. **And add one
   column: how many of the round's findings were introduced by the previous round's fixes?** That
   number, not the total, is what says whether the loop terminates.

---

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table** with your own baseline, a
  **sibling table**, a **guard table**, and a **reachability verdict on every finding**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round14-v-code-{a,b}.md`.
