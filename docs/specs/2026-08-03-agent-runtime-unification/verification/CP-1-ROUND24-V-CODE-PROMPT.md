# CP-1 · round 24 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R23's delta** (`714d8b7c8`). Items with an independent PASS from rounds 1–23 are not
re-graded.

R23 was the run's first split verdict, and the split located the real limit: **the census is a gate
for the 55 RED sites and not for the 13 SILENT ones, because its id is not injective.** This round
grades the two things that follow from that.

## ▶ 1 · The guards now EXECUTE — try to make them lie

The previous pair read source text and were green over the census's own removal (8 of 8 bypasses,
one control that never fired). They now watch `Path.write_bytes` **during** a real `census()` run and
parse the workflow as YAML. **Find the ninth bypass.** Consider: writing through `os.replace`,
`shutil.copyfile`, `open(...,'wb')` or a subprocess; a mirror placed *inside* the repo; a workflow
whose census step lives in a reusable action or a composite; `pytest -p no:cacheprovider`.

And grade the fix's own honesty: my first rewrite compared the tree **before and after**, which the
census's restore satisfies. **Is the write-watch now measuring the property, or the next proxy for
it?**

## ▶ 2 · The non-injective id — the decision this round should inform

68 sites → 54 digests; 4 collision groups; 2 contain an allowlisted row. B listed six ≤15-line
changes. **Grade whether an injective id is achievable without reintroducing prose-churn**, which is
the trade the previous two digests each lost in one direction. If the honest answer is *"a stable id
and a prose-blind id are incompatible, choose"* — say that, and say which the gate needs.

## ▶ Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE over an ENUMERATED space.** *Execution over a hand-picked sample is argument wearing a
  lab coat.*
* **A test satisfied by a comment is not a test** — three instances, one inside the repair for
  another.
* **Derive your own denominator.**
* Builder's record over sixteen rounds: nine pairs fixed at one end; three refuted negative claims;
  **two consecutive rounds of a claim inherited from a verifier and shipped unchecked**; a register
  that has lost rows in six consecutive rounds; and four instruments that measured something
  adjacent to what they claimed.

## Verifier A — the instrument

1. Item 1 above.
2. **W4**: your predecessor wrote and executed the 22-line test (SHIPPED 138 passed, REVERTED 1
   failed). It is still not in the tree — **8th round**. Re-state it in applicable form.
3. The recorder hazard (5th): the one-sentence V-LIVE observation.
4. The weak oracles (7th), T11d (5th), the probe writers hardcoding `"app"` (5th), the **6.71 GB** of
   unremoved mirrors.
5. **Convergence**, plus executed-vs-argued.

## Verifier B — the membrane

1. Items 1 and 2 above.
2. **`dict(r)` shallow at 4/4 doors**, and its one test asserts non-mutation by `==` — **the guard
   requires the defect**. State what the rewritten test must assert.
3. B18-8 (6th), B18-11 (6th), **B18-10 (9th)**, `surface.py:305` (5th), `_ID` (5th).
4. **The record**, and the measured hazard of two verifiers sharing one worktree — the live allowlist
   was observed rewritten by a concurrent process. Is the verification method itself now a source of
   contamination?
5. **Convergence**, plus one new falsifiable prediction.

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round24-v-code-{a,b}.md`.
