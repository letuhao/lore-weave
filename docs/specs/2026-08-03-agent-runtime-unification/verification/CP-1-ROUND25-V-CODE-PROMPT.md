# CP-1 · round 25 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: the R25 delta only.** Items with an independent PASS from rounds 1–24 are not re-graded.
Three items were **moved to CP-2** by the PO before this delta was written (the catalogue-outage
ordering residual, `rows_of`'s document-level stamp check, B18-10's fifth exported door) — they are
**out of scope here**, and challenging the transfer is item 5 below, not a finding.

## 🔴 The isolation rule, and it is not advisory

R23 measured a real hazard: **two verifiers sharing one worktree** — the live allowlist was observed
being rewritten to `deadbeef` and back by a concurrent process. R24 measured a second: **the builder
broke FREEZE**, landing a commit while B was measuring, and B established that a 20-minute-earlier
landing would have produced a **false PASS on the round's biggest finding, undetectably**.

So: **each verifier runs in its own `git worktree`, on the frozen commit, and nothing else runs
there.** If you observe a file changing under you, that is a finding about the method, and it
outranks whatever you were measuring.

## ▶ What this delta claims, so you know what to attack

Nine items carried for 5–8 rounds each were closed, and the builder's claim is that **every one has a
guard proven RED-able by reverting exactly the fix, in a throwaway mirror, never with
`git checkout`**. Measured by the builder: **7/7** (membrane), **5/5** (instrument, including a 2×2),
**11/11** (census guards). ⚠️ **Builder's evidence, and the census being green is the builder
measuring the builder's own instrument.**

| # | item | rounds | what was done |
|---|---|---|---|
| 1 | `dict(r)` shallow at both copy doors | 5 | `members` copied; the guard now asserts list IDENTITY and writes through it — the old one asserted `id` by `==`, which a shallow copy protects, so **it passed in both states** |
| 2 | `_ID` had no length bound | 6 | `ID_MAX_LEN = 64`; driven at the id AND the member spelling, three doors |
| 3 | `surface.py` `OrderBy` key-pair shape | 5 | code was already correct; the **census recorded the refusal as SILENT**, and the guard's vehicle must be a 2-element **list** — a 3-tuple/1-tuple/2-char `str` all raise from Python's own unpacking and prove nothing |
| 4 | B18-8 `str`-subclass key / member | 7 | both were already refused; **2 of 3 pins were census-SILENT**. Guards added |
| 5 | B18-11 dead `canon` imports + refuted docstring | 7 | 2 imports removed, docstring corrected to what execution showed, `_norm` now uses `nfc` so the claim "one place decides the composed form" is true inside its own module. **The property gate found a THIRD dead import (`manifest: import re`) that eight rounds of review had not named** |
| 6 | W4's `s.body[:1]` untested | 8 | test + a control for the first-statement case |
| 7 | three weak oracles | 8 | bound to the offender **sentence**; the first repair (module path alone) was **still not an oracle** — measured green under a gate broken for an unrelated reason |
| 8 | T11d — the live SQL spelling | 6 | column-name aliases resolved to a fixed point; 4 vehicles |
| 9 | 6 probe writers hardcoding `"app"` | 6 | `_swept_root()` + a property gate |
| C1 | census guard caught 1 of 8 write cells | — | both writers × four write APIs, enumerated as controls |
| C2 | CI half green under 15 of 16 disable shapes | — | **17** shapes enumerated, each a control |

## ▶ Verifier A — the instruments

1. **The 8-cell guard.** It intercepts writes and returns a fake handle rather than touching disk.
   **Find the ninth cell.** Consider `os.replace`, `os.rename`, `shutil.copyfile`/`copytree`,
   `os.remove`, `Path.unlink`, `Path.rename`, `subprocess`, `mmap`, `os.open`+`os.write`, a mirror
   placed *inside* the repo, a write through a C extension. Is `{2 writers} × {4 APIs}` even the
   right space, or is it the space the previous verdict happened to name?
2. **The 17 CI shapes.** Enumerate your own; report how many the check survives. A composite action,
   a reusable workflow, a `defaults.run.shell` that swallows `rc`, branch protection not requiring
   the job, `paths:` filters, a self-hosted runner label that never matches.
3. **W4, the weak oracles, T11d, the probe writers** — for each, is the guard binding the property or
   the nearest proxy? The T11d fix resolves aliases across ALL modules with no import graph: **what
   does that over-approximation cost, and can it be made to red on correct code?**
4. **Convergence**, and executed-vs-argued with your own denominator.

## ▶ Verifier B — the membrane

1. **Items 1–5 above.** For each: does the guard red for the reason it names, or for a bystander?
   The builder's reversions are in the verdict — **re-derive them, do not inherit them.**
2. **The `ID_MAX_LEN = 64` bound is a number a person chose.** Is 64 defensible, is the bound
   enforced everywhere an id is a key, and does anything in the tree already exceed it?
3. **The dead-import gate** treats a name appearing in any string literal as "used". That is
   deliberately loose. Enumerate what it therefore misses.
4. **The `members` copy is one level deep** because `check_row` bounds members to `str`. Verify that
   claim rather than accepting it, at every door.
5. **Convergence**, plus one new falsifiable prediction.

## ▶ Item 5 for BOTH — the transfer, which is the PO's and is challengeable

Three items moved to CP-2 on the criterion *"an item whose measurement has no SUBJECT until a later
checkpoint's code exists MOVES."* **Was the criterion applied honestly, or used to clear a board?**
The load-bearing fact is that `agentruntime` has **zero importers outside the package**. Check it.
If any of the three is measurable today, say so and say how.

## ▶ Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE over an ENUMERATED space.** *Execution over a hand-picked sample is argument wearing a
  lab coat.*
* **A test satisfied by a comment is not a test** — three instances, one inside the repair for another.
* **Derive your own denominator.** Every ratio the builder has published in this run has been a lower
  bound.
* Builder's record over seventeen rounds: **ten pairs fixed at one end**; three refuted negative
  claims; two rounds of a verifier's claim inherited and shipped unchecked; a register that lost rows
  in six consecutive rounds; four instruments that measured something adjacent to what they claimed;
  **one broken FREEZE**; and one `atexit` that was deleting the system temp directory while the
  builder blamed the environment.

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish, **and the path of the worktree you ran in.**

Write to `verification/CP-1-round25-v-code-{a,b}.md`.
