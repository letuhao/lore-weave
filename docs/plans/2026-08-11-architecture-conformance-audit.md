# Architecture conformance — audit, implement, run, measure

*Opened 2026-08-11. Branch `refactor/entity-lifecycle`.*

## The PO's ruling, and the order of work

> **The session is done only when the architecture is implemented correctly — not when the spec or
> the run state is complete.**

> **Audit the architecture, spec and run state → implement them correctly → then, after
> implementation is complete, do a live run and measure the real data that run produced → prove
> the architecture works.**

That is ordinary development order. This plan follows it, and the two prior attempts did not:

- **Attempt 1** measured the dev store *before* implementing and read low coverage as proof the
  architecture was unbuilt.
- **Attempt 2**, correcting attempt 1, decided the fix was a synthetic reference corpus with
  hand-authored ground truth, hypotheses registered in advance, the whole apparatus. **That was
  over-engineering** — a research instrument built to work around a problem that finishing the
  implementation dissolves.

**Why attempt 1 was actually wrong, stated correctly.** Not "because it is a dev database". Because
the data was produced by an **incomplete implementation** — ad-hoc partial runs — so it measured
the residue of half-finished work. Data produced by a **completed** implementation on a live run is
valid evidence about that implementation. The problem was the *timing*, not the environment.

So: measurement comes **last**, and it needs no special instrument. Finish the work, run it, look
at what came out.

---

## Phase 1 — AUDIT

Determine what is built and what is not. **Repo-grounded: code, schemas, wiring.** No data
required, so nothing here is blocked and nothing here is contaminated by residue.

The unit is one sealed decision from `2026-08-09-ARCHITECTURE-OVERVIEW.md` §9 — **31 rows**,
`B1–B6` boundaries · `SH1–SH4` service shape · `T1–T7` storage · `MD1–MD11` model · `SQ1–SQ3`
sequencing.

**Verdicts:**

| verdict | means |
|---|---|
| **BUILT** | The code implements it. Cite the file. |
| **ABSENT** | Not built. Includes "the mechanism exists but is not wired into the path that would use it" — an unreachable mechanism is not built. |
| **DIVERGED** | Built differently from the sealed text. Decide **sound-and-recorded** vs **drift**. (T9 shipped a different index on evidence and was right to; that is sound divergence.) |
| **UNMEASURABLE** | The decision names something that does not exist in the codebase, so no check can be written. A finding in itself — stop condition 3's `HAPPENS_BEFORE` is a confirmed instance. |

**Rule:** every verdict cites a file, a symbol or a command. Not a document. The refactor plan is
an input only where it makes a claim, and the claim is then what is under test — three times this
week a task read complete while the decision it implemented was absent (T32, T33, T38), and none
of it was findable by reading the plan.

**Also audit the spec and the run state**, but as *derived* work: where they misdescribe what
Phase 1 finds, correct them. Not as an independent exercise — that is what produced three sessions
of document churn.

- [ ] **1a** — Boundaries `B1–B6` and service shape `SH1–SH4`
- [ ] **1b** — Storage `T1–T7` *(spot-checked already: `T1` AGE eliminated ✅; `T2` **ABSENT** — only
      `neo4j_graph_store.py` + a test fake, no second adapter, and X1 requires both)*
- [ ] **1c** — The model `MD1–MD11` *(the largest group and where the gaps are)*
- [ ] **1d** — Sequencing `SQ1–SQ3`. **`SQ3` — *"every gate ships a bite; a gate that cannot fail
      is decoration"* — covers 97 wired gates and governs how much every other verdict is worth.
      `D-T38-MECHANISM-IS-VACUOUS` is one confirmed violation already.**
- [ ] **1e** — Correct the spec and run state where 1a–1d contradict them

**Output:** a 31-row table, verdict + citation. That is the implementation backlog.

### Phase 1 findings so far *(2026-08-11)*

