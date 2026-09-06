# CP-1 · round 22 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R21's delta** (`1569ce443` + `93af52373`). Items with an independent PASS from rounds 1–21
are not re-graded.

R21 graded the census and found the mechanism sound, the gate unfinished, and **five ≤10-line fixes**
between the two. All five shipped. R21-A said it would support closing CP-1 against the census once
they landed — **that decision is the PO's and is open on the board**; this round runs under the
existing criterion.

## ▶ Grade the hardened census first

1. **Kill it.** 4 of 4 kills previously left a neutered `raise` in a tracked file. It now snapshots
   every file before the first write and restores via `atexit` + SIGINT/SIGTERM. **Kill it four ways**
   — SIGINT, SIGTERM, SIGKILL, and a crash inside the loop — and report the tree state each time.
   `atexit` does not run on SIGKILL; say what that costs and whether it is acceptable.
2. **Reorder.** Each row now carries a hash of the raise statement's own AST. Reorder two SILENT
   siblings, rename a function, reindent a raise, and change a message string. Which of those four
   *should* move a row, which should not, and which does?
3. **The CI green state.** It installs `requirements-test.txt` now. **Execute the job's steps** and
   say whether it can pass — the previous version could not, and I did not run it in its CI shape.
4. **What it still cannot say.** The allowlist has no vocabulary for *"guarded by a same-class
   sibling"* or *"dead"*. Two verifiers measured 2 and 5 mis-recorded rows by asking different
   questions. **Is that fixable, or is it the honest boundary of a red/silent census?** If a third
   column is the answer, say what it is and who writes it.
5. **Concurrency.** 15 of 20 concurrent suite runs went red during a census, destroying a verifier's
   baselines. Is that still true, and is it the census's problem to solve?

## ▶ Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE over an ENUMERATED space, not a chosen sample.** *Execution over a hand-picked sample is
  argument wearing a lab coat.*
* **A fix without a red-able test is not a closed finding.**
* **Derive your own denominator.**
* Builder's record over fourteen rounds: eight pairs half-fixed; three refuted negative claims; five
  self-measurements wrong in the flattering direction; a register that has lost rows in **four
  consecutive rounds**; and a gate whose green state was unreachable, shipped without being run in
  its CI shape.

## Verifier A — the instrument

1. The census, items 1–5 above.
2. **W4's `s.body[:1]` still has no test** — reverting it leaves 137 passed. Write the shape that
   would red it, or say why none exists.
3. **The recorder hazard is unfalsifiable at this seam**, third round. Confirm, and state exactly
   what V-LIVE would have to observe.
4. The three weak oracles, **fifth round**; T11d; probe modules in the live tree.
5. **Convergence**, raw and enumerated, plus executed-vs-argued.

## Verifier B — the membrane

1. The census, items 1–5 above — especially item 4, whose two answers were yours and A's.
2. **`generate()`'s newline is pinned and the guard reds.** Verify, and sweep the package for every
   other `write_text`/`read_text` whose bytes matter.
3. **`dict(r)` is shallow at 4/4 doors** and unfixed. Re-measure; say whether a deep copy or a frozen
   row is right.
4. **B18-8, B18-11, B18-10 (7th round), `surface.py:305`, `_ID`** — all carried, all open.
5. **The register must be generated from the verdicts.** Design that: what is the source of truth,
   what is the id, and what does the generator refuse?
6. **Convergence**, plus one new falsifiable prediction.

## What both verdicts must contain

* **The census verdict first.**
* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round22-v-code-{a,b}.md`.
