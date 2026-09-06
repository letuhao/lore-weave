# CP-1 · round 16 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R15's delta.** Items with an independent PASS from rounds 1–15 are not re-graded.

R15's two verdicts agreed on one systematic flaw, and it is the sixth round they have named it:
**the fix went to the doors a verifier pointed at, not to the set.** So this round's delta is
deliberately structural — `contract.check_row` is now the single definition of a valid row (shape
**and** clauses) and every row-reader calls it; the row schema is **closed** to the seven fields the
writer emits; the terminal-write gate anchors on the **bind** rather than on an assignment form; and
the catalogue-outage fact moved off a `ContextVar[bool]` onto the recorder.

**Grade whether "at the set, not at the named door" is TRUE THIS TIME — by counting, not by
reading the claim.** Enumerate every function in `app/agentruntime/` that reads a manifest row, and
every path that reaches a consumer. If the count of row-readers and the count of `check_row` callers
differ, that difference is the finding, and it is worth more than anything else this round produces.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`** — it discards
the round's real edits in the same file.

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read. Verify each injection took effect** — patch every binding, print the
  check, and build a fresh scratch tree that is not nested in a stale one.
* **A fix without a red-able test is not a closed finding.**
* **Put a reachability verdict on every finding**: production-reachable, or adversarial-input only.
* Builder's record over seven rounds: five crashes recreated inside their own fixes; **five** findings
  fixed at what a verifier pointed *at* rather than what it *meant*; a guard loosened while the
  comment beside it claimed it had not been — **twice**, the second time in a new spelling; a guard
  **deleted** during a consolidation; and a test made vacuous by an improvement.
* **This round claims its guards were proven red-able pre-commit** (14/14 membrane, 10/10 instrument)
  and that a builder-run read-twice sweep returned **0 sites**. Both claims are the builder's own
  evidence about the builder. **Re-run them.** A sweep that reports what its author expected is the
  failure this design has a standard about, and the builder's first version of that sweep counted
  writes as reads.

---

## Verifier A — the instrument

1. **The per-bind terminal-write gate.** It reds T1, T2, T2b, T3 (`:7424`, seven rounds), T5, T6, T7
   and the voice control, and is green on the pristine tree. **Find T8.** Consider: SQL assembled
   across two locals; a bind through `*args`/`**kwargs`; an executor reached by an alias; a helper
   that returns the value; `executemany`; a third module. Also grade the **NV** — the assertion that
   the anchor still matches `{_persist_terminal_assistant, _emit_chat_turn, voice_stream_response}`.
   Is naming three functions the right bound, or does it license losing a fourth writer?
2. **Routes 21 and 22 are deleted; `discovery_seed_for_surface` moved into `_NOT_A_TURN` with a
   stated reason.** Verify the reason is true of the code. Then **find route 23**. The two previous
   route fixes each created the next one, so the question is not whether the sweep is now complete —
   it is which assumption the deletion introduced.
3. **Route 18's false positive is fixed by accepting a `With`/`AsyncWith` body at depth 1**, and
   `If`/`Try` were deliberately NOT widened. Is that line drawn in the right place? An arm inside a
   `try:` body — unconditional at entry, conditional in effect — is the case to argue about.
4. **The outage fact moved onto the recorder.** `_turn_recorder` is a `ContextVar` holding the
   recorder; `arm_turn_surface` releases it **only when the sink is empty**. Attack that condition
   directly: name an ordering where it is wrong. Consider two recorders in one turn; a turn that
   never constructs one; a pooled thread whose sink object persists non-empty; a background task.
   **Say plainly whether this is better than the boolean it replaced, or merely different.**
5. **The container `try` was split and `count` is `type(...) is int` at three doors** — one of which
   the builder records as *redundant and not independently guarded*. Is that honest, or is it a
   third door that should be deleted rather than annotated?
6. **Convergence, your scope.** Same buckets, same "introduced by the graded delta" column, and this
   time also **per changed line** — the builder's delta is large and a raw count rewards shipping
   less. Is the introduction rate falling?

## Verifier B — the membrane

1. **`check_row` at four doors, `check_document_rows` for the set clauses.** Count the row-readers.
   Is there a fifth? Include `declarations`, `discover`, `SurfaceAssembler`, `load`, the drift gate,
   `_row`, `build`, and anything in `__all__`. **Does any path still reach a consumer with a row that
   `load()` would refuse?**
2. **The schema is closed to seven fields, and the four ranking fields are refused.** This is the
   answer the previous round wrote down and did not take. **Now grade the cost.** Does refusing an
   undefined field break a legitimate forward path in a way that will be discovered late — CP-2's
   `relevance`, CP-4's `lane`/`tier`/`cost`, a new field added to `_row`? The builder claims
   `check_row(row, "row")` on the writer converts a late failure into an immediate one. Verify that
   by adding a field and measuring **where** it fails.
3. **The exception hierarchy changed**: `UntrustedRow(ValueError)`, `ContractViolation(UntrustedRow)`,
   `UnresolvedReference(UntrustedRow)`, all defined in `contract.py`. Is any caller's `except` now
   catching something it did not before, or missing something it did? `UntrustedRow` becoming a
   `ValueError` is the half most likely to be wrong.
4. **The 5th TOCTOU is claimed CLOSED** (`type(doc) is dict`, and the return built from validated
   values rather than `{**doc}`). Confirm or refute, and re-measure `build`'s `r.get("id")`/`r["id"]`
   split, which the builder records as still OPEN.
5. **The P4 test now drives the queue through `generate()` as well as `build()`.** The builder's
   first version of that fix was still green on a live mechanism — it amended before writing. Verify
   the current one reds by **building the mechanism yourself**, and check the `build()` half did not
   become the vacuous one instead.
6. **Convergence**, same buckets, plus per changed line. R15's closure was **~27%**, the first rise
   in the series, and two of the four closures were incidental. **Is that a trend or a single point?**
   Name the evidence that would settle it — and if the answer is the same as last round's, say so.

---

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table** with your own baseline, a
  **sibling table**, a **guard table**, and a **reachability verdict on every finding**.
* An independent re-run of the builder's two pre-commit claims (red-ability, read-twice sweep).
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round16-v-code-{a,b}.md`.