| row | verdict | evidence |
|---|---|---|
| **T1** — AGE eliminated | **BUILT** | no AGE / Kuzu / Memgraph anywhere in the repo |
| **T2** — two graph adapters, engine chosen by shadow comparison | **ABSENT** | only `neo4j_graph_store.py` + `fake_graph_store.py` (a test double). Decision **X1 requires both candidates**; a shadow comparison with one adapter is not a comparison. Blocks `D-T17-BACKFILL-CYPHER` → T43 → QC-7 |
| **B6** — gateway policy moves to Python | **BUILT** | ⚠️ *and my first reading of this was wrong.* `src/kal/temporal.ts` still **exists**, which looked like the violation — but its policy is **gone**: it now fetches the capability from the owning service and forwards, with the rule in `knowledge-service/app/kal/temporal.py`. **File existence is not the test; policy location is.** A file-presence check would have reported a false violation here |
| **B1** — two boundaries, KAL **+ ports** | **PARTIAL** | all four ports exist (`graph_store` · `truth_store` · `vector_store` · `ontology_store`), but **84 runtime modules outside `app/db/neo4j_repos/` still import it directly, against 15 that import a port.** ⚠️ Stated as a *ratio*, not as a delta from the sealed `67` — that number's method is not reproducible, and comparing across methods is the `DRIFT-4` trap |
| **SQ3** — every gate ships a bite | **BUILT, and FAILING** | see below — the most consequential finding of the sweep |

### ⚠️ SQ3 is enforced, is red, and does not block

`scripts/gate-teeth-gate.py` already implements SQ3, on two tiers: **HARD** (a gate must contain a
reachable non-zero exit) and **RATCHET** (a gate should carry a *proof* it goes red — a printed
selftest or a test file). It is currently **FAIL: 50 gates without a red-ability proof, baseline
44.**

Two things make that worse than the number looks.

1. **It is wired into `foundation-ci.yml` but NOT into `.githooks/pre-commit`.** So it does not
   block a commit; it reddens CI later, where it has been sitting.
2. **I added two of the unproven gates this week** — `migration-drift-gate.py` and
   `authored-catalog-reader-gate.py` — while writing plan prose about how a gate that cannot fail
   is decoration. I bit both by hand in a terminal and pasted the transcript into the plan. **CI
   cannot see a pasted transcript**, and `gate-teeth-gate` is right to count that as unproven.

**Fixed for my two** (52 → 50): each now has a `--selftest` that exercises the behaviour its
accuracy actually rests on, and each selftest was itself bitten —

```
authored-catalog: disable docstring stripping  → SELFTEST FAIL, exit 1
migration-drift:  unreachable DB returns set() → SELFTEST FAIL, exit 1   (instead of None/SKIPPED)
```

The remaining **6 over baseline are pre-existing** and not mine. **This is stop condition 2**: the
instruments Phase 1 leans on are themselves partly unproven, so repairing them competes with
finishing the sweep.

## Phase 2 — IMPLEMENT

Build what Phase 1 finds ABSENT, and repair what it finds to be drift. In plan order, with this
repo's normal discipline: bite every guard, evidence pasted, QC before every commit.

**No measurement claims in this phase.** A test proving a mechanism works is not a claim that the
architecture is in force; that is what Phase 4 is for, and conflating them is how "the corpus bite
passes" came to stand in for "world order is populated".

## Phase 3 — LIVE RUN

Once Phase 2 is complete: run the real pipeline through the real application, end to end, on a
book. Rebuild images first — a stale container passes for the wrong reason, which has already
happened here.

This run **creates the data Phase 4 measures.** That is what makes the measurement valid: it is
output of the finished implementation, not sediment from development.

## Phase 4 — MEASURE AND PROVE

Measure what the Phase 3 run produced, against the decisions Phase 1 listed. This is where
`MD5`/`MD9`/`MD10` and stop condition 3 finally get answered, because there is finally something
to answer them with.

**Prove the architecture works** — the acceptance case end to end, on data the system just made.

---

## Definition of done

The architecture is implemented and a live run proves it. Not a complete document, not a full set
of checkboxes.

## Stop conditions

1. **A sealed decision turns out to be wrong** (not merely unbuilt) → stop, present evidence, the
   PO re-opens it. Do not design around it.
2. **`SQ3` finds gates broadly lack bites** → the instruments Phase 1 leans on are themselves
   unproven, and repairing them outranks finishing the sweep.
3. **Phase 4 contradicts a sealed decision** → that is the real signal this whole plan exists to
   produce. Stop and report it; do not adjust the measurement until it agrees.
