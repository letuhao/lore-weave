# CP-0 retrospective — the method was sound, the SCOPE was wrong

*Written 2026-08-04 after ten verification rounds, ~25 verifier deployments, and no closure. Not a
post-mortem on effort. A finding about where the effort was pointed, backed by the one number in
this run nobody had looked at.*

---

## 1 · The signal, and it is unambiguous

Ten rounds of independent V-CODE verdicts, per item:

| item | what it is | verdict across ALL rounds |
|---|---|---|
| 0.1 `advertised_tools` | instrument the **legacy** turn loop | **FAIL · FAIL · FAIL · FAIL · FAIL** |
| 0.2 `withheld_tools` | instrument the **legacy** narrowing stages | **FAIL ×5** — eight distinct frames |
| 0.3 `source` + `latency_ms` | instrument the **legacy** mint sites | **FAIL ×5** |
| 0.4 terminal outcome | instrument the **legacy** write paths | **FAIL ×5** |
| 0.5 frozen baseline | **a new artifact we create** | **PASS · PASS · PASS · PASS** |
| 0.6 binding measurement | **a new artifact we create** | **PASS** once run |
| 0.7 `runtime_variant` | **a new column with a default** | **PASS ×4**, mutation-verified |

**Four items never passed once in ten rounds. Three passed immediately and stayed passed.** The line
between them is not difficulty or care. It is:

> **0.1–0.4 retrofit honesty onto the runtime being replaced.
> 0.5–0.7 build something new.**

## 2 · Why the retrofit could not converge

The single defect behind 0.2 took **eight frames** — no caller · wrong variant · unpassed argument ·
armed too late · a stage above everything · two drops below everything · my own fix armed 73 lines
late · my own registration inside a branch that does not run.

That is not eight mistakes. It is **one property — "every narrowing registers" — asserted over a
surface with seven narrowing stages spread across five files, thirty mint sites and six INSERT
paths.** Each fix was correct at the layer named and blind to the next. There was never a place to
stand where the whole surface was visible.

**The new runtime does not have this problem, by construction.** `ARCHITECTURE.md` §0.1: the
membrane is **construction, not filtering** — one assembly point, one manifest, one write path. On
that surface *"every narrowing registers"* is not a property you chase across files; it is a
property you cannot violate without a compile error. **CP-1's `Admitted[D]` with a private field is
exactly this idea, and CP-0 spent ten rounds proving why it is needed.**

## 3 · The finding that changes the plan: we instrumented the CONTROL GROUP

The comparison needs the baseline's **numbers**, not the baseline's **instrument** — and V-METRIC
ruled, twice, that adding the instrument to legacy made the arms *less* comparable:

> *"The baseline can only be derived from error-prose signatures (pre-CP-0 rows have no `source`),
> while the new runtime classifies structurally and completely. **Those are different instruments**,
> so not-a-real-dispatch cannot be compared between arms — no `n` fixes that."*

The frozen side is **frozen**. It can never acquire `source`, `advertised_tools` or
`withheld_tools`. So instrumenting legacy going forward does not produce a comparable baseline — it
produces a **third population**: post-CP-0 legacy, which is neither the frozen control nor the new
treatment.

**All four baseline classes are computed from data that already existed** (`tool_calls[].ok`, the
tool name, `finish_reason`). Nothing in 0.1–0.4 was required to compute them. That is checkable in
`baseline-metrics.sql`, and it is why 0.5 passed on day one.

## 4 · What the retrofit was nonetheless worth

It was not wasted, and the record should say so plainly. Driven end-to-end it caught, in production:

- a **resume erasing the turn it resumed** — declining a confirm card deleted the pass-1→pass-2
  deletion, *the founding-defect artefact*, and replaced an executed call with a breaker entry;
- a **sweep stamping `crashed` on the row of a user who had merely deleted a message**;
- **five silent mid-turn removals** recorded with both states preserved — the arm-E defect, visible
  in production for the first time;
- **33 turns advertising `awaiting_input`** whose suspended run had expired — a success label on a
  permanently dead turn, 84.6% of that bucket.

Those are real defects in a live product, found because the instrument was partially built. **Keep
what exists. Stop trying to make it complete.**

## 5 · Where the method was right, and where it must change

**Right, and not negotiable:** the verifiers. They caught what I could not — a quotation I
*invented* to escalate, four asserted values, a fix that was a production no-op, and my own gates
green over the very defects they name. **Seven times in this checkpoint I stated as fact something I
had not checked.** A builder cannot verify itself; this run is the evidence.

**Three changes the evidence demands:**

1. **Scope a checkpoint to what one person can hold in view.** Ten rounds on one checkpoint is a
   scoping failure, not diligence. If a property spans five files, it belongs to the layer that
   makes it structural — not to a checkpoint that retrofits it.
2. **Adopt the control turn as standard technique.** V-LIVE isolated one variable — a world-setup
   turn where the intent filter provably does not fire — and disproved two rounds of my diagnosis in
   one measurement. Five frames were spent fixing *named* layers because nothing isolated a
   variable. **Use it at frame one, not frame six.**
3. **Freeze means freeze.** I broke it three times, committing while audits ran; each time a
   verifier had to re-derive from blobs to save its own work.

## 6 · Recommendation

**Close CP-0 on 0.5, 0.6, 0.7 — the three that pass — and move 0.1–0.4's properties to where they
are structural.**

| | new home | why |
|---|---|---|
| **P1** every narrowing registers | **CP-1** (membrane) | one assembly point makes it a construction property, not a hunt |
| **P2** `source` assigned structurally | **CP-2** (runtime) | the new runtime dispatches through one path |
| **P3** every terminal path writes an outcome | **CP-3.6** | already its owner: *"a plan that ends anywhere but `done_when` names what is live and hands it to a human"* |
| **P4** no constant bindings | **CP-1** | construction *is* validation |

**What CP-0 then delivers, and it is enough to start:** a frozen 315-tool baseline with its
derivation and fingerprint; a completed binding measurement with an honest null result;
`runtime_variant` recorded on every row with a fail-safe default; and — the thing it was actually
built to determine — **the knowledge that the original rate claim cannot be settled on this corpus**,
which is why the claim is now a property claim.

**The legacy instrumentation stays in place as-is**, better than it was, with its remaining holes
recorded rather than hidden. It is a diagnostic for the control group. It was never the deliverable.
