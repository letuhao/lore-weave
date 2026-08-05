# CP-1.8 / CP-1.9 · V-CODE — verifier prompt

*Committed before U-1, U-2 and 1.8 were built. **U-3 and U-4 were built BEFORE this prompt existed**
— a process deviation, recorded here rather than hidden, and they are in scope precisely because a
prompt written after them cannot be trusted to have been written to fail them.*

---

You are verifying work in the LoreWeave repository (`d:\Works\source\lore-weave`). You did not write
this code. Read source and execute it in a sandbox; do not run the live system. Do not read the
builder's commit messages or notes.

## The claims

**CP-1.9 — four ways the tool surface changed without anyone deciding it should.** All four were
found by adversarial review, and two are worse than debt: **U-2 is a live counter-example to P1**
(*every narrowing registers*), and **U-4 crossed a user boundary**.

| | claim |
|---|---|
| **U-1** | Unicode normalisation cannot silently delete a declaration from the wire. Text is normalised to **NFC at the point it enters the package**, not at each use site |
| **U-2** | a catalogue that fails to load **registers the narrowing** and **tells the model**, rather than yielding an empty surface with a log line |
| **U-3** | skill vectors are never shared between two embedding models |
| **U-4** | one user's provider-availability signal never reaches another user's turn |

**CP-1.8 — three shape changes**, designed at `ARCHITECTURE.md` §0.14:

| | claim |
|---|---|
| a | narrowing stages are **data with pipeline stage kinds**, and `order_by` is **required** before any `top_k` / `take_while_budget` |
| b | **one** canonical-serialisation implementation, gate-enforced |
| c | the purity boundary: ambient reads confined to **one named module**, gate-enforced |

## Your mandate

For each claim: **what is the input that defeats it?** Name it with `file:line`, or state the search
that found none and how you searched. A claim of absence with no method is not a finding.

**Hunting grounds, all of them defects this project has already shipped:**

1. **The correction applied in one place.** The same sentence has been found in **three files across
   three rounds**, and U-3 existed *because* its twin was patched and it was not. For every fix here,
   **search for a sibling that was not fixed.** `_TOOL_VECTOR_CACHE` / `_SKILL_VECTOR_CACHE` was one
   such pair; find the others.
2. **The capability written as though it exists.** Four instances in one document. Any comment or
   docstring claiming a gate enforces something — **run the gate and check.**
3. **The gate proven red-able by the wrong shape.** An injection proves red-ability **only for the
   shape injected**: a previous gate was declared red-able after a probe that happened to match its
   one working branch, while the branch that mattered was dead code. For each new test, ask **what
   realistic defect shape would slip past it**.
4. **The stale label.** A test class or docstring naming a property it no longer asserts.
5. **U-2's two halves.** Registering the narrowing without telling the model reproduces the founding
   defect: a verifier watched the model state a withheld tool *"does not exist at all"* while the row
   recorded it correctly. **The row was honest and the screen was not.** Check both halves.
6. **U-1's real subject.** The token estimate is **both the sort key and the accumulator** in a hard
   budget cliff, so a normalisation defect changes **which declarations survive**, not just a number.
   Verify the fix covers the path that actually feeds the budget — and that no second entry point
   was missed.
7. **§0.14's own rules turned back on the implementation.** *`order_by` required before `top_k` /
   `take_while_budget`*; *a missing field is a rejection, not a fallback*; *`id` appended as the final
   ordering component always*; *`op ∈ {eq, in, not_in}`*; *one canonical implementation*. **Each is
   checkable. Check each.**

## Judge the tests, do not rely on them

**A test may reject; it may never admit.** For each new test: is it red-able, and **by the shape that
will actually occur**? Does it assert over the artifact a consumer receives, or over an intermediate
the test constructed? Does `assert x is not None` stand in for asserting the value is right?

**For U-1 specifically:** a test that normalises its own fixture and then asserts equality proves
nothing. The subject is text that arrives **un-normalised from outside**.

## Vacuity

For every check added, state whether a realistic input makes it fire. **A gate whose subject never
occurs is a `FAIL` finding even when the code is correct.**

## Output

Write your verdict to `docs/specs/2026-08-03-agent-runtime-unification/verification/CP-1.8-1.9-v-code.md`:

1. **Verdict** per claim: `PASS` / `FAIL` / `CANNOT DETERMINE`, and overall.
2. **The falsifier** — what you looked for that would have produced `FAIL`. A `PASS` with no stated
   falsifier is recorded as `CANNOT DETERMINE` and does not close anything.
3. **Findings**, each with `file:line`.
4. **The sibling table** — for each fix, the sibling you searched for and whether it was also fixed.

Do not propose fixes. Do not grade intent. If something is well-built, say so briefly and spend your
words on what is not.
