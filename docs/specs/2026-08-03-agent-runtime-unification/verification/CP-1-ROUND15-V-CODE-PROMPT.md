# CP-1 · round 15 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R14's delta.** Items with an independent PASS from rounds 1–14 are not re-graded.

R14's central answer changed shape: instead of bounding another value, the membrane now has **one
definition of a valid row** (`contract.check_row_shape`), and **a row carrying a field the contract
does not define is refused** — because both previous rounds' vehicles were *well-typed plain
scalars* that no value bound can catch.

**The claim that most needs grading is the one written beside that fix, not the fix:**

> A hand-typed but well-typed `cost` is the **hand-edited-manifest** threat, whose only answer is the
> document digest recorded in §6.4.2 and **deliberately not taken**. Pretending a value bound closes
> it would be worse than leaving it open, because it would look closed.

**Is that true, or is it a rationalisation?** If a cheaper mechanism exists that does not weaken
§6.1 layer 3, saying so is the most valuable thing this round can produce.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read. Verify each injection took effect** — patch every binding, print the check,
  and build a fresh scratch tree that is not nested in a stale one.
* **A fix without a red-able test is not a closed finding.**
* **Put a reachability verdict on every finding**: production-reachable, or adversarial-input only.
* Builder's record over six rounds: five crashes recreated inside their own fixes; four findings
  fixed at what a verifier pointed **at** rather than what it **meant**; **a guard loosened while the
  comment beside it claimed it had not been**; and three defects introduced by the fixes themselves.

---

## Verifier A — the instrument

1. **The terminal-write gate** now also matches `ast.AnnAssign`. **`stream_service.py:7424`, the
   clean finish, was still bindable to `None` with the gate green** because `_emit_chat_turn` has no
   `withheld*` local — R10's I13, six rounds open. Confirm, and say what shape of check would catch
   it without a false positive.
2. **Route 20 was created by the previous fix** — `arming` granted an exemption on a bare name across
   115 files. It now follows **import edges**. Verify that, and find route twenty-one.
3. **Route 19** (`async def` only) is closed. Check the sibling assumption: is there a turn entry
   point that is neither a `def` nor an `async def` at module scope?
4. **`_NOT_A_TURN` grew two entries** (`tool_surface`'s budgeting helpers). Is each genuinely not a
   turn, and is the "a function that IS a narrowing primitive is not an entry point" rule sound, or
   does it exempt something that narrows *and* begins a turn?
5. **The flag is INERT** (every production read precedes every drain), two rounds running. Say
   plainly whether the fix should be kept, simplified, or removed — and what evidence decides it.
6. **The container `try`**: `rows_in = list(sink); del sink[:]` share one `try`, so a tuple or
   generator sink now loses every row where the previous code recorded them. Confirm.

## Verifier B — the membrane

1. **`check_row_shape` is one definition for both doors.** Find the third door, or the caller that
   reaches a consumer without passing it. Include `declarations`, `discover`, `SurfaceAssembler`,
   `load`, the drift gate, and anything in `__all__`.
2. **Undefined fields are refused; the ranking fields are named and bounded.** Grade the boxed claim
   above. Then: does refusing an undefined field break any legitimate forward path — a CP-4 row, a
   CP-2 `relevance`, a future field — in a way that will be discovered late?
3. **`members` is required.** Find what still treats an absent or empty `members` as "no members".
4. **The 5th/6th TOCTOUs** and the **`r.get("id")`/`r["id"]` split** remain OPEN. Re-measure their
   reachability against this round's changes: narrower, wider, or unchanged?
5. **The P4 test on a `generate()`-landing mechanism** remains OPEN. Confirm.
6. **Convergence**, same three buckets, same "introduced by the graded delta" column. R14 was the
   first round in four with no new TOCTOU — **is that a trend or a single point?** Say which, and
   name the evidence that would settle it.

---

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table** with your own baseline, a
  **sibling table**, a **guard table**, and a **reachability verdict on every finding**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round15-v-code-{a,b}.md`.
