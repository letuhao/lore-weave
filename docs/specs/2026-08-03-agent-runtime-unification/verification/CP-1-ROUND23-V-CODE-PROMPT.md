# CP-1 · round 23 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R22's delta** (`bc1452f4c`). Items with an independent PASS from rounds 1–22 are not
re-graded.

R22-A stated the distance to supporting closure as **four ≤10-line changes**. All four shipped. **That
is the builder's own evidence and settles nothing** — this round decides whether they are real.

## ▶ Grade the mirrored census first

1. **It no longer writes into the live tree.** Verify by execution: kill it every way you can find,
   on your platform, and report the live tree's state each time. Then find what the mirror does
   **not** reproduce — untracked files, submodules, symlinks, file modes, a dirty index.
2. **The digest is `ast.unparse` with string literals blanked.** Re-run the 68×4 edit-class
   enumeration: reorder, reindent, rename, reword. Which now move a row, and which *should*? A
   digest blind to prose is also blind to a **message that changes what the refusal means** — say
   whether that matters.
3. **Version stability**, the defect that made the previous gate print a plausible lie: check the ids
   across at least two interpreters.
4. **The CI test now asserts the census RUNS.** Try to make it green while the census does not run.
   The previous version fell to `echo skip`, to `--write`, and to a **comment**.
5. **The allowlist header** now claims only what one-at-a-time neutering can support. Is it now true
   of all 13 rows?

## ▶ The two designs R22-B produced, and whether to build them

`effect ∈ {accepts, refuses-differently, no-observable-change}` and
`static ∈ {reachable, unreachable-handler}`. **Grade the design, not the intention**: is `effect`
computable from what pytest already reports, and is `static` decidable here? If either is not, say so
now rather than after it ships — the last three instruments in this run were shipped and then found
to be measuring something adjacent to what they claimed.

## ▶ Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE over an ENUMERATED space.** *Execution over a hand-picked sample is argument wearing a
  lab coat.*
* **A fix without a red-able test is not a closed finding**, and a test satisfied by a **comment** is
  not a test — measured twice this round, once inside the repair for the other.
* **Derive your own denominator.**
* Builder's record over fifteen rounds: nine pairs fixed at one end; three refuted negative claims;
  five self-measurements wrong in the flattering direction; **a claim inherited from a verifier and
  propagated to four places unchecked**; a register that has lost rows in five consecutive rounds,
  the last by omission; and two instruments that broke the thing they were built to protect.

## Verifier A — the instrument

1. The census, items 1–5.
2. **W4**: you wrote and executed the 9-line shape that reds `s.body[:1]`. It is not in the tree.
   Re-state it so it can be applied, and say what it costs.
3. **The recorder hazard**, 4th round: state the V-LIVE observation in one sentence a CP-2 harness
   could implement.
4. The three weak oracles (**6th**), T11d (4th), the probe writers hardcoding `"app"` (4th).
5. **Convergence**, plus executed-vs-argued.

## Verifier B — the membrane

1. The census, items 1–5 — especially 2 and 5, which were your findings.
2. **`dict(r)` shallow at 4/4 doors**, and its one test **asserts non-mutation by `==`, so the guard
   requires the defect.** You measured the 2-line fix; verify it still holds and name what the
   rewritten test must assert.
3. **B18-8 (5th), B18-11 (5th), B18-10 (8th), `surface.py:305` (4th), `_ID` (4th)** — re-measure.
4. **The record.** R21's block had no `Open, carried` line at all; R22's has one. Audit it against
   both R22 verdicts.
5. **Convergence**, plus one new falsifiable prediction.

## What both verdicts must contain

* **The census verdict first.**
* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round23-v-code-{a,b}.md`.
