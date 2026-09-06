# CP-1 · round 17 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R16's delta** (`869c5be52`). Items with an independent PASS from rounds 1–16 are not
re-graded.

R16's real finding was not a bug. **Both verifiers independently refuted both of the builder's
self-measurements** — a red-ability ratio whose denominator was the guards just written (22/30 and
9/16 when counted against the guards that exist), and a read-twice sweep that returned 0 only under
the definition the builder had chosen (6 under *two reads of one fact*). This round's delta is
written to answer that, so **grade the measurements before the code**:

* The builder now claims **10 of 11**, with the denominator taken from *your predecessors' verdicts*
  rather than from what was built, and declares the eleventh **unguarded with a reason** instead of
  counting it. **Re-derive the denominator yourself.** If the right denominator is larger, that is
  the finding.
* The builder's read-twice sweep now reports **two numbers** (6 same-fact sites, 0 mixed-mechanism)
  and its own control. Re-run it. A sweep that reports what its author expected is the failure this
  design has a standard about — and this one has been wrong twice.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read. Verify each injection took effect** — patch every binding, print the
  check, and build a fresh scratch tree that is not nested in a stale one.
* **A fix without a red-able test is not a closed finding.**
* **Put a reachability verdict on every finding**: production-reachable, or adversarial-input only.
* Builder's record over eight rounds: five crashes recreated inside their own fixes; **six** findings
  fixed at what a verifier pointed *at* rather than what it *meant*; a guard loosened twice while the
  comment beside it denied it; a guard **deleted** during a consolidation; a test made vacuous by an
  improvement; a guard that **passed on the artifact it replaced**; and **two self-measurements that
  were wrong in the flattering direction**.

---

## Verifier A — the instrument

1. **The outage fact was REVERTED** to the derived boolean, and the surviving hole is now asserted
   as a *defect* rather than dressed up: `arm → record → drain → read` is asserted `False`. Grade
   that decision. Is the reverted state genuinely no worse than both alternatives — re-run the
   head-to-head yourself rather than trusting the builder's account — and **is the new guard red on
   `530ce3eff`'s `instrument.py`**, the artifact it replaced? The previous one was not, and that is
   why it existed.
2. **The claim that no arrangement inside `instrument.py` can satisfy every ordering.** That is a
   negative claim about a design space, made by the party who wants to stop working on it. **Try to
   refute it.** If an arrangement exists that is correct in all six orderings without a turn
   identity, saying so is the most valuable thing this round can produce.
3. **T8 is closed by discovering the file set with `rglob`.** Find T9. Consider: a writer that is not
   a function (module scope, a lambda, a comprehension); a module the sweep cannot parse; a writer
   reached through a class; SQL built by a helper in a third module.
4. **Route 23 is closed and both relations now share one definition of "unconditional"** (`Expr`,
   `Assign`, `AnnAssign`, `AugAssign`, `Return`, descending into `With`/`AsyncWith`/`Try` bodies at
   depth 1). **Find route 24** — and say specifically whether the shared definition removed a class
   of hole or merely moved where the next one appears.
5. **The `try:` body now counts as unconditional.** Is that right? An arm in a `try` whose body
   raises before reaching it is a turn that narrows into nothing, and the builder's stated
   justification is that the property is *syntactic*. Grade the justification, not the line.
6. **Convergence, your scope**, per changed line as well as raw. R16 measured 0.68/100 — the lowest
   of four rounds — on a delta that also introduced 5. Which number should this run steer by?

## Verifier B — the membrane

1. **`ROW_REQUIRED` is a literal again, gated against the writer's real output.** Verify the gate
   fires when a field is added to `_row` without a decision. Then grade the **migration** claim
   directly: with an optional tier, can CP-2 actually add `relevance` to a non-empty manifest on
   disk without erasing origin stamps? **Execute it** — write a manifest, add the field, and try.
2. **`build` now preserves C-12's structured fields.** Sweep for the same shape elsewhere: any
   `except` naming a class that has since gained a subclass. `UntrustedRow` gained two.
3. **`canon.nfc()` was deleted as a normalisation whose stated harm was not real.** Confirm or
   refute — and check the deletion did not remove a door §0.14.2 actually needs.
4. **Four previously-unguarded checks got tests** (duplicate ids, `previous.declarations` a list, the
   document's closed schema, `dict(r)`). Verify each reds for the reason it names, and find the
   fifth.
5. **`rows_of` still runs no document-level stamp check** — recorded OPEN, owner CP-2. Is that
   scoping honest, or is it reachable today?
6. **Convergence**, same buckets, per changed line. R15 and R16 were the first two *structural*
   deltas and R16-B predicted the introduction rate would rise again on the next site-by-site one.
   **This delta is site-by-site.** Report whether the prediction held — that is a falsifiable claim
   made in advance, and settling it is worth more than another finding.

---

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table with a denominator you derived
  yourself**, a **sibling table**, a **guard table**, and a **reachability verdict on every finding**.
* An independent re-run of the builder's two measurement claims.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round17-v-code-{a,b}.md`.
