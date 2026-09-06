# CP-1 · round 12 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R11's delta only.** Items with an independent PASS from rounds 1–11 are not re-graded.

R11's finding was not a defect. It was that **9 of 9 of the previous round's guards were silent
under injection, and 3 of the round's own guards fired for the wrong reason** — fixes were outrunning
evidence. So this round grades the delta on two axes, and the second is new:

1. Is the fix correct?
2. **Does each fix have a test that reds — and reds for the reason it names?**

A fix without a red-able test is **not** a closed finding this round, however correct the code is.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read.** Every round from 5 to 11 shipped a defect that source-reading blessed.
* **Measure the baseline yourself**, and **verify your own injection took effect** before concluding
  anything from a green run. In R11 the builder's probe patched `manifest.build` while the test
  imports `build` from the package, so the injection was inert and the test looked fine. A negative
  measurement must be shown capable of measuring something.
* The builder's record: a crash **recreated inside the function written to fix it, four times**; a
  verifier's finding fixed at what it pointed **at** rather than what it **meant**, three times;
  **U-2's founding confusion re-created inside a fix for something else**; and a guard that reddened
  on correct code while blind where it mattered.

---

## Verifier A — ordering, arrival, and the guards

1. **Ordering is no longer load-bearing**: `record_surface_withheld` / `record_catalogue_unavailable`
   now **open a sink if none exists** (`_sink_for_record`), so a narrowing before any arming is
   still recorded. **Attack the new property, not the old one.**
   * Can a record now land in the **wrong turn's** sink — a background task, a subagent, an
     `asyncio.create_task` that inherits a context, a thread?
   * `arm_turn_surface` still *replaces*. Find an ordering where the replacement discards rows that
     a caller needed — i.e. where auto-arming happens **before** the real arming on a live path.
   * Does anything now drain a sink that was never a turn's?
2. **`absorb` is claimed total over row shapes.** Feed it shapes the parametrised test does not:
   deeply nested, recursive, `__str__` raising, a `dict` subclass, keys that are not strings, a
   generator as the sink itself.
3. **The terminal-write gate** now matches SQL naming the column. Defeat it: build the SQL from a
   constant, an f-string fragment, a helper, or a different table alias. Does it still see all
   writers? Does it red on anything correct?
4. **The stale-exemption gate and the whole-tree sweep.** Find route sixteen, and check whether any
   `_NOT_A_TURN` entry is now wrong rather than merely visible.
5. **The empty-vs-outage revert.** Confirm a *successful* empty catalogue registers nothing on
   **every** door, and that the cache fix it was tangled with is still in place: `[]` not cached, a
   recovered gateway re-dialled.

## Verifier B — the membrane's bounds and the manifest

1. **Three TOCTOUs were closed in `manifest.py`.** Find the fourth. Look for any value read twice
   between a check and a use, in `manifest.py`, `surface.py`, `contract.py`, `admission.py` and
   `canon.py` — including through `ambient`.
2. **`rows_of` validates row shape.** Find the row field that still reaches a decision unbounded,
   and the door that does not go through `rows_of`.
3. **The P4 defect-assertion test now performs a partial re-admission.** Build §6.4's grandfathering
   yourself — **at every binding, and verify your injection took effect** — and confirm the test
   reds. Then try to make it red for the wrong reason, and green with the mechanism present.
4. **Every fix in `app/agentruntime/` this round: is it guarded?** Inject each one and report
   green/red in a table. This is the round's second axis and it is not optional.
5. **`generate`'s `exists`→`load` re-check.** Is the added check reachable, and does it fire for the
   reason it names, or is it a line that cannot execute?
6. **The membrane gate script.** It has not been re-graded since round 8. Does its selftest still
   cover what it claims, and is `SINGLE_SITED` still true?

---

## What both verdicts must contain

* The falsifier per claim, stated before the search.
* A **bypass table**, a **red-ability table** with your own baseline, and a **sibling table**.
* **A guard table** — for every fix in the delta: *is there a test? can it red? does it red for the
  reason it names?* A "no" in column one is a finding on its own.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round12-v-code-{a,b}.md`.
