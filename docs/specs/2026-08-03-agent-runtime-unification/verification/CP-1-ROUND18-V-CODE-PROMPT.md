# CP-1 · round 18 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R17's delta** (`8a84f78e1` + `9453c9f86`). Items with an independent PASS from rounds 1–17
are not re-graded.

R17's finding was that I claimed something was **impossible** and the counter-example was one
statement I had deleted myself, resting on an argument of mine that had gone vacuous. That is the
fourth consecutive round in which a builder claim about a *measurement* or a *design space* was
wrong in the flattering direction. So this round is asked to attack claims before code.

**Two claims in this delta are load-bearing and both are mine:**

1. *"The restored writer plus the derivation satisfies every ordering except one, and that one rides
   the sink so no arrangement of this variable addresses it."* **Try to refute it**, the same way
   R17-A refuted its predecessor. Construct a seventh ordering. If the residual is addressable here,
   saying so is worth more than any other finding.
2. *"Two of the four unguarded holes did not reproduce."* I recorded them **UNREPRODUCED, not
   fixed** — C-12's structured fields surviving `check_row`'s re-raise, and a tool with resolving
   members. **Re-measure both with your own probe.** If they reproduce, my probe was wrong and the
   holes are open; say which.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read. Verify each injection took effect.** Patch every binding; a test module
  importing a name from the package will not see a patch applied only to the defining module.
* **A fix without a red-able test is not a closed finding.**
* **Put a reachability verdict on every finding.**
* **Derive your own denominators.** Every builder ratio in this run has been smaller than the truth.
* Builder's record over nine rounds: five crashes recreated inside their own fixes; six findings
  fixed at what a verifier pointed *at* rather than what it *meant*; guards loosened, deleted and
  made vacuous while comments denied it; a guard that passed on the artifact it replaced; **four
  self-measurements wrong in the flattering direction**, the last being a negative existence claim
  from a single failed attempt.

---

## Verifier A — the instrument

1. **The writer is restored and six orderings are asserted.** Verify each against this tree. Then
   claim 1 above: **find a seventh ordering that breaks it.**
2. **T9 is closed by resolving SQL through module and cross-module constants, and the parse is
   fail-closed.** Find T10. Consider: SQL built by string concatenation or `%`/`.format`; a constant
   re-exported through `__init__`; an executor reached through `getattr`; a write in a file the
   sweep excludes.
3. **Route 24 is closed by refusing a delegate whose own arguments narrow.** Find route 25 — and say
   whether the fix removed a class or moved the boundary again, which is what the last three did.
4. **The `Try` rule** now refuses to treat a `try` body's arm as covering a narrowing in that try's
   handlers. Grade it: is the rule right, and does it still red W4 while accepting the shape route
   18 was about?
5. **`db/migrate.py` reddened the widened gate and the answer was to qualify the SQL match to
   writes.** Is that qualification now too narrow — is there a real write it no longer sees?
6. **Convergence**, raw and per changed line. A recommended steering by raw count with regressions
   flagged separately. Do you agree, and what would you steer by?

## Verifier B — the membrane

1. **`ROW_REQUIRED ⊆ emitted ⊆ ROW_FIELDS`** replaced the equality. Verify each half fires, and
   check the optional tier end to end: add an optional-and-emitted field and confirm an existing
   manifest still loads and re-generates with origins intact.
2. **The eleventh guard exists now** and re-executes the module source. Verify it reds for the
   reason it names and does not red for an unrelated edit to that file.
3. **Claim 2 above** — re-measure the two unreproduced holes yourself.
4. **`rows_of` still runs no document-level stamp check**, recorded OPEN with owner CP-2 for two
   rounds. Re-test the scoping: is it reachable today by any exported path?
5. **Find the fifth unguarded load-bearing check** in the package, with your own denominator.
6. **Convergence**, and the prediction question. Your predecessor's advance prediction held. Make
   one of your own that this run can settle next round, and state what would falsify it.

---

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table with a denominator you derived**,
  a **sibling table**, a **guard table**, and a **reachability verdict on every finding**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round18-v-code-{a,b}.md`.
