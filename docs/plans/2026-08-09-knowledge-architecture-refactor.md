# Implementation Plan: Knowledge architecture refactor (book layer + KAL + storage ports)

Branch: `refactor/entity-lifecycle`
Created: 2026-08-09
Size: **XL** (`workflow-gate size XL 150 40 5 40` — 40 distinct semantic changes; side effects
API + DB + migration + cross-service contract set the floor)
Design (SEALED): [`docs/specs/2026-08-03-glossary-kg-entity-refactor/2026-08-09-ARCHITECTURE-OVERVIEW.md`](../specs/2026-08-03-glossary-kg-entity-refactor/2026-08-09-ARCHITECTURE-OVERVIEW.md)
· decision register §9 (31 decisions) · red team discharged

> ⚠️ **Invoke consumer commands with an explicit path override:**
> `/aif-implement @docs/plans/2026-08-09-knowledge-architecture-refactor.md`
> This filename follows the repo convention (`docs/plans/YYYY-MM-DD-<feature>.md`, per
> `.ai-factory/skill-context/aif-plan/SKILL.md`), but aif consumers discover plans by
> **branch-slug** under `paths.plans` -> `docs/plans/refactor-entity-lifecycle.md`, which does
> not exist. The single-plan fallback cannot rescue it either: that resolver branch only fires
> when git mode is off or `create_branches` is false, and this repo sets both true.
> `/aif-implement`, `/aif-verify` and `/aif-rules-check` will otherwise fail to auto-discover it.

## Original Request

scope if full plan, not small slices, need full plan first before do anything else

## Current state — read this before resuming *(2026-08-09 22:16)*

**Phase 0 LANDED (`6ee50af00`). Phase 1 LANDED (`cfbcea8b5` + `3fbf79afb`) — T4–T10, T53, QC-1.
Phase 2 slice 1 LANDED (`b042380b5`) — T11·T12·T13. Slice 2 (T14·T15·T16) done. Next: T17.**

⚠️ **Commit 5's checkpoint was re-cut, deliberately.** The plan grouped T14–T17; T14–T16 are
ADDITIVE (new ports, new fakes, a new gate — no consumer changed) while T17 rewrites 67 modules.
Those are two different risk boundaries, and the sizing gate's own rule is to checkpoint at a risk
boundary rather than a task-count. So T14–T16 commit together and T17 commits on its own.
The reported defect is fixed end to end and the read is index-served. Phase 2 is pulling Cypher
back behind the repository layer so it can go behind a port at all — and it is finding things:
T11 uncovered a **tenancy bypass**, T12 a **chapter delete that did not retract its own canon**.
⚠️ Commit 4 did **not** make the service Cypher-free — **16 files outside `app/db/` still carry
it** (T16 gates, T17 sweeps). See T13.

> ⚠️ **T9 shipped a DIFFERENT index than the plan specified, on evidence.** The task's stated
> rationale was wrong in both halves (the sort does not grow with book length; the key-only index
> does not remove it). See T9 for the measurements. Nothing in the sealed design changed — only
> the index definition the plan sketched.

| | |
|---|---|
| **Sized** | Commit 2's slice: `workflow-gate size L 10 8 3 35` → OK, no phases skippable. (Phase 0 ran at **M**.) |
| **Test DB** | throwaway DBs on `localhost:5555` created for this work — `loreweave_glossary_p0test`, `_t5test`, `_bisect`, `_headtest`. The dev DBs were not written to |
| **Test command** | `go test ./internal/api/ -count=1` — **not** `./internal/...`, which runs the `api` and `migrate` packages concurrently against one DB and reports ~30 false reds (measured at HEAD too; see T5) |
| **Live smokes** | `entity-lifecycle-guards-live-smoke.sh` (11/11) · `state-asof-live-smoke.sh` (9/9). **Rebuild the images first** — a stale container passes for the wrong reason, which already happened once here |
| **Images rebuilt** | `glossary-service` · `knowledge-gateway` · `composition-service`, from the working tree, 2026-08-09 |

**RESUME: QC-3 — finish the two owed measurements.**

**Run state as of 2026-08-10 22:2x (context compaction point).**

DONE this session: T26–T29 + T50 (**Phase 4 complete**, no open deferrals) ·
`D-T27-LIVE-REPLAY` cleared (it found lifecycle handlers that had never worked — every archive
was hitting the DLQ on a missing `project_id`) · the dead `/kg/neighborhood` upstream now served
· T25b parts 1 and 2a · `D-T25B-PG-ANCHOR-SCORE` decided and guarded by a test.

NEXT, in this order:
1. **QC-3a** — re-run `./scripts/diskann-rebuild-scale.sh 40000,70000,100000`. One point landed
   (40 000 rows → **175 s**, against 104 s predicted by the drill's curve) before a harness bug
   cut it short; the bug is fixed and the syntax checked. See
   `docs/measurements/2026-08-10-diskann-rebuild-scale.md` — the headline is that
   `maintenance_work_mem = 64 MB` fills the builder's neighbor cache at ~14 700 vectors, which
   is *below* the drill's own 20 000-row fit point and far below the 65 536 threshold. Add a
   second sweep at a raised `maintenance_work_mem`; that now looks like the real lever.
2. **QC-3b** — re-measure the `300/200` search-effort defaults above 181 rows
   (`app/benchmark/vector_backend_bench.py --rows 5000,20000`). **Do not run it while 3a is
   running** — one container, and contending for CPU corrupts both.
3. Then the rest of QC-3, and T25b part 2b.

⚠️ **T25b part 2b is genuinely blocked, not deferred by choice.** The passage read swap needs
the dual-write soak, and dual-write is default-off (`KNOWLEDGE_VECTOR_DB_URL` unset), so the
secondary has had **zero** writes. Enabling and soaking it is an operational decision about the
dev stack. Until then `vector_dual_write_total{outcome="secondary_failed"}` reads zero because
nothing is wired, which — as T25a's own docstring puts it — looks exactly like zero because
nothing failed.

**T25b — the vector READ cutover.** Both PO decisions are standing (below).
T26–T29 are done, `D-T27-LIVE-REPLAY` is cleared (it found a handler that had never worked),
and the dead `/kg/neighborhood` upstream is served. **Phase 4 is COMPLETE** (T26–T29, T50) with
no open deferrals. T25b's two PO decisions are standing: reopen T14 to add `project_id` + an
archived flag to `EntityVectorRecord`, and fork a vector-specific mapper rather than touching
`passage_to_hit`.
T27's deferral is CLEARED. It formerly read: the lifecycle events are proven as outbox rows on a
live Postgres, but nothing has yet carried one through Redis into Neo4j. T25b (the READ cutover) is parked below on two PO decisions; Phase 4 needs none of them.

**T25b — the READ cutover.** ⚠️ Two decisions are the PO's, listed at the bottom.

**T25a is DONE (write path wired).** `app/adapters/vector_store_provider.py` is the composition
root Phase 3 never had. The three vector WRITE sites — `passage_ingester`, `glossary_passage`,
`entity_embedder` — now go through `VectorStore`, so
`vector_dual_write_total{outcome="secondary_failed"}` **can move**, proven by a live test that makes
it move. Default-off: with `KNOWLEDGE_VECTOR_DB_URL` unset the factory returns a plain
`Neo4jVectorStore` and behaviour is unchanged.

**T25b — what remains of the cutover.** Reads still call `find_passages_by_vector` directly from
`context/selectors/passages.py`, `routers/public/drawers.py` and `search/retriever.py`. This is
NOT a mechanical swap, and the reason is worth reading before planning it: those hits flow into
`passage_to_hit`, which is **shared with the CJK lexical leg**. That leg is not a vector search and
will never come through this port, so changing the shared hit shape to the port's `VectorHit` would
rewrite a retrieval path this migration has no business touching. Also `VectorHit.attributes` does
not carry `block_index`, which `passage_to_hit` reads — a small, real gap to close first.

**Before the read cutover can be argued for, the secondary must have been receiving writes long
enough for the gate to mean something.** T25a made the gate real; it still has to be *watched*.

**✅ T25b PART 1 IS DONE — both PO decisions implemented, no read switched.**
`EntityVectorRecord` now carries `project_id` + `archived` (the T14 reopen), the Neo4j adapter
carries `block_index` (the gap the plan named) plus the entity lifecycle pair, and
`vector_hit_to_raw_hit` sits BESIDE `passage_to_hit` rather than replacing it. 4145 python
tests green (+6). *Bite: drop `blockIndex` from the fork → the field-for-field agreement test
and the block test both red.*

The read sites are deliberately UNTOUCHED. This plan's own precondition — *"the secondary must
have been receiving writes long enough for the gate to mean something"* — is not met:
dual-write is default-off (`KNOWLEDGE_VECTOR_DB_URL` unset), so the secondary has received
**zero** writes. Switching reads to a store nothing has fed would not be a cutover, it would be
an outage with a port in front of it.

✅ **T25b PART 2a IS DONE — the entity refusal is lifted.** `PgVectorStore.search(scope=
"entity")` now filters on `project_id` and `NOT archived`, the upsert writes both, and the
tenant index widened to `(user_id, project_id)` so the project predicate reaches the planner
rather than a post-filter. **21 pgvector integration tests green on a live pgvector Postgres**
(6 of them new), 4145 unit tests green.

⚠️ **`CREATE TABLE IF NOT EXISTS` does nothing to an existing table** — so the two new columns
would have appeared on every fresh test database (where these tests run) and on **no
deployment that already had data**, passing here and failing in production on exactly the
installations that matter. `ensure_vector_schema` now runs an explicit
`ADD COLUMN IF NOT EXISTS` pair, and a test drops the columns to simulate a pre-T25b table and
asserts they are repaired.

⚠️ **The refusal was pinned by an integration test that had been SKIPPING** — Postgres-gated,
so the suite reported green over an assertion nobody had run since T23. It is replaced by five
real ones. *(Bite: remove the `NOT archived` predicate → "an archived entity reached a default
search".)*

✅ **`D-T25B-PG-ANCHOR-SCORE` — CLOSED as a decision, with a guard.** It is not a gap to fill
in the adapter, and the first framing of it here was too weak.

`recompute_anchor_score` is `mention_count / max(mention_count)` **across a bucket**. The value
therefore changes when a *different* entity's mention count moves, without the entity itself
being touched — so a copy on the vector row would need rewriting for **every row in the bucket
on every recompute**. That is a mirror which drifts *by construction*, which is precisely the
failure T27, T28 and T29 each spent a task closing. **Write-through is the wrong fix, not a
smaller one**, and "the caller joins" is no better: the follow-up fetch the consumer already
makes goes to *glossary-service*, not the graph, so it cannot supply a KG-owned score.

**The decision: the store that OWNS `anchor_score` serves the entity read path.** Today that
holds for free — dual-write reads the primary, and the primary is Neo4j. The pg entity search
built above is correct and proven for lifecycle-filtered retrieval; it is simply not the store
that can rank two-layer.

**The risk is not in today's code — it is in the change that makes Postgres primary**, which
nobody writing that change would be reading this file to discover. So the mechanism is a test,
not a note: `tests/unit/test_vector_primary_owns_anchor_score.py` asserts dual-write reads the
primary, that the provider still composes Neo4j as primary, that `_ENTITY_ATTRS` still omits
the score, and that this deferral is still recorded in the plan.
*(Bite: swap the dual-write arguments — i.e. begin the read cutover — → "the dual-write
argument order changed … close D-T25B-PG-ANCHOR-SCORE first".)* 4149 unit tests green.

⬜ **T25b PART 2, what remains:**
2. The dual-write soak. `vector_dual_write_total{outcome="secondary_failed"}` must be watched
   with the secondary actually enabled before a read swap can be argued for at all.
3. Only then the three read sites (`context/selectors/passages.py`,
   `routers/public/drawers.py`, `search/retriever.py`).

### 🔻 DEFERRAL `D-T25B-SOAK` — the passage read swap, blocked on an operational decision

| | |
|---|---|
| **Blocker** | The read swap's own precondition is unmet. Dual-write is default-off (`KNOWLEDGE_VECTOR_DB_URL` unset), so the Postgres secondary has received **zero** writes. Switching reads onto a store nothing has fed is not a cutover; it is an outage with a port in front of it. |
| **Evidence** | `app/adapters/vector_store_provider.py` returns a plain `Neo4jVectorStore` when the env var is unset (T25a, asserted by test). Consequently `vector_dual_write_total{outcome="secondary_failed"}` reads **0** — and as T25a's own docstring puts it, *a gate that reads zero because nothing is wired looks exactly like a gate that reads zero because nothing failed*. The counter is not evidence of health here; it is evidence of absence. |
| **To unblock** | Someone with authority over the dev stack sets `KNOWLEDGE_VECTOR_DB_URL`, and the secondary then takes real traffic for long enough that a zero on the failure counter means something. **This is an operational decision about a shared environment, not a code change** — which is exactly why it is not mine to make unilaterally. |
| **Mechanism** | `tests/unit/test_vector_primary_owns_anchor_score.py::test_the_provider_keeps_neo4j_as_primary` asserts on the **constructed** store that Neo4j is primary and that `DualWriteVectorStore(primary, secondary)` keeps that argument order. Any attempt to begin the read cutover reds it with a message naming this deferral. A note in a file nobody is editing would not have done that; T27 already proved that failure mode here, shipping handlers that could never run. |
| **Retry when** | `KNOWLEDGE_VECTOR_DB_URL` is set on the dev stack **and** the soak has produced a non-trivial write count with `secondary_failed` observed at zero *while writes were demonstrably flowing*. Both halves are required; the second without the first is the trap above. |

**PO decisions (both ANSWERED, kept for the record):**

1. **The entity read path.** `PgVectorStore.search(scope="entity")` refuses, because
   `include_archived` and `project_id` describe lifecycle state a vector-only store does not hold.
   Closing it means adding those fields to `EntityVectorRecord` — **a T14 port change**, which is
   why it is not a quiet fix.
2. **Whether the read cutover keeps `passage_to_hit` shared** or forks a vector-specific mapper.

Also owed for the RTO: **a diskann rebuild measured above 65 536 vectors**
(`diskann.min_vectors_for_parallel_build`), since every number in the restore drill was taken below
that threshold and is therefore single-threaded. QC-3 owns it, along with the scale re-measure of
the 300/200 search-effort defaults (measured at 181 rows; the named fallback is pgvector's HNSW,
which hit 1.000 at the server's own defaults for dims ≤ 2000).

**Still open elsewhere:** the 6 `db/migrations/` backfills that carry Cypher — now tracked as
`D-T17-BACKFILL-CYPHER` under T17, gated at 6 by `scripts/graph-port-gate.py`; QC-2's
rendered-block diff, owed once a consumer holds a port; and 283 Postgres-gated integration skips.
*(This list appeared twice in this header, verbatim, and one copy is now deleted — a duplicated
debt list is a debt list that gets updated in one place.)*

⚠️ **Verify the extension matrix on PG18.** T21 measured on PG17 (the readily available image);
the design records pgvectorscale supports PG18 via `--pg18 pg_config`, and T22 is where that stops
being a citation and becomes a build.

⚠️ **Two debts recorded rather than dropped:** (a) QC-2's *rendered-block* diff is owed once a
consumer actually holds a port (T17); the port-level diff shipped in its place. (b) **283 Postgres
skips** remain in `tests/integration/db` — the same "env-gated tests skip and the suite lies"
problem one backend over, and its own slice.

Live-parity recipe: `docker run -d --name lw-neo4j-scratch -p 7999:7687 -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community`
then `TEST_NEO4J_URI=bolt://localhost:7999 pytest tests/integration/db`.

A throwaway Neo4j for the live suite:
`docker run -d --name lw-neo4j-scratch -p 7999:7687 -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community`
then `TEST_NEO4J_URI=bolt://localhost:7999`. The fixture now REFUSES ports 7687/7688 (the dev
graph) unless `TEST_NEO4J_ALLOW_SHARED=1`.

⚠️ **283 skips remain and they are POSTGRES** (`TEST_KNOWLEDGE_DB_URL`), not Neo4j — the same
"env-gated tests skip and the suite lies" problem, one backend over. Worth its own slice.

⚠️ Two of those 15 need a decision rather than a move: the six `db/migrations/` backfills are
admin one-shots reachable through `internal_backfill.py`, so **Phase 7's engine swap must either
port or retire them** — they will silently break against a new engine otherwise.

⚠️ **Bite discipline, learned the hard way in T11:** several files in knowledge-service are
**CRLF**, and a `perl -0pi` pattern containing `\n` silently no-matches — a bite that never applied
reads exactly like a guard with no teeth. Use `/tmp/bite.py` (normalises line endings and **exits
non-zero if the pattern is absent**) or an equivalent, and never conclude "redundant guard" from a
green run you did not verify mutated the file.

**Found in passing, NOT fixed, routed to T27:** `apply-edit` carries no liveness guard, so editing a
trashed entity **commits the write and then returns 500** from its own post-commit read-back
(`loadEntityDetail` filters `deleted_at IS NULL`). Measured identical with the Phase-0 changes
stashed, so it is pre-existing and orthogonal. Whether a trashed entity is editable at all is a
command-contract decision, which is exactly what T27 is for.

## ▶ Run policy — read before executing, this plan RUNS, it does not report

**Default: keep going.** Finish a task, paste its evidence into the task, start the next one. Do not
stop to summarise, do not ask whether to continue, do not hand back at a task boundary because the
next task looks large. A plan of 61 tasks that stops every second task is not being executed, it is
being narrated.

**Commit checkpoints do NOT ask.** `/aif-implement` Step 3.8 offers *"ready to commit?"* at every
checkpoint — on this plan that is **14 interrupts**. Treat every checkpoint as pre-authorised and
commit without prompting. The authorisation is not blanket: **the QC task guarding that checkpoint
must be green first**, which is the same gate that already governs the commit. QC green ⇒ commit and
continue. QC red ⇒ fix it, still without asking.

**The complete list of legitimate stops.** Nothing else qualifies:

| stop | why |
|---|---|
| **QC-3, QC-5, QC-7** — the three ⏸ POST-REVIEW checkpoints | the design mandates human sign-off before a data migration, a model change and an engine swap. Present evidence and WAIT |
| **A stop condition fires** (T8 · T21 · T33 · T41 — see Stop conditions) | the design is wrong and must be re-opened, not worked around |
| **A gate blocks on a decision only the PO can make** | e.g. T9's index-build strategy if both options are unacceptable |
| **Context is genuinely exhausted** | see below — this is a handoff, not a pause |

**Running out of context is not a stopping point, it is a handoff.** Before the window closes:
update the touched task with its evidence, refresh the **Current state** block above (dirty files,
resume task, anything half-done), and end with the single line `RESUME: <task id>`. The next
invocation reads that and continues. A half-finished task is fine *if it is written down*; what is
not fine is stopping cleanly and calling it done.

**To span context windows automatically**, drive it with the loop skill rather than re-typing:

```
/loop /aif-implement @docs/plans/2026-08-09-knowledge-architecture-refactor.md
```

Self-paced (no interval) — it re-enters after each window with the plan as the source of truth. The
POST-REVIEW checkpoints still stop it, which is the point.

## PO decisions taken during execution *(2026-08-09)*

Recorded here so they are not re-derived, and not "optimised" away by a later reader.

| # | decision | why it is written down |
|---|---|---|
| **X1** | **Phase 7 builds BOTH graph adapters; the engine is chosen by P2 shadow comparison** — as sealed (T2). The fact that T6's re-open tripwires already measure **zero** (p50 entity degree 0, no query needing variable-length `RELATES_TO` past depth 2) is **not** grounds to pre-narrow to Postgres-relational and skip Kuzu | the shallow workload is shallow *because relationship extraction is immature* (3 of 8 edges defensible) — the sealed design says so itself. Choosing on that basis would decide the engine by an artefact of a known-weak extractor rather than by measurement. The plan's method is shadow comparison; a cheaper argument does not replace it |
| **X2** | **The four gate measurements stay at their scheduled slices** — T8, T10, T21, T41 are **not** front-loaded | they are already sequenced immediately before the work they gate, and each carries a stop condition. Pulling T21 or a T41 spike forward buys earlier warning at the cost of context-switching out of a phase that is not finished |
| **X3** | **QC-0 runs before Commit 1**, and the same rule holds at every later checkpoint | option 1 of the resume question; it is also what the QC spine already says |

## Settings

- Testing: **yes** — AC1/AC2 are the deliverable, written red-before-green
- Logging: **verbose** — DEBUG detail; every read logs its resolved position, every caller that
  omits one logs `WARN`
- Docs: **yes** — mandatory documentation checkpoint at completion

## Scope note

This is the **whole sealed design**, not a slice, per the PO. Phases are ordered so each is
independently valuable and independently revertible; the plan may be stopped after any phase without
leaving the tree in a half-state. **Phase 1 ships the reported defect** — that ordering came from the
red team (RT-1) and is deliberate.

**Not in scope:** the manifest, the reality DB, the game engine (below the PO's hard boundary);
`Q-L5A-1` canon emission; wiki generation moving out of knowledge-service (recorded, not planned).

---

## Quality Control spine

> **Audit, 2026-08-09:** the first draft of this plan had **measurement but no QC** — zero review,
> QC, POST-REVIEW, smoke, dogfood or E2E tasks, against a repo whose 12-phase workflow mandates
> REVIEW(code) · QC · POST-REVIEW and whose corpus carries 12+ `*-live-smoke.sh` scripts. Worse, the
> design's own register states the acceptance test in one line — *"fix the design, then **re-run this
> book**"* — and the plan never re-ran it. This section is the correction.

**Three independent controls. A phase is not done until all three are green.**

| control | what it proves | why the others do not |
|---|---|---|
| **① Code review** — `/aif-review +check` at every commit checkpoint; `/review-impl` on Phases 4, 5, 7 | the change is *correct and idiomatic* | tests pass on wrong code all the time |
| **② Live proof** — a `*-live-smoke.sh` per phase, run against a real stack | the wiring is *actually connected* | this repo's own lore: **a green suite proves the working tree, not the commit**; an env-gated test that skips makes the suite lie; and injecting a fake at the chokepoint cannot prove the chokepoint is wired |
| **③ Real-run data** — logs + measured output from a real book | the *behaviour changed for a reader* | a unit test cannot tell you the critic still scores 5/5 on a wrong betrayal |

**Evidence gate (repo phase 6).** Every task's Definition of Done is *evidence pasted into the
commit or the plan*, never a ticked box. `checklist ⇒ test the effect` — a self-report is not a
control.

**Human checkpoints (repo phase 9).** POST-REVIEW is a **stop-and-wait** after Phases 3, 5 and 7 —
the three phases that migrate data, change the model, or swap an engine.

---

## Deferred rows this plan discharges — and the ones it does NOT

> **Why this section exists.** This refactor's own README records **three bugs declared "already
> closed" that were open** at `24dd7bdac`, because *"that sentence was their entire tracking
> mechanism."* The `DEBT-REGISTER.md` was created for exactly this failure. **A row is discharged in
> the register in the same commit that closes it** — never "at the end", never by assertion.

| row | discharged by | commit |
|---|---|---|
| `D-GLOSSARY-KG-REFACTOR-DESIGN` | ✅ already — the sealed design (`a96d241ac`) | done |
| `D-ENTITY-EXISTS-GUARD` | T1 | Commit 1 |
| `D-KNOWN-ENTITIES-PER-JOB` | T2 | Commit 1 |
| `D-OUTBOX-PAYLOAD-TRASH` | T3 | Commit 1 |
| `D-GLOSSARY-EVENTS-NO-SOT` | T30 | Commit 9 |
| `D-ENTITY-LIFECYCLE` | T31 + QC-4 | Commit 9 |
| `D-ENTITY-IDENTITY-HASH` | T35 + QC-6 | Commit 10 |
| `D-CANON-CHECK-BLIND-TO-ROLE` | T36 + **QC-5 (the dogfood re-run)** | Commit 10 |

**Explicitly NOT closed by this plan** — recorded so nobody assumes they were:

| row | why not |
|---|---|
| `D-KG-KIND-FACETS` · `D-KIND-FACETS-SURFACE` | the kind-spec M4 halves; they ride the KG mirror this refactor re-cuts, but are their own work |
| `D-KG-EDGE-TYPING-UNCHECKED` | needs the kind mirror first; it is a consumer of what T33 builds |
| `D-BOOTSTRAP-PREVIEW-LIES` | fix-now shaped, one function, needs none of this — do it independently |
| `D-UNKNOWN-PARK-IS-PROSE-NOT-DATA` | load-bearing only when the refactor re-kinds parked entities in bulk |

**Per-task rule:** any task whose commit closes a row above must, in the same commit, (a) strike the
row in `DEBT-REGISTER.md` with the closing commit sha, and (b) update the Deferred Items table in
`docs/sessions/SESSION_HANDOFF.md`. `scripts/deferral-gate.py` runs pre-commit — if a row's mechanism
does not change colour by itself, it is not discharged.

---

## Standards that govern this work

Read before touching the area they name — per `.ai-factory/skill-context/aif-plan/SKILL.md`.

| rule | why it applies here |
|---|---|
| **INV-KAL** (`scripts/knowledge-access-gate.py`, `knowledge-http-surface-gate.py`) | every phase touches the KAL's scope; both gates are pre-commit and must stay green |
| **INV-FACTS / SCOPE-3** (`docs/standards/scope-separation.md`) | `entity_facts` is truth; the EAV projection and prose snapshot are regenerable caches. Phase 8 **rewrites** this row — deliberately, per T7 |
| **Settings & Configuration** (SET-5 *must be consumed*) | the whole refactor is a stored-but-never-read cure; do not add another write-only field |
| **Two-layer glossary↔knowledge** | Phase 8 rewrites `D-SUBSTRATE-HOME`; until then it holds |
| **Language rule** (`contracts/language-rule.yaml`) | Go = glossary, Python = knowledge, TS = gateway. **Logic may not move into the gateway** (decision B2) |

---

## Commit Plan

Checkpoint at **risk boundaries** (contract, migration, cross-service seam) — not at file counts,
per the sizing gate's own guidance.

**No commit lands without its QC task green** (see the QC spine). Each checkpoint below is preceded
by a `QC-n` task carrying code review + live proof; three of them are **stop-and-wait** POST-REVIEW
checkpoints.

- **Commit 1** (T1–T3): `fix(glossary,translation): close the three lifecycle guards recorded as closed`
- **Commit 2** (T4–T8, **T53**): `feat(kal,glossary): state@as_of read + AC1/AC2 conformance`
- **Commit 3** (T9–T10): `perf(glossary): covering index for the book-wide as-of read`
- **Commit 4** (T11–T13): `refactor(knowledge): pull Cypher out of selectors, events and extraction`
- **Commit 5** (T14–T17): `refactor(knowledge): VectorStore + OntologyStore ports with fakes`
- **Commit 6** (T18–T20): `refactor(knowledge): GraphStore + TruthStore ports`
- **Commit 7** (T21–T25): `feat(knowledge): pgvector adapter, dual-write, cutover`
- **Commit 8** (T26–T29, **T50**): `feat(kal,glossary): command surface with outbox-in-transaction + MCP parity`
- **Commit 9** (T30–T34, **T52**): `feat(glossary): lifecycle, story status, world order`
- **Commit 10** (T35–T37, **QC-5**): `refactor(glossary,knowledge): opaque identity + mentions`
- **Commit 11** (T38–T40, **T51**): `refactor: migrate consumers onto the KAL + frontend`
- **Commit 12** (T41–T43): `feat(knowledge): second graph adapter + shadow comparison`
- **Commit 13** (T44–T46): `refactor: consolidate TruthStore`
- **Commit 14** (T47–T49): `docs: document the new contract, verify the plan, discharge the register`

---

## Tasks

### Phase 0 · The three fix-now bugs *(independent — no design dependency)*

Recorded as *"already closed"* and re-verified open at `df18e9049`. Each is single-file with a known
root cause. They are first because they are cheap and because Phase 4's gate would otherwise have to
allowlist them.

- [x] **T1** — Add `deleted_at IS NULL` to `entityExistsInBook` — **IMPLEMENTED, uncommitted**
  `services/glossary-service/internal/api/entity_genres_handler.go:37`
  Guards 6 paths; the canonical-translation one fires a **paid LLM call** on deleted content and
  caches the result. Mirror the correct twin at `pipeline_read_tools.go:104`.
  **Logging:** `DEBUG` the entity id + book id + resolved liveness on every guard call; `WARN` when
  a request is refused because the entity is deleted (that WARN is the regression detector).
  **Test:** delete an entity, call canonical-translation, assert 404 and **assert no LLM call**.
  ---
  **Evidence.** Liveness resolves through the existing `entityDeleteState`, so *absent / other book /
  purged* and *in the recycle bin* stay distinguishable — only the second logs `WARN`, which is what
  makes that line a detector rather than noise. The guard is shared by 8 HTTP call sites
  (canonical-translation · entity-genres ×2 · facts ×2 · fold ×3) plus 2 MCP tool sites.
  Test: `entity_lifecycle_guard_test.go::TestDeletedEntity_CanonicalTranslationRefusedAndSpendsNothing`
  — asserts **404**, **0 claim rows** in `canonical_snapshot_translations` and **0 MT calls**. The
  claim row is the single-flight ticket (exactly one row per launched fill), so zero rows proves no
  fill was launched *without racing the background goroutine*. A restore-and-retry control in the
  same test asserts the live path still reaches 200 + 1 claim row.
  **Bite (run, not asserted):** fix reverted → the trashed entity returns
  `200 {"status":"translating"}` — it claims the row and launches the paid fill on deleted content.
  ```
  WARN entity-in-book guard refused a deleted entity entity_id=019fe6c1-… liveness=deleted
  --- PASS: TestDeletedEntity_CanonicalTranslationRefusedAndSpendsNothing (0.36s)
  ```

- [x] **T2** — Re-fetch `known_entities` per chapter — **IMPLEMENTED, uncommitted**
  `services/translation-service/app/workers/extraction_worker.py:474` (fetch) vs `:589` (loop)
  A book-wide job holds the list for its lifetime, so a mid-job delete is re-emitted for every
  remaining chapter.
  **Logging:** `DEBUG` the known-entity count at each chapter boundary; `INFO` when the count
  changes mid-job (that is the bug becoming visible).
  **Test:** delete an entity mid-job; assert it is absent from the next chapter's known set.
  ---
  **Evidence.** Two holes, not one. The refetch closes entities the *server* knows; it cannot close
  entities **this run created**, which sit below the endpoint's `min_frequency` floor until a second
  chapter mentions them and which the old code appended locally for prompt continuity. Those are now
  held by `entity_id` and pruned on the same boundary by `POST /internal/books/{id}/entities/by-ids`,
  which already drops soft-deleted ids ("soft-absent", DI3) — a batched liveness probe, **no new
  contract**. It fails toward the old behaviour on a glossary hiccup, so an outage cannot silently
  strip prompt context.
  ⚠️ **Scope note:** this is 2 files, not 1 — `glossary_client.py` gains the thin
  `fetch_live_entity_ids` helper. Stated because the plan called T2 single-file.
  Test: `tests/test_extraction_known_entities_refresh.py` — 3 tests (the deletion; *one fetch per
  chapter, not per job*; the session-created prune, with a still-live control).
  **Bite (run):** restoring "fetch once per job" → the deleted entity survives into chapter 2
  (`{'Ao Bing','Nezha'} == {'Nezha'}` fails) and the per-chapter fetch count falls **3 → 1**.

- [x] **T3** — Add a lifecycle filter to the outbox payload query — **IMPLEMENTED, uncommitted**
  `services/glossary-service/internal/api/outbox.go:398` — `WHERE e.entity_id = $1` with no filter,
  so editing a trashed entity re-publishes it and knowledge-service re-embeds it. **The deletion is
  silently reversed in the consumer's index.**
  **Logging:** `WARN` when an outbox row is skipped because its subject is deleted.
  **Test:** soft-delete, then edit; assert no `entity_updated` is emitted.
  ---
  **Evidence.** The filter alone was **not sufficient**, and that is the interesting part: the three
  best-effort emitters honour `ok=false` and return, but every *transactional* caller reads the AFTER
  snapshot with `_` for `ok`, so a lifecycle-filtered read would have emitted an **empty payload**
  rather than none at all. So `emitEntityUpdatedTx` gained a liveness check **inside the writing tx**
  — the transactional twin of the filter. Restore is unaffected (it clears `deleted_at` in its own tx,
  before any emit); merge's `entity_merged` is untouched, since that event is *about* a deletion.
  Test: `entity_lifecycle_guard_test.go::TestDeletedEntity_EditEmitsNoOutboxEvent`, live-edit control
  first (must emit exactly 1), then trash-and-edit (must still be 1).
  **Bite (run):** fix reverted → `entity_updated` count goes **1 → 2**.

- [x] **QC-0** — Review + live proof for the three guards — **GREEN**
  `/aif-review +check` on the diff. Then **live**: on a running stack, soft-delete an entity and
  (a) call canonical-translation → assert 404 **and zero LLM spend** in `usage_logs`; (b) edit it →
  assert no `entity_updated` on `loreweave:events:glossary`.
  **Why live:** T1–T3 are all *bypass* bugs. A unit test with a mocked pool cannot prove the real
  guard is on the real path — that is the inject-at-the-chokepoint trap.
  ---
  **① Code review — `/aif-review +check`.** Validator: 4 keep, 1 modify (0 dropped, 0 reclassified).
  **One CRITICAL found and fixed during the review:** `_refresh_known_entities` sat two lines *above*
  the per-chapter `try:`, and `fetch_known_entities` returns `resp.json()` unvalidated — so a
  malformed glossary response raised `AttributeError` out of the refresh, past the chapter-level
  `except`, and killed the **whole job**. Strictly worse than the fetch-once code it replaced, which
  could at most fail one chapter. Fixed by normalising the response; 4th test added; bite:
  `AttributeError: 'str' object has no attribute 'get'` with the normalisation removed.
  Five non-blocking suggestions recorded, none merge-blocking. Gate: `warn`, 0 blockers.

  **② Live proof — `scripts/entity-lifecycle-guards-live-smoke.sh` (new).**
  Images rebuilt first: `infra-glossary-service-1` was a **2026-08-01** build, so the stack as it
  stood would have tested the old binary and passed for the wrong reason. Real Postgres, real Redis
  stream, real relay, fixture book discovered at runtime (no UUID pinned in a tracked file), scratch
  entity minted and purged by the script's own trap.

  | | with the fix | on the pre-fix binary (rebuilt to check) |
  |---|---|---|
  | T1 canonical-translation on a trashed entity | **404**, **0** claim rows | **200 `translating`**, **1 claim row — a paid MT fill launched on deleted content** |
  | T1 control, same call on a live entity | 200, exactly 1 claim row | 200, 1 claim row |
  | T3 edit a trashed entity → outbox | **0** new `entity_updated` | **1** new `entity_updated` |
  | T3 edit a trashed entity → `loreweave:events:glossary` | **0** frames | **2 frames — a consumer re-anchors a deleted entity** |
  | T2 `entities/by-ids` drops a soft-deleted id | omitted (live control: returned) | same (never the broken half) |

  **`passed=11 failed=0` GREEN** with the fix · **`passed=7 failed=4` RED** without it.

  ⚠️ **The stream leg was vacuous on the first run and was fixed.** The relay *polls* (~33 s); the
  first version asserted absence 3 s after the write, so "0 frames" would have held for an event that
  simply had not shipped yet — and it did: the control frame was missing too. The smoke now waits for
  the control frame to **actually arrive** and only then trusts the absence; if the control never
  lands it says `SKIP` rather than claiming a pass. That is why the pre-fix run could report 2 frames.

  **③ Real-run data:** the pre-fix numbers above *are* the real-run data — a paid machine-translation
  call bought on author-deleted content, and two stream frames re-anchoring a deleted entity in a
  consumer's index, both observed on the live stack rather than argued from the code.

  **Stated gap, not silently skipped:** T2's *worker* half (the per-chapter refetch) is unit-covered
  with a bite but is **not** live-smoked — proving it end-to-end means running a real extraction job
  and deleting an entity mid-run, which spends LLM budget. What the smoke proves live is the
  cross-service contract that half depends on (`entities/by-ids` drops a soft-deleted id). The
  worker path gets its live exercise in **QC-4**, whose smoke already asserts the per-consumer effect
  of a trash across translation.

<!-- Commit checkpoint: T1–T3 -->

### Phase 1 · Prove the read shape *(S-0.5 — ships the reported defect)*

The substrate already works; nothing reads it. `composition-service` passes `as_of` **zero** times.

- [x] **T4** — Write AC1 + AC2 as failing conformance tests **first** — **RED, as required**
  New: `services/glossary-service/internal/api/state_asof_test.go`
  **AC1:** character dies ch.40 → `as_of=41` reports dead; **`as_of=39` reports present and ALIVE**.
  The second half is what proves the mechanism is temporal — a `deleted_at`-style implementation
  passes the first and fails the second.
  **AC2:** an attribute changes at ch.10/25/60 → `as_of=30` returns **exactly the ch.25 value**, one
  value per attribute.
  **Both must be RED before T5.**
  ---
  **Evidence.** 4 test functions, **all RED** at `6ee50af00` — every assertion reports `404`, the
  router having no such route:
  ```
  --- FAIL: TestStateAsOf_AC1_DeathIsTemporalNotAFlag        (3 subtests, all 404)
  --- FAIL: TestStateAsOf_AC2_OneValuePerAttributeAtAPosition
  --- FAIL: TestStateAsOf_MissingAsOfIsRejected              (missing / non-numeric / negative)
  --- FAIL: TestStateAsOf_InvalidatedFactsAreExcluded
  ```
  **This file is also the contract T5 implements** — the response shape is asserted here, and
  `facts` is a **list, not a map keyed by attribute**, deliberately: AC2's claim is *exactly one
  value per attribute*, and a map satisfies that by construction.
  ⚠️ **Corrected during T5:** the list shape is necessary but was **not sufficient** — AC2's three
  intervals are disjoint, so `DISTINCT ON` could be deleted with the file still green. See T5's first
  bite; a sixth test now seeds an unclosed chain, which is the condition that actually needs it.
  Beyond the two acceptance cases it pins three things a later reader would otherwise have to guess:
  the **half-open boundary** (`as_of=40` is the first *dead* chapter — an off-by-one here decides
  whether the chapter someone dies in describes a living or a dead character), that the response
  carries **which interval answered** (`valid_from_ordinal`), and that an **invalidated** fact is
  excluded however well its story interval matches (story time and belief time are different axes).
  ⚠️ **Two assertions were vacuous on first write and were fixed before this was called done** —
  "expect nothing" checks pass against an endpoint that does not exist. Both now assert `200` first,
  and the invalidated-fact test seeds a second, *live* fact as a control so its silence about the
  invalidated one means something.

- [x] **T5** — `GET /internal/books/{book_id}/state?as_of=N` in glossary-service — **GREEN**
  New: `services/glossary-service/internal/api/state_handler.go`; register in `server.go`
  `DISTINCT ON (entity_id, attr_or_predicate)` over the half-open predicate, `cardinality='single'`,
  `invalidated_at IS NULL`. **`as_of` is REQUIRED** — a missing position is `400`, never a default
  (decision: a default returns a silently wrong answer).
  **Logging:** `DEBUG` resolved `as_of`, row count pre/post `DISTINCT ON`, elapsed ms; `WARN` on a
  request without `as_of`.
  (depends on T4)
  ---
  **Evidence.** `internal/api/state_handler.go` + one route at `server.go:146`. All six tests pass on
  a fresh throwaway DB (`loreweave_glossary_bisect`, created for this run):
  ```
  --- PASS: TestStateAsOf_AC1_DeathIsTemporalNotAFlag (3 subtests)
  --- PASS: TestStateAsOf_AC2_OneValuePerAttributeAtAPosition
  --- PASS: TestStateAsOf_AC2_OverlappingIntervalsCollapseToTheFreshest
  --- PASS: TestStateAsOf_MissingAsOfIsRejected
  --- PASS: TestStateAsOf_InvalidatedFactsAreExcluded
  --- PASS: TestStateAsOf_TrashedEntityIsExcluded
  ```
  The pre-`DISTINCT ON` row count the logging spec asks for comes from `count(*) OVER ()` in the same
  query — window functions are evaluated before `DISTINCT ON` in Postgres, so the log line costs no
  second round trip. Nothing is ever truncated: past `stateSizeWarnFacts` the read `WARN`s and returns
  everything, because a silently capped state read is precisely the confidently-wrong answer this
  endpoint exists to remove (that ceiling is T8's measurement, not a cap).

  **Five bites, each reverted after measuring.** Every one names a real failure mode:

  | remove | goes red as |
  |---|---|
  | `DISTINCT ON` | `as_of=30 returned 2 rank values, want exactly 1` |
  | `DESC` → `ASC` on the tie-break | returns the ch.10 value where ch.25 is current |
  | `invalidated_at IS NULL` | a superseded fact surfaces as canon |
  | `valid_from <= N` → `<` | `as_of=40 life_status = []` — the death chapter loses every fact |
  | `e.deleted_at IS NULL` | a trashed entity is handed to the drafting agent |

  ⚠️ **T4's own DISTINCT-ON claim was wrong, and the first bite is what caught it.** Deleting
  `DISTINCT ON` left the whole file **green**: AC2 seeds `[10,25) [25,60) [60,∞)`, three *disjoint*
  intervals, so the `WHERE` clause alone already returns one row at position 30. The T4 evidence below
  asserts that list-not-map shape made the assertion falsifiable — it did not, for that fixture.
  The condition `DISTINCT ON` actually defends against is an **unclosed chain** (`maintain_chain`
  fails to stamp `valid_to_ordinal`, so two values are simultaneously current), which is a substrate
  bug the read must survive rather than forward. `TestStateAsOf_AC2_OverlappingIntervalsCollapseToTheFreshest`
  seeds exactly that and now bites both ways — missing `DISTINCT ON` **and** a non-deterministic
  tie-break.

  ⚠️ **Scope note — a THIRD axis, beyond what T5 specified.** The task named story time and belief
  time. `glossary_entities.deleted_at` is neither: it is the author's recycle bin, and it has no story
  position at all. An entity in the bin is not canon at any ordinal, so it is excluded — filtered on
  the **entity**, never on the fact, so it cannot be confused with the temporal death AC1 tests.
  `permanently_deleted_at` too. This is T1's guard extended to the new read and the unit twin of
  QC-4's *"absent from composition's cast read"*; stated because the plan did not ask for it.

  **Found in passing, NOT caused by this change:** `go test ./internal/...` in glossary-service reports
  ~30 failures that vanish under `-p 1`. Go runs packages concurrently and the `api` and `migrate`
  suites share **one** `GLOSSARY_TEST_DB_URL` database, so they migrate each other mid-run. Measured
  at HEAD with T5's files moved out: **31 failures**, same command, same fresh DB. CI is unaffected —
  `domain-db-smoke.yml` runs `./internal/api/...` alone, which is **0 failures** with T5 in place.
  Recorded rather than fixed: it is a test-harness defect in a package this plan does not otherwise
  touch, and inventing a per-package DB here would be scope drift.

- [x] **T6** — Expose `state@as_of` on the KAL — **GREEN**
  `contracts/api/knowledge-gateway/kal.v1.yaml` + `services/knowledge-gateway/src/kal/kal-read.controller.ts`
  **Gateway carries no logic** (decision B2): validate, authorize, forward. `temporal_capability`
  is reported by the service, not computed here.
  **Logging:** `DEBUG` inbound `as_of` + downstream latency.
  (depends on T5)
  ---
  **Evidence.** `GET /v1/kal/books/{book_id}/state?as_of=N` — one controller method, plus the path
  and two schemas (`StateEntity`, `StateFact`) in the contract. Full gateway suite **22/22 PASS**,
  `tsc --noEmit` clean, and both INV-KAL gates still green:
  ```
  [knowledge-access-gate] PASS — no direct EAV/Neo4j reads outside the owning services
  [knowledge-http-surface-gate] PASS — no consumer hits the owning services' bi-temporal /internal endpoints
  ```
  **The required-`as_of` rule is NOT re-implemented here**, and that is the design decision worth
  recording. The gateway forwards whatever arrived and lets glossary refuse; `downstream.ts` already
  propagates a 4xx faithfully, so the caller still sees `400`. A TypeScript copy of the rule would be
  a second owner of a domain constraint inside the layer B2 says carries none — and two owners drift.
  The test proves the difference rather than assuming it: it asserts the 400 **and** that the request
  actually reached the service (`fetchMock` called once), which a short-circuiting gateway would fail.

  **Three bites, each reverted:**

  | change | goes red as |
  |---|---|
  | `Array.isArray(...) ? ... : []` → `?? []` | a downstream object keyed by entity id passes through as the bounded array |
  | gateway throws its own `400` on a missing `as_of` | the request never reaches the service — the rule now has two owners |
  | drop `temporal_capability` | a consumer cannot tell "no facts here" from "this source ignored `as_of`" |

  ⚠️ **Note for T26:** this adds a **fourth** call site of `temporalCapability()` in the gateway.
  T26 moves that function into the Python use-case layer; it now has one more site to move. Included
  deliberately — every other temporal read on this contract carries the field, and a state read that
  omitted it would be the odd one out for a reason no consumer could see.

- [x] **T7** — Migrate composition's cast read off `roster` — **GREEN**
  `services/composition-service/app/clients/kal_client.py` · `app/deps.py:300` · the planner/packer
  call sites
  `roster` survives as what it honestly is — an untimed catalogue enumeration.
  **Logging:** `INFO` the story position each drafting run resolves; `WARN` if a caller reaches the
  cast read without one.
  (depends on T6)
  ---
  **Evidence.** `KalClient.state(book_id, as_of=…)` + `cast_from_state` (`engine/heal_canon.py`) +
  `_canon_cast_at` (`routers/plan.py`), wired into the **two canon-bible reads**: self-heal-propose
  and quality-report. 14 new tests, **3619 passing** across the composition suite.

  ⚠️ **The task said "the cast read"; there are 13, and they do not all want the same thing.**
  Migrating them wholesale would have been wrong. The split, decided per call site and written into
  `_cast_roster`'s docstring so the next reader inherits the reasoning rather than re-deriving it:

  | callers | read | why |
  |---|---|---|
  | canon bible (self-heal, quality-report) | **`state@as_of`** | a bible is a claim about what is true AT the chapter being written |
  | `present_entity` commit validation · motif-swap + role-rebind binding targets | `roster` | an entity introduced in ch.50 is a valid binding target while planning ch.10 — gating membership on a position rejects valid ids for not being born yet |
  | bound-motif label resolution | `roster` | a display name, not a canon claim |
  | `/decompose`'s cast | `roster` | the plan spans the book; no single position exists to read it at |

  **The position is the chapter's `sort_order`**, resolved through `book.get_chapter_sort_orders` —
  the same axis `valid_from_ordinal` is written on. Verified rather than assumed: the extractor
  sources `chapter_ordinal` from book-service's `sort_order`
  (`extraction_worker.py:1006`), after a job-relative index was measured colliding — *"index 0 named
  SIX different chapters"*. Passing a list index here would have answered confidently about a
  different chapter.

  **A second defect surfaced and is fixed by the same change.** `render_canon` renders
  `role` / `personality` / `relationships` / `description`, but `roster` is projection-restricted to
  **id+name by contract** — so those branches were **dead code** and every canon bible ever rendered
  was a bare list of names. `state@as_of` carries facts, so the bible now says what each character
  *was* at that chapter. Asserted directly:
  `assert "protagonist" not in render_canon([{"entity_id": …, "name": …}])` — the roster-shaped cast
  the old path produced.

  **Four bites, each reverted:**

  | change | goes red as |
  |---|---|
  | canon path back to `_cast_roster` | `state` never called; the bible is untimed again |
  | client drops `as_of` from the query | the position is not on the wire — the service would 400 in production while any response-only assertion still passed |
  | flatten only `name` (the pre-T7 shape) | role/description vanish from the bible |
  | accept a non-list `entities` | (first attempt did **not** bite — the per-row `isinstance` filter already returned `[]`, so the guard's only real contribution is the WARN. The test now asserts the log line, and it bites) |

  **Degradation, stated:** an unresolvable position falls back to the untimed roster and `WARN`s
  (`NO resolved story position`); a KAL outage returns `[]` and leaves the run ungrounded, as before.
  A `400` is logged separately from an outage — it means composition asked wrongly, and burying it in
  the outage bucket would hide a caller bug as an infrastructure blip.

- [x] **T53** — Migrate the *other* roster consumers — **RESOLVED: both stay untimed, documented**
  *(added by `/aif-improve +check`)*
  `services/lore-enrichment-service/app/clients/kal.py:131` (drained for the cast hint at
  `app/compose/compose_task.py:569`) · `frontend/src/features/knowledge-temporal/api.ts:82`
  T7 migrates composition only; these two keep reading **the union of every entity that ever
  existed, with no story position** — so the defect this plan exists to fix survives on the
  enrichment and knowledge-temporal surfaces.
  **Either** migrate them onto `state@as_of`, **or** document per consumer why it legitimately
  wants the untimed catalogue. Silence is not an answer here.
  **Logging:** `INFO` the resolved position per consumer; `WARN` where an untimed read is kept
  deliberately, naming the reason.
  (depends on T6)
  ---
  **Evidence.** Both consumers examined; **neither is migrated, and both now say why in code.**
  The task allowed either answer but forbade silence, so this is the answer, not a skip.

  **`lore-enrichment-service`** drains the roster to hint an intent RESOLVER — the user typed free
  text and we are deciding *which entity they meant*. An entity introduced in chapter 50 is a valid
  enrichment target while the reader sits at chapter 10, so filtering candidates by position would
  make the resolver fail to find things the user can see in their own glossary. It asks what
  **exists**, not what is **true** — the opposite of the canon bible T7 moved.

  ⚠️ **The frontend half's premise was wrong, and checking beat assuming.** T53 asserted
  `features/knowledge-temporal/api.ts:82` *"keeps reading the union of every entity that ever
  existed"*. It has **zero call sites** in `frontend/src` (`grep -rn "\.roster(" frontend/src` →
  nothing): it is client surface mirroring the KAL contract, not a live read, so no user reaches the
  defect through it. Documented in place; `state` is deliberately **not** added there until something
  calls it — T51 owns the frontend migration, and an unused wrapper is how a client drifts from the
  contract it claims to mirror.

  Suites after the change: lore-enrichment **1263 passed**, frontend `tsc --noEmit` clean.

- [x] **T8** — Measure `state@as_of` end-to-end, doc-21 style — **GREEN, no stop condition fires**
  New: [`docs/measurements/2026-08-09-state-asof-ceiling.md`](../measurements/2026-08-09-state-asof-ceiling.md)
  Rig stated · durability stated · **ratios not absolutes** · with a bite. Compare in-process vs
  through-the-KAL and **publish the ratio** — this is the gate the design named as most likely to
  invalidate it. Baseline already measured: **8.7 ms flat** at 26k facts.
  (depends on T7)
  ---
  **Evidence.** Rebuilt images, real dev corpus (**48 492 facts / 11 books**; the book measured is
  the largest at **26 192 facts over 1 673 entities**, chapters 0–97), 20 reads per surface.

  | surface | p50 | p95 |
  |---|---|---|
  | in-process (`glossary /internal/.../state`) | 34.8 ms | 43.4 ms |
  | through the KAL | 51.0 ms | 67.6 ms |
  | **ratio** | **×1.47** | **×1.56** |

  A second run measured ×1.62 / ×1.65 — **×1.5 ± 0.1** is this rig's resolution. **Stop condition 1
  does not fire:** the cast resolves once per chapter, against LLM calls measured in seconds — 51 ms
  is 0.25 % of a 20-second generation.

  **The plan is `Index Scan + Sort`, which hands T9 its before-picture and its bite:** the book index
  carries `book_id` only, so **17 254 of 26 192 rows are read and discarded** by the as-of filter, and
  the `DISTINCT ON` sorts **1 213 kB** (quicksort) — a sort that grows with book length and spills
  `work_mem` at T10's ceiling.
  **And an honest reading of AC2 on real data:** 8 938 rows in → 8 914 out. Only **24** rows are
  collapsed — so overlapping intervals are *rare but real*, and `DISTINCT ON` is what stands between
  a caller and two contradictory values on 24 attributes. (T5's first bite already showed a synthetic
  disjoint fixture cannot demonstrate this.)

  ⚠️ **Finding, recorded not fixed:** the consumer receives **1 674 entities → 1 463 canon bible
  rows** on the real book. T7 did not change that *count* (`roster` drained the same 1 674) but did
  widen each row. **No cap was added deliberately** — truncating the cast to the first N is a silent
  correctness change dressed as a perf fix, and *which* cast members matter for a chapter is a
  salience question this task has no business answering. The context-budget law owns that ceiling.

- [x] **QC-1** — Contract review + consumer live smoke — **`passed=9 failed=0`**
  New: `scripts/state-asof-live-smoke.sh`
  `/aif-review +check`. Then drive `state@as_of` **through the KAL from composition** against a real
  book — not through a test client. **A new cross-service contract is proven by its consumer**, and
  the gateway hop is exactly what a unit test omits.
  **Data:** capture p50/p95 and the resolved position for 20 consecutive chapter reads; paste into
  the plan.
  ---
  **② Live proof — `scripts/state-asof-live-smoke.sh`, `passed=9 failed=0`.** Images rebuilt from the
  working tree first (glossary-service · knowledge-gateway · composition-service), against real
  Postgres and the real gateway. Scratch entity minted and purged by the script's own trap; ordinals
  9000+ so they cannot collide with real chapter positions in a shared dev book.

  | leg | result |
  |---|---|
  | AC1 `as_of=9039` through the KAL | **alive** — present and living one chapter before the death |
  | AC1 `as_of=9040` | **dead** — the half-open boundary holds end-to-end |
  | AC2 `rank` at 9030 | exactly **one** value (`inner`) |
  | AC2 **unclosed chain** (two open intervals on one attribute) | collapses to the freshest (`Ash`), not two contradictory values |
  | REQ no `as_of` / negative `as_of` through the KAL | **400** both — the service's rule, forwarded, not re-implemented |
  | CONS composition's own `KalClient.state()` in the composition container | saw the entity; `rank=inner` (the as-of value, **not** the head) |
  | CONS `cast_from_state` on live data | **1 463** bible rows — the canon path is genuinely grounded, not silently empty |

  **Why this is not vacuous:** every leg but one could pass against a stubbed read. The AC1 pair
  cannot — an endpoint ignoring `as_of` returns the head value at *both* positions and fails the
  first leg. That pair is what makes the rest mean something.

  ⚠️ **The harness produced two false REDs on its first run and was fixed, not explained away.**
  `life_status='alive', want 'alive'` — Windows Python writes CRLF, so the value compared as
  `alive\r`. A harness that fails between two identical-looking strings is worse than one that fails
  loudly: it reads as a product bug. `values_for` now strips `\r`, with the reason on the line.

  **① Code review of the Commit-2 diff.** Performed at this checkpoint over the full diff
  (11 modified + 6 new files). Findings, all fixed in the same slice rather than deferred:

  | # | finding | disposition |
  |---|---|---|
  | 1 | **AC2's fixture could not exercise `DISTINCT ON`** — three disjoint intervals; deleting it left the file green | fixed: a sixth test seeds an unclosed chain (T5) |
  | 2 | **The non-list `entities` guard had no bite** — the per-row `isinstance` filter already returned `[]`, so the guard's only contribution is its WARN | fixed: the test now asserts the log line (T7) |
  | 3 | **`state` silently violated the KAL's own "bounded by construction" invariant** — the preamble carves out `roster` and `list_attr_values` explicitly; a third unbounded shape slipping in without a carve-out is how an invariant rots into a comment | fixed: the preamble now carves out `state`, states that it is bounded by the POSITION not a page, and says why paging it would be worse (a drained snapshot is torn) |
  | 4 | **The smoke reported two false REDs** (Windows CRLF) | fixed with the reason on the line |
  | 5 | **Completeness check on T7:** `grep -rn "render_canon" services/` → exactly 2 non-test call sites, both migrated. The worker path receives the canon in its payload, so it inherits the as-of bible rather than rebuilding one from `roster` | verified, no action |

  Not found: no SQL built by concatenation (both new queries are parameterized), no new tenancy
  surface (the route sits behind `requireInternalToken` like every sibling `/internal` read, and
  user auth stays at the gateway's `KalAuthGuard`), no new secret in a tracked file.

  **③ Real-run data:** the PERF block above *is* real-run data — 40 reads against a 26 192-fact book
  on the deployed binaries, plus the query plan in the measurement doc.

<!-- Commit checkpoint: T4–T8 — contract boundary -->

- [x] **T9** — Covering index for the book-wide as-of read (**D9**) ✅
  New migration in `services/glossary-service/internal/migrate/`
  `(book_id, entity_id, attr_or_predicate, valid_from_ordinal DESC) WHERE invalidated_at IS NULL AND cardinality='single'`
  Removes the sort. Today's plan is `idx_entity_facts_book` (**128 lifetime scans**) + quicksort,
  which grows linearly with book length and spills `work_mem`.
  ⚠️ **Two constraints, both concrete** *(added by `/aif-improve +check`)*:
  **(a)** Ship as a **NEW ledger chain step** — never an edit to an existing one.
  `migrate.go:231`: *"shipped as a NEW ledger step (0052) — NOT edited"*; editing one breaks
  already-migrated databases.
  **(b)** The runner wraps every step in `pool.Begin` + `pg_advisory_xact_lock`
  (`migrate.go:303,308`), so **`CREATE INDEX CONCURRENTLY` cannot run in that path at all** —
  and a plain build takes a write lock on a table this plan projects to ~1.08 M rows per book.
  **Resolve the conflict in this task, not at migration time:** either an out-of-band concurrent
  build with a ledger step that only verifies presence, or an accepted maintenance window with
  the lock duration measured first.
  **Bite:** drop the index → the plan must return to `Sort`.
  ---
  **Evidence.** Shipped as `0062_entity_facts_asof_index` (new ledger step, nothing edited).
  Measurements: [`docs/measurements/2026-08-09-state-asof-ceiling.md`](../measurements/2026-08-09-state-asof-ceiling.md) §R-4/R-5.

  ⚠️ **DEVIATION FROM THE PLAN, with evidence — this task's stated rationale was wrong in both
  halves, and shipping it literally would have been a 140 MB index that misses its own goal.**

  1. *"The sort grows linearly with book length and spills work_mem."* It does not. At one
     position exactly one interval per (entity, attribute) can match, so the sort input is
     **cast size × attributes**, not chapter count — measured **2 175 kB at 108 k facts and
     2 175 kB at 1.08 M facts**. (It can still spill on a book with a very large *cast*; that
     is a different axis and would need a different fix.)
  2. *"Removes the sort."* The key-only index does not. The read joins `glossary_entities`
     for the recycle-bin filter, and a join above the scan destroys the index ordering — the
     `Sort` survives whichever index is chosen. Forcing an ordered path (`enable_sort=off`)
     produces one at **12× the buffers**, which is why the planner declines it.

  The real cost is the **heap**: ~558 k random fetches for `value`/`fact_kind`. So the shipped
  index adds `INCLUDE (valid_to_eff, value, fact_kind)`, making the scan **index-only**
  (`Heap Fetches: 0`). Five runs, median, at the ceiling:

  | index | median | size | plan |
  |---|---|---|---|
  | none | 281.1 ms | — | `Index Scan` + `Sort` |
  | the plan's literal definition | 197.6 ms | 140 MB | `Index Scan` + **`Sort` still there** |
  | **shipped** (+ `INCLUDE`) | **74.1 ms** | 216 MB | `Index Only Scan`, 0 heap fetches |

  **The `CONCURRENTLY` conflict, resolved here as the task demands:** the step takes the
  write-blocking build, measured at **2.4–2.8 s on 2.16 M facts** (CONCURRENTLY was 3.2 s — it
  is not faster, only non-blocking). Reads are unaffected; only writes to `entity_facts` queue,
  for under three seconds at ~45× the current corpus. An operator who cannot accept that builds
  the index CONCURRENTLY out of band **before** upgrading and `IF NOT EXISTS` makes the step a
  no-op. That route is deliberately not the default: a migration depending on someone
  remembering a manual step is one that silently does not exist wherever they forgot.

  **Five bites, each reverted:** `INCLUDE` loses `value`/`fact_kind` · the index stops being
  partial · `valid_from_ordinal` loses `DESC` · `CONCURRENTLY` appears in the SQL (it would
  fail at *migration* time on a real deployment, not in CI) · the step is not registered in the
  chain (it would then exist only on fresh databases).
  ⚠️ The CONCURRENTLY guard **matched its own explanation** on first run — the doc comment
  necessarily contains the string it forbids. The test now reads the SQL literal, not the file.

- [x] **T10** — Synthetic 4,000-chapter ceiling run — **GREEN, the ceiling is not a ceiling**
  New: `scripts/perf/state-asof-ceiling.sh`, throwaway DB only
  ~1.08 M facts. **Must not touch a real service DB** (`EnsureThrowawayDB`).
  (depends on T9)
  ---
  **Evidence.** The script builds its own database (name must carry a throwaway marker — the
  same rule `testsafe.EnsureThrowawayDB` enforces in Go), applies the **real chain** so the index
  under test is the shipped one, seeds 1 500 entities × 12 attributes × 60 revisions on one book
  (**1.08 M facts, ordinals 0–3 960**) plus 9 decoy books, and drops the database on exit.

  **`state@as_of` survives a 4 000-chapter book: 65–87 ms, with or without the index.** The read
  returns ~18 000 facts at *any* position regardless of book length — only one interval per
  (entity, attribute) can cover a given ordinal. Book length grows the rows **scanned**, never
  the rows **returned**.

  ⚠️ **The ceiling rig has a pathology worth naming, and it changes T9's verdict twice.** Its
  target book is **53 % of the whole table**, so scanning everything costs ~2× the necessary
  work — and there the seq scan *beats* the index. Real databases hold every book on the
  deployment. Both shapes, same rig:

  | shape | with index | without | verdict |
  |---|---|---|---|
  | **a normal book — 108 k facts, 5 % of a 2.05 M-row table** | **16.2 ms** | 50.2 ms | **index wins ×3.1** |
  | one 4 000-chapter book at 53 % of the table | 87.3 ms | 64.8 ms | seq scan wins ×1.35 |

  Ship it: row two is the rig's artifact, not a deployment shape, and its 22 ms cost is against a
  34 ms win in row one that **grows with the number of books**. A database holding essentially
  one enormous book is exactly where a sequential scan is near-optimal anyway.

  **Three harness defects found and fixed, all of which produced *plausible* numbers:** a
  scan-node regex that could not match an index name (`[a-z ]*` excludes `_` and digits); a
  missing `VACUUM` after the bulk seed, leaving the visibility map unset so an `Index Only Scan`
  was unavailable; and a **40 % bloated index** (301 MB vs 205 MB rebuilt) because the chain
  creates it empty and the rig then grows it through a 2 M-row insert landing in seconds — the
  rig now `REINDEX`es and says why. The script refuses to print a ratio unless the planner
  actually chose the index, because a ratio between one plan and itself is host noise wearing a
  decimal point.

<!-- Commit checkpoint: T9–T10 — migration -->

### Phase 2 · The ports *(sliced — each ships alone, per RT-12)*

- [x] **T11** — Pull Cypher out of the selectors — **GREEN, and it was hiding a tenancy bypass**
  `services/knowledge-service/app/context/selectors/salience.py`
  Nothing can be abstracted while Cypher lives in a selector.
  **Logging:** `DEBUG` the repo call replacing each inline query.
  ---
  **Evidence.** One Cypher block, moved to `app/db/neo4j_repos/entities.py`
  (`load_promotion_signals` + `PromotionSignals`); the selector is now scoring only.
  Knowledge unit suite **4005 passed**.

  ⚠️ **Not a tidy-up.** The selector called `session.run(...)` **directly**, so it never passed
  through `run_read` and its Cypher **never carried `$user_id`** — the bypass
  `neo4j_repos/__init__.py` calls *"the single highest-severity bug class in this service."* It
  matched on `project_id` alone. Routing it through `run_read` adds the owner filter every
  sibling read already has, plus `archived_at IS NULL` — an archived entity must not receive a
  promotion boost, because the boost is a **re-ranking** and ranking it above a live entity is
  exactly what budget-trim then protects. Both are tightening: an entity missing from the result
  just gets no boost, and both salience weights default to `0.0`.

  **Four bites, each verified to actually apply** (see the warning below), each red then green:
  the tenant filter is dropped (the original query) · archived entities are promoted again ·
  empty input still hits the driver · naive timestamps are no longer made aware.

  ⚠️ **Three bites silently did NOT apply on the first attempt, and read as "the guard is
  redundant".** `perl -0pi` patterns containing `\n` no-match against this file's **CRLF** line
  endings. That is the worst possible failure for a bite — a no-op mutation looks exactly like a
  guard with no teeth, and the honest-looking conclusion is to delete the guard. The bites now run
  through a helper that **exits non-zero if the pattern is absent**, so "the test still passes"
  can only mean what it says.

- [x] **T12** — Pull Cypher out of event handlers and extraction — **GREEN, and it found a bug**
  `app/events/handlers.py` · `app/extraction/coref_detect.py` · `app/extraction/glossary_passage.py`
  (depends on T11)
  ---
  **Evidence.** All three files are now Cypher-free. Knowledge unit suite **4005 passed**.

  | site | moved to | what it was |
  |---|---|---|
  | `handlers.py` chapter-delete cascade | `neo4j_repos/provenance.delete_source_cascade` | direct `session.run` **write** — and wrong (below) |
  | `glossary_passage.py::_current_hash` | `neo4j_repos/passages.get_passage_content_hash` | direct `session.run` read; had `$user_id`, so a relocation |
  | `coref_detect.py` two loaders | new `neo4j_repos/coref.py` | already via `run_read`; pure relocation |

  🐞 **The handler's inline Cypher was a real defect, and moving it is what exposed it.** It ran a
  bare detach-delete on the `ExtractionSource`, which drops the `EVIDENCED_BY` edges **without
  decrementing the `evidence_count` those edges maintain**. So every entity, event and fact the
  chapter evidenced kept an inflated counter: it stayed visible to the `evidence_count >= 1`
  reads — **the chapter's canon survived its own deletion** — and could never reach zero for
  `cleanup_zero_evidence_nodes` to collect. Only the offline K11.9 reconciler repaired it,
  whenever it next ran. The **sibling `chapter.kg_excluded` handler already retracted properly**,
  so deleting a chapter (the stronger action) was doing strictly less than excluding it. Fixed by
  calling `delete_source_cascade`, which resolves the natural key, decrements each edge, then
  deletes the node.
  **Test + bite:** `test_chapter_deleted_decrements_evidence_instead_of_bare_detach_delete` — it
  asserts the repo call's arguments **and** that the handler ran no Cypher of its own (a handler
  keeping its own query alongside the repo call would satisfy every other assertion while leaving
  the counters wrong). Reverting to the bare delete goes red.

  ⚠️ **A comment nearly armed a future gate against itself:** the explanation of what was replaced
  originally quoted the Cypher it removed, which T16's `no-cypher-outside-adapters` gate would
  match. Reworded to describe rather than quote.

- [x] **T13** — Pull Cypher out of `db/neo4j_helpers.py` — **GREEN, the guard module is clean**
  Index creation and schema helpers move behind the port that will own them.
  (depends on T12)
  ---
  **Evidence.** `neo4j_helpers.py` went **356 → 181 lines** and now contains **zero** Cypher.
  It is the multi-tenant *guard* — `assert_user_id_param`, `run_read`, `run_write` — and holding
  index DDL made the one module whose job is to police queries also the one place a query was
  expected. Two new repo modules, seven importers repointed, knowledge unit suite **4008 passed**.

  | moved | to | why there |
  |---|---|---|
  | `summary_index_name` · `parse_summary_index_name` · `list_summary_vector_indexes` · `drop_summary_index` · `ensure_summary_indexes` | `neo4j_repos/vector_indexes.py` | this is **T14's `VectorStore` surface** (`ensure_index` / `drop_index` + the naming that pairs them) — isolating it now makes T14 a wrapping, not a rewrite |
  | `purge_project` | `neo4j_repos/project_graph.py` | not an index concern and not a passage concern; it is the whole-project teardown a project delete owes the graph |

  **Two `$user_id`-free surfaces, each documented rather than "fixed":**
  - The index ops are **admin DDL** — `SHOW`/`CREATE`/`DROP INDEX` have no rows, so no tenant to
    filter, and `run_read`/`run_write` would rightly reject them. Tenancy is **structural**: the
    name embeds the project + model UUIDs, and every name reaching `DROP` is validated by
    `parse_summary_index_name` first. Cypher has no parameter form for index names, so that
    validation is also the injection barrier.
  - `purge_project` matches on `project_id` alone, and **must**. Its only caller is gated by
    `require_project_grant(OWNER)` and has already completed the authoritative Postgres delete.
    Adding a user filter would be actively wrong: a node written under a different owner id in a
    shared project would survive the purge and orphan the graph — the exact defect
    (`D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`) the function exists to close.

  **Guard + bite.** `test_neo4j_helpers_contains_no_cypher` walks the module's AST and inspects
  **string constants with docstrings excluded** — this module's prose necessarily quotes Cypher
  (`assert_user_id_param`'s docstring demonstrates literal-injection on purpose), so a plain grep
  reports the explanation as the violation. Both halves bite: putting a query constant back goes
  red, and **dropping the docstring exclusion also goes red**.
  ⚠️ That second bite did **not** fire at first — the verb list omitted `CREATE (`, the very verb
  the docstring uses, so the exclusion was decorative. Adding it made the guard broader *and* the
  exclusion load-bearing. A positive-control test pins the AST walk itself, so a filter that
  silently swallowed everything cannot report "no Cypher" forever.

  ⚠️ **Stated gap — this slice did NOT make the service Cypher-free.** T11–T13 named five files
  and cleared them. **16 files outside `app/db/` still carry Cypher**: `extraction/glossary_sync.py`
  · `extraction/hierarchy_writer.py` · 6 under `jobs/` · 5 under `routers/` · `tools/kg_unify.py` ·
  `benchmark/runner.py`. That is **T17's** sweep ("migrate the 67 modules"), gated by **T16**'s
  `no-cypher-outside-adapters` check. Recorded here so nobody reads Commit 4 as the end of the job.

<!-- Commit checkpoint: T11–T13 -->

- [x] **T14** — Define `VectorStore` + its fake — **GREEN**
  New: `app/ports/vector_store.py`, `app/adapters/neo4j_vector_store.py`, `app/adapters/fake_vector_store.py`
  `search(scope, embedding, k, filter)` · `upsert` · `ensure_index` · `drop_index`. Adapter is
  existing code lifted **byte-for-byte**.
  **Logging:** `DEBUG` scope, dim, k, filter cardinality, elapsed.
  ---
  **Evidence.** Port + two implementations + 13 contract tests; knowledge suite **4021 passed**.

  **"Lifted byte-for-byte" read as DELEGATION, not duplication.** The adapter calls the existing
  `neo4j_repos` functions rather than copying their Cypher — a byte-for-byte copy would be two
  places to fix a tenant filter, which is precisely the failure `neo4j_repos` and its
  `run_read`/`run_write` guards exist to prevent.
  ⚠️ **That has a consequence T16 must absorb:** `app/db/neo4j_repos/` **is** adapter territory,
  so the `no-cypher-outside-adapters` gate must allow it as well as `app/adapters/`, or T17 must
  move the repos under `app/adapters/neo4j/`. Written into `app/adapters/__init__.py` — a gate
  that quietly allowlists a directory nobody remembers deciding on is how an invariant becomes a
  formality.

  **Three deliberate deviations from the sketched signature, each because the sketch would have
  made the port lie:**
  - **`upsert` takes a typed union, not one common shape.** Passages (18 fields, chunked,
    canon-flagged) and entity embeddings (a write onto an existing node) are genuinely different;
    their intersection is `(id, embedding, dim, model)`, which drops `canon`, `chunk_index`,
    `source_lang`, `content_hash`. Those come back as kwargs the moment the adapter needs them,
    and the abstraction leaks on day one.
  - **`weighted_score` is not returned.** `find_entities_by_vector` computes
    `raw_score * anchor_score`; that weighting is domain policy. The port returns `raw_score` plus
    the anchor value and lets the caller decide — a backend that had to reproduce a scoring
    formula to be swappable is not swappable.
  - **`oversample_factor` is not on the port.** Over-fetch-then-filter compensates for Neo4j's
    index being unable to filter by tenant. pgvector filters in the planner (T23) and would have
    to accept a meaningless parameter. It lives in the adapter.

  **The fake computes real cosine similarity and enforces the rules, not the signatures.** It is
  about to carry the ~561 tests that skip without a live Neo4j (T20), and a fake that has drifted
  is *worse* than the skip it replaces — a skip is visible in the output. So it enforces tenant
  scoping, the dim/index-family split, `False`-on-missing-entity, replace-on-re-embed, and
  index-name validation on drop. It reuses the **real** name builder, so a name it mints survives
  the real parser.

  **Six bites, each verified to mutate the file first, each red then green:** cosine replaced by a
  constant (insertion order wins) · the fake ignores `user_id` · it ignores the dim family · drafts
  stop being excluded by default · `drop_index` accepts any name · the Neo4j adapter renames `k`
  to `top_k`.

  ⚠️ **`isinstance(x, VectorStore)` proves almost nothing** and both implementations pass it
  trivially: a `runtime_checkable` Protocol checks method **names** only. An adapter whose `search`
  took `top_k` would satisfy it and fail at the call site. So conformance is asserted by comparing
  **signatures** — names, kinds and defaults — for both implementations, with a positive control
  proving that comparison can fail.

- [x] **T15** — Define `OntologyStore` + its fake *(smallest — proves the pattern)* — **GREEN**
  New: `app/ports/ontology_store.py` + adapters. 2.5k LOC, low blast radius.
  (depends on T14)
  ---
  **Evidence.** Port + `PostgresOntologyStore` + `FakeOntologyStore` + 14 contract tests;
  knowledge suite **4035 passed**.

  **It proves the pattern on a DIFFERENT backend, which is the point.** `VectorStore` fronts
  Neo4j; this fronts Postgres (`kg_graph_schemas`). Had both fronted Neo4j, "the pattern works"
  would have been a claim about Neo4j rather than about the pattern.

  ⚠️ **Scope: READS only, and that is not a half-measure.** Ontology writes are effects
  (`adopt_effect` · `schema_edit_effect` · `sync_effect` · `triage_schema_write_effect`), each
  with its own transaction, confirm-token and optimistic-concurrency semantics — KM6 compares
  `(schema_id, schema_version)` at confirm time to detect drift since mint. Porting those means
  porting the transaction model, and the port would have to expose a connection to keep them
  atomic, which is the abstraction failing out loud. The reads are what every consumer outside
  `app/ontology/` uses — resolver, routers, MCP server, extraction — and none of them needs a
  database after this.

  **The rules under test are VISIBILITY rules,** because a store that returned another user's
  `user`-tier template satisfies every signature and still leaks across tenants. Two behaviours
  the fake copies deliberately: *not-visible and not-found both return `None`* (if invisible
  raised, a caller could enumerate another tenant's schema ids by watching which ones raise), and
  *`resolve_for_project` never returns `None`* (a project with no ontology still has to extract
  something — the fallback is contract, not convenience).

  **Seven bites, each red then green:** every user's templates become visible · a project schema
  leaks without naming the project · invisible raises instead of reading as absent · deprecated
  templates appear in the picker · another user's template becomes adoptable · the
  empty-resolution `WARN` goes silent · the Postgres adapter drops a keyword.

  ⚠️ **A test of mine was wrong and the fake was right:** `ORDER BY scope, code` is **alphabetical
  by scope**, so `project` sorts before `system` — it looks like a tier order at a glance and is
  not. Now asserted explicitly, so a consumer reading position 0 as "most specific" finds out
  here rather than in a prompt.

- [x] **T16** — The `no-cypher-outside-adapters` gate — **GREEN, and it found what T11 missed**
  New: `scripts/graph-port-gate.py`; wire into pre-commit + `foundation-ci.yml`
  No `MATCH (` / `MERGE (` / `CREATE (` outside `app/adapters/`.
  **Bite:** delete the adapter package → gate must go red.
  (depends on T15)
  ---
  **Evidence.** `[graph-port-gate] PASS — 289 file(s) scanned outside adapter dirs; 21 baselined`.
  Wired staged-scoped into `.githooks/pre-commit` and repo-wide into `foundation-ci.yml` (a stale
  baseline entry is only detectable against the whole tree).

  🐞 **On its first run the gate caught a selector T11 missed.**
  `context/selectors/summary_blend.py` runs `CALL db.index.vector.queryNodes` through a direct
  `session.run`. T11's brief was *"pull Cypher out of the selectors"* and I cleared `salience.py`
  alone — because the search that scoped the task grepped for `MATCH`/`MERGE`/`CREATE`, and this
  query opens with none of them. **A hand-written search decided the scope of a task; the gate
  decided it correctly.** Moved to `neo4j_repos/vector_indexes.py::query_summary_index`, with the
  level weighting left in the selector (that is blending policy, not storage).

  ⚠️ **Its first finding was also a FALSE POSITIVE, and that mattered more than the true one.**
  `CREATE INDEX` and `CREATE CONSTRAINT` are SQL as well as Cypher, so the gate reported
  `app/db/migrate.py` — the **Postgres** DDL blob — as a graph violation. Both tokens are gone;
  `CREATE VECTOR INDEX` stays because only Cypher has it. A gate whose first finding is wrong is a
  gate people learn to skip.

  **It parses, it does not grep.** Only string CONSTANTS are examined, with docstrings excluded —
  prose about Cypher is not Cypher, and that false positive has already bitten this refactor twice
  (T9's `CONCURRENTLY` guard matched its own comment; T13's guard matched a docstring
  demonstrating injection).

  **The baseline is a ratchet, not a hiding place.** 21 files still carry Cypher, so "clean or
  fail" would have meant not shipping the gate. It ships with an **explicit per-FILE** baseline —
  a new file in a listed directory fails — and **a baseline entry with nothing left to excuse is
  itself an error**, so a cleaned file cannot keep standing permission and silently re-grant it
  later. T17's job is to delete entries.

  **Adapter territory is `app/adapters/` AND `app/db/neo4j_repos/`**, decided in T14 and written
  in three places (the gate, `app/adapters/__init__.py`, this plan): the repos package *is* the
  Neo4j implementation, and the adapters delegate to it rather than copying its Cypher.

  **Four bites, each red then green:** new Cypher in a non-adapter file · a cleaned file left on
  the baseline · the docstring exclusion removed (prose reported as violation) · the adapter dirs
  stop counting as adapters.

- [~] **T17** — Migrate the 67 modules to the two shipped ports — **IN PROGRESS: 6 of 21 cleared**
  **Logging:** `DEBUG` adapter selection at construction; `INFO` the bound adapter at startup.
  (depends on T16)
  ---
  **Evidence (batch 1).** Gate baseline **21 → 15**. Six runtime paths moved into adapter
  territory; knowledge suite **4040 passed**; 5 bites, each red then green.

  | file | query moved to |
  |---|---|
  | `jobs/orphan_extraction_source_cleanup.py` | new `neo4j_repos/maintenance.py` |
  | `jobs/quarantine_cleanup.py` | ″ (keeping its deliberate `run_write` bypass — the one caller that legitimately passes `user_id=None`) |
  | `jobs/stats_updater.py` | ″ (`count_nodes_by_label` + the closed label tuple) |
  | `jobs/reconcile_evidence_count.py` | ″ (`reconcile_evidence_count_for_label`) |
  | `routers/internal_admin.py` | ″ (`clear_embedding_model_tag`) |
  | `jobs/regenerate_summaries.py` | `neo4j_repos/passages.py::recent_passage_texts` |

  **The scheduling stayed in `jobs/`** — retry policy, metrics, loop-until-zero, *"do not run
  concurrently with extraction"*. Those are operational decisions, not storage.

  🐞 **One move was NOT just a move, and the test exists because of it.** `regenerate_summaries`
  carried **two near-identical queries** differing only in the project predicate — and only one of
  them had been updated when the source-type filter was added. They are one query now, with the
  branch in Cypher. The naive collapse
  (`$project_id IS NULL OR p.project_id = $project_id`) is true for **every** passage when the
  scope is global, so a global summary would be built from every project's passages — the
  cross-contamination KSA §7.6 rule 5 exists to prevent, and it would read as a slightly-too-good
  summary rather than a bug. Asserted directly, and the naive form is asserted **absent**.

  ⚠️ **I guessed a closed set wrong and checking caught it.** Moving the reconciler I wrote
  `RECONCILE_LABELS = ("Entity", "Fact", "Event", "EntityStatus")` from memory; the real set is
  `("Entity", "Event", "Fact")` — Relations and EntityStatus are excluded because they carry no
  `evidence_count`. Reconciling a fourth label would have written a counter onto nodes that never
  had one, and nothing would have failed loudly. Both closed sets are now pinned by a test.

  ⚠️ **Three test files needed their seam repointed, and that is the honest cost of a move:**
  `monkeypatch.setattr("app.jobs.….run_write")` patches nothing once the query lives in the repo.
  Repointed to `app.db.neo4j_repos.maintenance.run_write` with the reason on the line.

  **Batch 2 (2026-08-10).** Gate baseline **15 → 12**: `tools/kg_unify.py` (bulk entity detail by
  id → entities repo), `routers/public/entities.py` (the C17 alias-collision pre-check → entities
  repo), `benchmark/runner.py` (passage count by source type → passages repo). Unit suite **4079**.

  ⚠️ **Two bites failed to fire, for two DIFFERENT reasons, and both mattered.**
  - The `IN` → `=` bite on the moved passage count reported "mutation applied" and the suite stayed
    green — because `passages.py` now contains **two** queries with that exact line, and the bite
    replaced the first, which was a different query. Same first-match trap as T18's as-of clause,
    caught this time because the bite was expected to bite. Redone by line offset inside the named
    template.
  - The alias-collision bite found **no test at all**: the exclusion of the two merge participants
    was only ever exercised against a live graph. Without those clauses the pre-check finds the
    source colliding with the target and refuses **every** merge with a 409 blaming a non-existent
    third entity. Now guarded.

  **A pre-existing regression lock moved WITH its query rather than being deleted with it:**
  `test_real_passage_count_cypher_has_safety_clauses` pinned the `IN`-not-`=` typo on a literal that
  no other test reads. It follows the query into `passages.py` and still bites.

  **Batch 3 (2026-08-10).** Gate baseline **12 → 9**: `extraction/hierarchy_writer.py` (the
  Book→Part→Chapter→Scene MERGE → new `neo4j_repos/hierarchy.py`),
  `extraction/glossary_sync.py` (the glossary→KG anchor MERGE → entities repo),
  `routers/public/graph_views.py` (both graph-browse reads → new `neo4j_repos/graph_views.py`).
  Unit suite **4079**.

  ⚠️ **`graph_views.py` had a SECOND consumer** — `tools/graph_schema_tools.py` imported both
  Cypher templates from the *router*, which is the coupling the port work exists to remove: an MCP
  tool reaching into an HTTP router for a query string. Both now call the repo.

  **Three decisions preserved rather than tidied away**, each recorded where it now lives:
  - the graph-view **as-of filter stays in PYTHON** (`edge_visible_at`), not in the Cypher — it is
    pure and unit-testable there, and pushing it down would trade a tested predicate for an
    untestable one;
  - `hierarchy.py`'s MERGE **carries no `$user_id` and must not** — it merges on `path`, the key
    the schema constraint enforces, and adding a filter would make the MERGE key disagree with the
    uniqueness constraint and start minting duplicates;
  - it also **must not open a transaction** (D2a: the caller runs it in the same tx as the pass-2
    writer, so a repo function that helpfully wrapped itself would silently break atomicity).

  ⚠️ **A seam CHANGED SHAPE, not just address.** `run_read` + `_records` collapsed into one repo
  call that returns rows. The over-fetch tests (`limit+1` sentinel → `meta.truncated`) patched
  `run_read`; left alone they would have patched nothing and the over-fetch assertion — their whole
  point — would have silently stopped being checked. Repointed, and re-bitten to prove the
  assertion still fires through the new seam.

  **Batch 4 (2026-08-10).** Gate baseline **9 → 8**: `routers/internal_enrichment.py` — five
  statements (write-back anchor, per-fact upsert, promote, retract) into a new
  `neo4j_repos/enrichment.py`. Unit suite **4085**.

  🔒 **The safety properties of enrichment live in the Cypher, and NOTHING asserted them.** The
  existing tests covered id derivation and confidence validation — the Python half. The half that
  decides whether an AI write-back can corrupt canon was exercised only against a live graph, which
  meant almost never. Six guards added, five bitten:

  | invariant | what its absence does |
  |---|---|
  | `ON MATCH` never touches a canon anchor's `source_type`/`confidence`/`origin` | an enrichment write-back **relabels a genuine canon node as enriched**, and the marker is what a reviewer trusts |
  | `ON CREATE` marks the node (`origin`, `pending_validation`, proposal id) | an enrichment-created node is **indistinguishable from canon** |
  | the stale-anchor free excludes `stale.id <> $canon_id` | it strips the glossary anchor off the very node about to claim it, and the MERGE then creates a **second** one |
  | retract is SOFT (`valid_until`, never `DELETE`) | unrecoverable |
  | retract is scoped to one proposal's `origin` + id | **it takes canon with it** |
  | every statement carries `$user_id` | none of these go through `run_write` — the anchor MERGE keys on `id`, so `$user_id` is a property rather than a filter and `assert_user_id_param` would pass for the wrong reason |

  That last row is why the guard exists at all: the usual tenancy check is structurally unable to
  help here, so the assertion had to be written by hand or not exist.

  **Batch 5 (2026-08-10).** Gate baseline **8 → 6**: `jobs/summary_processor.py` (seven
  Book/Part/Chapter traversals + the summary write → `neo4j_repos/hierarchy.py`) and
  `routers/public/extraction.py` (the project-delete-by-label loop and the graph-stats read →
  `neo4j_repos/maintenance.py`). Unit suite **4088**.

  **Every runtime path is now Cypher-free. The 6 files left are ALL `db/migrations/` backfills** —
  admin one-shots reachable through `internal_backfill.py`. They are deliberately last, and Phase 7
  must **port or retire** them: they run against whatever engine is bound, so an engine swap breaks
  them silently.

  🔒 **Two reasons-for-a-shape moved with their code rather than being left behind**, both of which
  are the kind that get lost in a refactor:
  - `PROJECT_GRAPH_LABELS` excludes `:Passage` **on purpose** — it holds chat- and glossary-sourced
    chunks extraction cannot rebuild, so a plain delete/rebuild must leave them alone while a model
    CHANGE must purge them through a separate flag. Both change-model paths once *documented*
    themselves as already doing this and **neither did**; proven live on 2026-07-23 when a
    `:Passage` node was the only survivor of that loop. The guard followed the constant.
  - `write_summary_to_node` interpolates the node label from the level, so the closed `Level`
    literal is the injection barrier — re-checked in the repo rather than trusted from a caller's
    type annotation.

  ⚠️ **Two closed-set guards had no test, again** — removing them left 4085 tests green. Same
  finding as batch 1, in two new places: a guard that is the *injection barrier* is exactly the kind
  nothing exercises, because the happy path never touches it. Both now bitten.

  ⚠️ **This paragraph was STALE and said so with a longer list than the truth** *(corrected
  2026-08-10)*. It named `glossary_sync.py`, `hierarchy_writer.py`, `summary_processor.py`,
  `internal_enrichment.py`, `routers/public/{entities,extraction,graph_views}.py`, `kg_unify.py`
  and `benchmark/runner.py` as still owed — **batches 2–5 cleared every one of them** and nobody
  trimmed the list. A completeness list that over-states what is left is not the safe direction
  it looks like: it hides the *real* remainder inside noise, and the next reader prices the task
  by the list rather than by the gate. The gate is the authority; it reads **6**:

  ```
  $ python scripts/graph-port-gate.py
  [graph-port-gate] PASS — 296 file(s) scanned outside adapter dirs;
                    6 baselined file(s) still carry Cypher (T17 shrinks that list)
  ```

  ### 🔻 DEFERRAL `D-T17-BACKFILL-CYPHER` — the last 6 files, tracked to Phase 7

  | | |
  |---|---|
  | **Blocker** | The 6 remaining files are `db/migrations/` backfills whose Cypher is *graph traversal and truth*, which belong to **T18 (`GraphStore`)** / **T19 (`TruthStore`)** — neither of the two ports T17 was scoped to migrate onto covers them. Moving them onto `neo4j_repos/` would be motion, not progress: they would have to move again at the engine swap. |
  | **Evidence** | `scripts/graph-port-gate.py` baseline, lines 93–98: `backfill_entity_alias_map.py`, `backfill_event_date.py`, `backfill_orders.py`, `backfill_participant_anchors.py`, `backfill_status.py`, `recanon_honorifics.py`. Gate output pasted above. |
  | **To unblock** | A second `GraphStore` adapter must exist, so "port or retire" is a decision with two real options rather than one. That is **T42**. |
  | **Mechanism** | The gate's baseline list *is* the tracker — it is asserted, not documented: any 7th file fails the gate, and removing an entry without porting the file fails it too. Wired into pre-commit and `foundation-ci.yml`, so the count cannot drift unnoticed between now and Phase 7. |
  | **Retry when** | T42 lands a second `GraphStore` adapter. **These are admin one-shots that run against whatever engine is bound, so an engine swap breaks them silently** — porting or retiring them is a precondition of QC-7's rebuild drill, not a follow-up to it. |

  T17 therefore stays `[~]` on purpose: its runtime scope is **complete** (every runtime path is
  Cypher-free), and the residue is a named, gated, Phase-7-owned list rather than an open end.

<!-- Commit checkpoint: T14–T17 -->

- [x] **T18** — Define `GraphStore` + its fake — **GREEN**
  Domain operations, not Cypher: `resolve_or_merge_entity` · `find_entities_by_name` ·
  `neighborhood(entity, depth, filters)` · `relations_for(entity, as_of)` · `status_at_order` ·
  `events_in_window(after, before, axis)` · `archive_entity`/`restore_entity` · `upsert_relation`.
  (depends on T17)
  ---
  **Evidence.** Port + `Neo4jGraphStore` + `FakeGraphStore` + 16 contract tests; knowledge suite
  **4056 passed**; 6 bites, each verified to mutate the file, each red then green.

  🔨 **`relations_for(entity, as_of)` did not exist and now does.** The sketch asked for it, and
  checking before encoding it was the right call: the substrate **does** support it — `Relation`
  carries the F3 `valid_from_ordinal`/`valid_to_ordinal` and `temporal.AS_OF_ORDINAL_PREDICATE` is
  the LOCKED shared fragment — but **no relation read applied it**; they all read the HEAD. So the
  clause was added to all three 1-hop templates, **additively**: omit `as_of` and the read is
  byte-identical to before. Putting `as_of` on a port whose data could not answer it would be the
  lie `temporal_capability` already exists to report; adding it where only the query was missing is
  the port doing its job.
  **The edge case is the interesting half:** a POSITIONLESS edge (`valid_from_ordinal IS NULL` —
  legacy data) is **excluded** by an as-of read. Cypher gets that free from three-valued logic;
  Python does not, so the fake says it explicitly and a test pins it.

  ⚠️ **`events_in_window(…, axis)` — there are THREE axes, not two.** `narrative` (authored
  `event_order`), `chronological` (in-story, undated events sink last) and `date` (parsed
  `event_date_iso`). The repo already distinguishes them; collapsing them into one "time"
  parameter would leave a caller unable to ask the one it means. A test shows the same two events
  ordering differently on two of them.

  ⚠️ **Two sketch parameters were wrong and reality won.** `upsert_relation` has **no
  `project_id`** (an edge inherits scope from its endpoints; a third source of truth for the same
  fact is the one most likely to disagree) and takes **singular `source_event_id`** — the plural
  lives on the READ, where later events accumulate onto the arc. `RelationDirection` is
  `outgoing`/`incoming`/`both`, not `out`/`in`.

  **`list_events_filtered` returns `(rows, total_count)` and the port drops the count** — it exists
  for a paginated browse ("page 3 of N"), and this port asks for a window. Keeping it would force
  every implementation to have a cheap count.

  ⚠️ **The fake set two fields the real models do not have** (`archived_reason` for
  `archive_reason`; a missing required `canonical_title` on `Event`) — caught immediately by
  building against the real Pydantic models rather than dicts. That is exactly the drift a fake is
  supposed to avoid, and it would have surfaced as a mystery in T20's 561 tests.

  ⚠️ **One bite did not bite, and the fix was to the TEST.** "resolve mints a duplicate" left the
  suite green: matching ids and a count of one both survive a fake that builds a fresh object and
  stores it at the same key. The test now asserts **source types accumulate**, which can only hold
  if the existing entity was returned and updated. Idempotency asserted, not assumed.

  **Deliberately NOT on the port:** subgraph/ego reads, motif and thread writes, causal-edge
  merges. Every method here must be implemented twice in Phase 7 and faked once; a port grows by
  demand, and T42 building the second adapter is the forcing function that says which of them
  belong.

- [x] **T19** — Define `TruthStore` + its fake — **GREEN**
  Two adapters from the start — `GlossaryTruthAdapter` (book-scoped authored facts) and
  `MemoryTruthAdapter` (project/global) — routed by scope. Consumers never learn which answered.
  (depends on T18)
  ---
  **Evidence.** Port + **four** implementations (`GlossaryTruthAdapter`, `MemoryTruthAdapter`,
  `ScopedTruthStore` router, `FakeTruthStore`) + 15 contract tests; knowledge suite **4071 passed**;
  6 bites, each verified to mutate, each red then green. Both INV-KAL gates still pass.

  **`ScopedTruthStore` is the thing consumers hold, and that is the whole task.** Phase 8 (T44–T46)
  merges the two stores — the Go bitemporal machinery moves to Python and the HTTP hop disappears —
  so any consumer holding a concrete adapter would be a rewrite. The router dispatches on the
  `scope` ARGUMENT, never on "is `book_id` set?": inference breaks the first time a project read
  carries a book id for logging, and **a misroute is silent** because the wrong store still returns
  well-formed facts. A test passes a `book_id` to a project read and asserts it still goes to
  memory.

  ⚠️ **`TruthFact` deliberately drops store-specific fields** (`canonical_content`,
  `pending_validation`, `coverage_xid`). A consumer that touched one would be pinned to that store.
  The renames live in the adapters: glossary's `attr_or_predicate` and memory's `(type, content)`
  both become `(attribute, value)` exactly once.

  🔀 **The two axes are the design risk, and they are made LOUD rather than smoothed.** Book truth
  is positioned on story ordinals, memory truth on wall clock — the plan names this as the one
  piece of Phase 8 that must be *designed* (T45). So `as_of` is `int | datetime` and **the wrong
  one raises**: Python compares two ints or two datetimes happily, so a mixed axis does not crash,
  it returns a confidently wrong set of facts. Both directions are asserted, on both adapters and
  the fake. The interval rule is identical on both axes (`valid_from <= as_of < valid_to`) so T45
  inherits one convention to reconcile, not two.

  ⚠️ **`GlossaryTruthAdapter.search_facts` raises `NotImplementedError` instead of returning `[]`.**
  glossary exposes no free-text fact search — its fact routes are keyed by entity. An empty list
  would be indistinguishable from *"this book has no matching facts"*, so a caller would conclude
  the book is empty when the **capability** is absent. That is the silent-success failure this repo
  keeps recording, so it fails loudly and names the alternative.

  ⚠️ **A new cross-service read, and the exemption it leans on is stated.** knowledge-service reads
  glossary's `/internal/…/facts` directly. It cannot go through the KAL — the gateway calls
  knowledge-service, so that would be a cycle — and `knowledge-http-surface-gate.py` already exempts
  `services/knowledge-service/`. Recorded in the adapter's docstring because leaning on an exemption
  without saying so is how an invariant quietly stops meaning anything. The hop is **temporary by
  design**: Phase 8 removes it.

  **Six bites:** scope isolation removed · the interval end made inclusive · an unpositioned fact
  leaking into an as-of read · the axis guard removed · the router inferring the store from
  `book_id` · glossary search returning `[]` instead of raising.

- [x] **T20** — Retire the 561 skips that needed a live Neo4j — **GREEN: 67 → 338 passing**
  `services/knowledge-service/tests/` — repoint at the fakes; make `-n auto` safe.
  **This is the port's first user-visible win.**
  (depends on T19)
  ---
  **Evidence.** `tests/integration/db`: **67 passed / 554 skipped → 338 passed / 283 skipped,
  0 failed.** Unit suite **4078 passed**. Three real defects found, all mine, all fixed.

  ⚠️ **The task's premise was wrong in two ways, and both had to be checked before acting.**

  **(1) They are not all Neo4j.** Measured: **272 Neo4j skips, 282 POSTGRES skips.** Repointing
  the Postgres half at a graph fake would have done nothing at all. The remaining 283 skips are
  that Postgres half — a separate `TEST_KNOWLEDGE_DB_URL` job, not this one.

  **(2) "Repoint at the fakes" would have DESTROYED coverage, not won it.** All 24 Neo4j-gated
  files are **repository tests** — `test_relations_repo`, `test_entities_repo`, `test_facts_repo`,
  `test_provenance_repo`, `test_neo4j_schema`… They verify the CYPHER against a real database.
  Pointing them at `FakeGraphStore` replaces *"does this query do what we think"* with *"does our
  fake do what we wrote it to do"* — the fake grading itself — and it would delete the ground
  truth **QC-2's adapter-parity proof compares against**. So the fakes stay where they belong
  (unit tests, and the consumer paths T17 is migrating), and these tests were made to **RUN**.

  That is the real win, and it is this repo's own lore: *env-gated tests skip and the green suite
  lies.* 554 tests silently skipping is the defect; 338 running is the fix.

  🔒 **The Neo4j fixture had NO throwaway guard** — the Postgres one has refused a non-throwaway
  DSN since the `kg-integration-tests-truncate-shared-dev-db` incident. Anyone setting
  `TEST_NEO4J_URI` to the dev graph would have had 272 tests creating and `DETACH DELETE`-ing
  nodes in real books. Closed: Neo4j Community has no multi-database, so "throwaway" cannot be a
  database *name* here — the equivalent is a dedicated instance, so the fixture refuses the dev
  stack's published ports (7687/7688) with an explicit `TEST_NEO4J_ALLOW_SHARED=1` escape hatch
  for CI. Verified by pointing it at 7688 and watching it refuse.

  🐞 **Three defects, all introduced by my own T17/T18 work, none caught by the unit suite:**

  | # | defect | how it hid |
  |---|---|---|
  | 1 | **T17 dropped `evidence_count_drift_fixed_total.inc(fixed)`** when the reconciler query moved | nothing unit-tested the metric, so the suite stayed green while the only signal saying whether the sweeper finds anything silently stopped moving |
  | 2 | **T18's as-of clause landed in `_EGO_HOP_STEP`**, which never binds `$as_of_ordinal` | loud (`ParameterMissing`) — but only against a live Neo4j, which nothing was running |
  | 3 | **T18's clause MISSED the outgoing/incoming templates, and covered only one UNION branch of `both`** | not loud at all: `relations_for(direction="outgoing", as_of=40)` returned a plausible answer that **ignored the position entirely**, and `both` filtered half its edges |

  Defect 3 is the one worth remembering. I verified the mutation *applied* — the lesson from T11 —
  but not that it applied **only where intended**. "The pattern exists" and "the pattern exists in
  exactly these three places" are different claims, and a blanket `str.replace` proves the first.

  **The guard is source-level and needs no database:** `test_relations_as_of_templates.py` asserts
  each 1-hop template applies the clause (so a read cannot accept `as_of` and ignore it), that the
  `both` template applies it to **each** UNION branch, and that the queries which never bind the
  parameter never reference it. All three defects would have failed it.

- [x] **QC-2** — Adapter-parity live proof — **GREEN, and it found drift on its first run**
  `/aif-review +check`. Then run the **same** context-assembly request against the Neo4j adapter and
  the fake, on a live stack, and diff the rendered block byte-for-byte.
  **Why:** the fake is about to carry 561 tests. If it drifts from the real adapter, every one of
  those tests becomes a lie — the exact failure the skips were hiding.
  ---
  **② Live proof — `tests/integration/db/test_graph_adapter_parity.py`, 10 tests, all green**
  against a throwaway Neo4j (`docker run … -p 7999:7687 neo4j:5-community`). Integration suite
  **348 passed**, unit **4078 passed**.

  ⚠️ **T20 changed this task's premise and made it MORE load-bearing, not less.** QC-2 assumed the
  fakes would carry ~561 tests. T20 measured that and rejected it — the Neo4j-gated tests verify
  Cypher, so repointing them at a fake is the fake grading itself. The consequence is that **this
  file is now the fakes' only check.** Nothing else compares `FakeGraphStore` to `Neo4jGraphStore`.

  **It is a port-level diff, not a rendered-block diff, and that is a deliberate downgrade.** The
  task said "the same context-assembly request … diff the rendered block byte-for-byte", but no
  consumer holds a port yet (T17 has 15 files left), so there is no assembly path that goes through
  one. Diffing the port surface is what is available and what actually protects the fakes; the
  rendered-block diff belongs after T17 finishes and is recorded as owed, not quietly dropped.

  🐞 **Three real divergences, found on the first run.** `FakeGraphStore.resolve_or_merge_entity`
  was returning a well-formed entity that simply **was not the one the real store produces**:

  | field | real | fake (before) |
  |---|---|---|
  | `aliases` | seeded `[name]` on create, accumulates the name on match unless `user_edited` | `[]`, never accumulated |
  | `version` | `coalesce(version,1) + 1` on every match | stuck at 1 |
  | `confidence` | HIGH-WATER MARK (`WHEN $confidence > e.confidence`) | unasserted — see below |

  Every unit test touching aliases or version had been agreeing with the fake. Fixed by copying the
  `ON CREATE` / `ON MATCH` semantics from the real MERGE rather than guessing them.

  ⚠️ **A fourth "divergence" was mine, not the fake's:** I mirrored `provenances`, which the Cypher
  writes but the `Entity` **model does not carry** — so it never crosses the boundary. Mirroring it
  would have been inventing state the real store's own RETURN cannot produce. Removed.

  **Five bites, each verified to mutate the fake, each turning parity RED:** aliases no longer
  seeded · version no longer bumped · confidence stops being a high-water mark · the as-of end
  bound drifts to inclusive in the fake only · positionless edges leak in the fake only.

  ⚠️ **The confidence bite did not bite at first** — no parity test re-resolved at a *lower*
  confidence, so the high-water rule was unasserted on **both** sides. A test was added rather than
  the guard accepted as redundant; that is now the third time in this plan that a failed bite found
  a missing assertion instead of a redundant guard.

  **Non-vacuity:** a sync guard test at the bottom of the file SKIPS WITH A LOUD REASON when
  `TEST_NEO4J_URI` is unset — a parity suite that silently skips reports the same green as one that
  passes, which is the exact failure QC-2 exists to prevent.

<!-- Commit checkpoint: T18–T20 -->

### Phase 3 · Vector layer to Postgres *(S1 — the only hard ceiling)*

`summary_index_name(project, model, level)` → ~30,000 HNSW indexes at 10k projects; ~63 M passage
vectors ≈ 390–780 GB. And **D2 needs as-of-filtered semantic search**, which is impossible while
vectors and validity intervals live in different stores.

- [x] **T21** — Verify pgvectorscale dims > 2000 (**gate**) — **GREEN: no ceiling, T22 unblocked**
  `SUPPORTED_PASSAGE_DIMS = (384, 1024, 1536, 2560, 3072)`. pgvector HNSW caps at 2000 (`vector`) /
  4000 (`halfvec`); StreamingDiskANN's ceiling is undocumented. **Blocks T22.**
  ---
  **Evidence.** [`docs/measurements/2026-08-10-pgvectorscale-dimension-ceiling.md`](../measurements/2026-08-10-pgvectorscale-dimension-ceiling.md).
  Throwaway `timescale/timescaledb-ha:pg17` container — PG **17.10**, pgvector **0.8.6**,
  pgvectorscale **0.9.0**.

  **Stop condition 2 does NOT fire.** All five supported dimensions index with
  StreamingDiskANN, including the two HNSW cannot take. At 3072 with real data: 2 000 rows,
  **2.0 s** build, 1 808 kB, the planner **chooses** the index (`Index Scan using f3072_dann …
  Order By: emb <=> …`), and the nearest neighbour of row 42 **is** row 42.

  ⚠️ **The answer is stronger than "≥3072".** Pushing upward: 4000 OK, 8000 OK, 16000 OK, and
  `vector(16001)` is rejected by the TYPE. **StreamingDiskANN has no dimension ceiling of its
  own** — pgvector's 16 000-dim type limit is the only one, five times the largest dimension in
  the closed set. That turns "no problem in our range" into "there is no index-side limit to run
  into", which is what T22 needs to commit.

  **The positive control is what makes that mean anything:** pgvector's HNSW was run at the same
  dimensions and failed at 2560/3072 with the exact documented message, at exactly the documented
  2000 boundary. A harness that reports OK for everything reports OK for a broken backend too.

  ⚠️ **Its first run reported FAIL for all five** — it treated any stderr output as failure and
  `DROP TABLE IF EXISTS` emits a `NOTICE`. Now keys on the exit code with `ON_ERROR_STOP=1`. A
  gate whose first run is a false negative is a gate people learn to argue with.

  ⚠️ **Tested on PG17 while the design targets PG18** — the readily available image bundling
  pgvectorscale is PG17, and the design's own M1 note records PG18 support (`--pg18 pg_config`).
  A dimension ceiling is a property of the extension's index implementation rather than the server
  version, so the result carries; stated rather than glossed, because "I tested what you're
  shipping" and "I tested a close relative" are different claims.

  **Consequence for T24:** `halfvec` is **not needed for reach**. It is a recall-vs-storage trade
  to be measured, not a workaround for a cap — so T24 is free to reject it, rather than owing its
  recall cost as the price of indexing 3072 at all.

- [x] **T22** — Build and publish the Postgres image (**decision T5**) — **GREEN, +2 MB**
  New: `infra/postgres-knowledge/Dockerfile` — PG18 + pgvector + pgvectorscale
  Self-hosters must not compile extensions; that would destroy the operability argument for leaving
  Neo4j. **You own this distribution's CVE cadence.**
  (depends on T21)
  ---
  **Evidence.** `loreweave/postgres-knowledge:18` — **PostgreSQL 18.4**, pgvector **0.8.6**,
  pgvectorscale **0.9.0**. `scripts/postgres-knowledge-image-smoke.sh` **passed=5 failed=0**.

  🎯 **The operability cost is far lower than the design feared, because pgvectorscale ships
  PREBUILT PG18 packages.** Checked before committing to a route: 0.9.0 publishes `pg18` assets for
  **both amd64 and arm64**. So there is no Rust/pgrx toolchain in the build and no compiler in the
  shipped layer — the image is **631 MB against a 629 MB base: +2 MB**. The M4 risk was that a
  self-hoster's `docker compose up` becomes a compile; it does not.
  **The CVE obligation is real and unchanged**, and is stated at the top of the Dockerfile: three
  version-pinned parts that must be re-pinned and re-tested on every advisory touching any of them.

  ⚠️ **Bookworm, not Alpine — a deliberate divergence from the dev stack's `postgres:18-alpine`.**
  pgvectorscale ships glibc binaries; musl would mean compiling the very thing this image exists to
  spare people.

  ✅ **T21's PG17 caveat is discharged here.** That gate was measured on PG17 (the only readily
  available image bundling pgvectorscale). All five `SUPPORTED_PASSAGE_DIMS` now index on **PG18**,
  on the image we actually ship — the citation became a build, exactly as T21 said it must.

  🐞 **The build-time verification caught a real failure on its FIRST run.** The Dockerfile assumed
  the release ZIP held loose `.so`/`.control` files; it holds **`.deb` packages**. The `find`
  matched nothing, installed nothing, and — because the `test -f` guards were there — the build
  FAILED instead of shipping an image that looks fine until someone runs `CREATE EXTENSION`. That
  is the exact silent failure the guards were written for.

  **The smoke does not check that files exist — it USES the image:** extensions load · all five
  dims index (incl. the 2560/3072 HNSW refuses) · a 3072-dim index over 500 real rows · the planner
  **chooses** it · the nearest neighbour of row 42 **is** row 42. That last one matters most: an
  index that builds and is chosen but returns wrong neighbours is worse than one that fails, because
  nothing complains.

  **Bitten with a genuinely broken image** (pgvector only, no pgvectorscale — the shape the first
  build produced): `passed=1 failed=9`, **exit 1**; the good image exits 0. Note the one PASS —
  "nearest neighbour is row 42" holds without any index at all, via a sequential scan. That is
  correct and is why the planner assertion is a separate check: correctness and index-usage are
  different questions and a single test cannot answer both.

  **`infra/docker-compose.knowledge-pg.yml` is a LAYER, not part of the default stack.** It joins
  at T25 with the Neo4j vector indexes dropped in the same change — adding a second Postgres to
  everyone's `up` before anything reads from it costs 600 MB for nothing and, worse, would look
  like the cutover had happened. Its healthcheck asks for the **extension**, not just `pg_isready`:
  an image that starts without pgvectorscale is not healthy for this purpose.

- [x] **T23** — `PgVectorStore` adapter ✅
  `services/knowledge-service/app/adapters/pg_vector_store.py`, 8 unit + 15 live tests, **4115
  green**. Per-dim tables from the closed `SUPPORTED_PASSAGE_DIMS` set — and that is *structural*,
  not a choice: `vector(n)` is a typed column, so one table cannot hold 384 and 3072. The closed
  set is therefore the injection barrier for the interpolated relation name, the same role it
  already plays for the Cypher property name in `passages.py`.

  **The planner property is PROVED, not asserted.** "The tenant filter reaches the planner" is a
  claim about a query plan; reading the SQL cannot settle it, and a test that EXPLAINed its own
  re-typed query would pass after the real one changed. So `build_search_sql` was extracted and the
  test EXPLAINs *that* statement. On 4 000 rows across two tenants:

  ```
  scan=Index Scan  index=passage_vectors_384_emb  rows_out=10  removed_by_filter=5
  ```

  One scan node, the diskann index serving the ordering, and `user_id` evaluated **on that node** —
  15 rows read to return 10. `Neo4jVectorStore` fetches 100 for the same answer.

  **Bitten five times, each one fired.** (A) drop `user_id = $1` → the cross-tenant test *and* the
  plan test go red. (B) over-fetch 10× and filter above the scan — the Neo4j shape — → **the
  cross-tenant test stays GREEN** and only the plan test catches it, which is exactly why the plan
  test exists: the wasteful shape returns correct results. (C) report cosine *distance* as the
  score → ordering stays right, only the explicit `score ≈ 1.0` assertion fires. (D) let the entity
  path guess. (E) answer entity search anyway.

  **Two defects found in review, same shape: a narrowing filter that silently does not narrow.**
  `search(scope="entity")` was ignoring `include_archived` (whose DEFAULT `False` means *exclude
  archived* — Neo4j runs a different query for it) and `project_id` (which `EntityVectorRecord`
  does not even carry, so the write path cannot store what the read path filters on — a **T14 port
  gap**). Answering anyway would have widened every entity result set **at the cutover**, green all
  the way. It now refuses with a named owner. Entity *upsert* works, so T24 has rows to measure.

  **The entity-existence oracle is a constructor argument.** The port's `False` return means "the
  entity was deleted between embedding and write". Neo4j can answer that because the node and its
  embedding are the same object; here the embedding row is the only object and an `INSERT` always
  succeeds. Returning `True` would satisfy the signature while dropping the guarantee, so the
  composition root passes `entity_exists` and without it entity writes raise — the same refusal
  `TruthStore` (T19) makes for a capability it does not have.

  **Divergence from the port's index lifecycle, recorded rather than smoothed over.**
  `ensure_index` is documented as returning `{level: name}` for chapter/part/book. That shape is
  Neo4j's per-project *summary* index model, and it describes neither half of this backend:
  summary vectors are a third family the port never modelled (`search`/`upsert` take
  `passage | entity`, while the index methods address `summary_embedding`), and there is no
  per-project index here **on purpose** — minting one would rebuild the ~30 000-index scheme the
  port's own docstring cites as the reason to move. So it returns `{scope: name}` over the shared
  per-dim indexes, and **every name it mints is unparseable by `parse_summary_index_name`**. That
  is load-bearing, not cosmetic: the prune-orphans admin path decides what to drop by parsing a
  project out of an index name, so an unparseable name is what stops it offering to drop an index
  serving every tenant. On this backend orphans are **rows, not indexes**. Unit-tested with a
  positive control, because a parser that returned `None` for everything would pass it silently.

  **`query_rescore`** (StreamingDiskANN's recall knob) is a constructor argument for the same
  reason `oversample_factor` never reached the port, and it applies `SET LOCAL` **inside an
  explicit transaction** — bare on a pooled connection it warns and does nothing, and plain `SET`
  would leak into the next borrower. **Unmeasured: T24 owns it.**

- [x] **T24** — Dual-write + shadow-read, with a recall gate ✅
  `app/adapters/dual_write_vector_store.py` (15 tests) · `app/benchmark/vector_backend_bench.py` ·
  **4132 green**. Full evidence: [`docs/measurements/2026-08-10-vector-backend-recall.md`](../measurements/2026-08-10-vector-backend-recall.md).

  **The headline is a correctness bug, not a benchmark.** StreamingDiskANN's SERVER DEFAULTS return
  **recall@10 = 0.715** on the real passage corpus — three of ten neighbours missing, from a search
  that reports success. At `search_list=300, rescore=200` the same corpus returns **1.000**, and it
  is not slower (4.66 ms vs 5.97 ms p50). T23 wired `query_rescore`, left the value to the server
  and called it an optimisation; it is the difference between correct results and quietly wrong
  ones. `PgVectorStore` now sets **both** knobs — `query_search_list_size` did not exist on it —
  from measured defaults. ⚠️ Measured at 181 rows; **QC-3 must re-measure at scale.**

  **The comparison the plan specified cannot be built.** The opclass catalogue says
  `diskann → vector_cosine_ops | vector_ip_ops | vector_l2_ops` and nothing else:
  **pgvectorscale 0.9.0 has no `halfvec` operator class for diskann.** Run naively (halfvec on
  HNSW, `vector` on diskann) the number would have blamed fp16 for a difference between two index
  ALGORITHMS. The cells were refactored to isolate one variable each, and a `halfvec_exact` cell
  added — no index on either side, so the only difference is 16-bit storage.

  **The bite fires, in that cell.** `halfvec_exact` **0.9950** (worst query **0.9000**) vs `exact`
  **1.0000** at 10k × 1024, for **49 % less storage**. On the 181-row real corpus halfvec loses
  nothing — which locates the cost rather than contradicting it: fp16 only scrambles orderings whose
  margin is below its rounding error. halfvec stays **rejected for the default path**, documented as
  available, and nothing in Phase 3 depends on it.

  **The first numbers were the harness.** Every backend scored 0.2–0.7 — a devastating-looking
  verdict on pgvector, and wrong. The queries were uniform random, and in 1024 dimensions a random
  query is near-orthogonal to the whole corpus, so its true top-10 is ten near-ties separated by
  float noise; no index can reproduce an ordering that is itself arbitrary. Queries are now drawn
  from the corpus distribution. The random corpus is kept and **labelled a floor, not a verdict.**

  **A defect in T23's own test helper.** `_seed_two_tenants` used an uncorrelated subquery under a
  comment claiming `random()`'s volatility made it per-row. It does not — an uncorrelated subquery
  is hoisted into an InitPlan and evaluated once: `count(*) = 3000`, `count(DISTINCT embedding) = 1`.
  T23's planner assertions survive (plan shape does not depend on the data; the evidence line now
  reads `removed_by_filter=10`), but any recall test on that helper would have measured nothing
  while looking healthy. Fixed, and **the helper now asserts its own output is distinct.**

  **Dual-write asymmetry:** writes go to both, reads come from the primary only — a read served from
  a half-populated secondary is a correctness regression bought for nothing. A secondary write
  failure is swallowed (it must not fail a user request) **and counted**:
  `vector_dual_write_total{outcome="secondary_failed"}` **must read zero before T25** — that counter
  is the deferral's mechanism, not a runbook sentence. A PRIMARY failure propagates. Shadow reads
  are off by default, sampled, inline (a `create_task` would measure a load the request never saw),
  and report **overlap, not recall** — neither backend is ground truth, so calling it recall would
  assert the primary is correct, which is the thing being measured.

  **Bite F took two attempts.** The first version asserted `SET LOCAL` behaviour on its own
  connection; deleting the transaction from `search()` left it green, because it was testing
  Postgres rather than the adapter. It now goes through `search()` and compares a starved store
  against a generous one — if the setting never arrives both silently get the server default and
  their answers become identical.
  (depends on T23)

- [~] **T25** — Cut over; drop the Neo4j vector indexes; **build the vector backup path**
  **Backup path DONE and drilled. The cutover is BLOCKED, and not by anything T25 can fix.**

  **① The backup path ✅** — [`scripts/vector-backup-drill.sh`](../../scripts/vector-backup-drill.sh),
  evidence in [`docs/measurements/2026-08-10-vector-restore-drill.md`](../measurements/2026-08-10-vector-restore-drill.md).
  It destroys the table and gets it back rather than checking that a file exists; the destroy step
  is what makes the rest mean anything, and the bite (replace `pg_restore` with `true`) gives
  `passed=2 failed=4`, exit 1.

  **The restore is sound and it does not restore the answers.** Every vector returns byte-identical
  and the exact nearest-neighbour query is unchanged, but at 20 000 rows the rebuilt ANN index
  returns a **different top-10 (overlap 7/10)** — `pg_restore` rebuilds the graph rather than
  copying it. Data recovery and *result* recovery are different guarantees; only the first is
  promised, and post-restore recall is an open question every time.

  **The index rebuild IS the recovery time:** 34.3 s of a 35.3 s restore at 20 000 rows (97 %).
  ⚠️ **Not extrapolable.** `diskann.min_vectors_for_parallel_build = 65536`, and both measurements
  sit below it, so both were single-threaded. **QC-3 owes a rebuild measurement above 65 536
  vectors; until then there is no defensible RTO.**

  **② The cutover ⛔ and ③ dropping the Neo4j indexes ⛔.** Measured, not assumed:
  `grep` for constructors of `PgVectorStore` / `Neo4jVectorStore` / `DualWriteVectorStore` outside
  `app/adapters/` returns **nothing**. The live semantic read path still calls
  `find_passages_by_vector` directly from `context/selectors/passages.py`, `routers/public/drawers.py`
  and `search/retriever.py`. **Nothing holds a `VectorStore`, so there is nothing to cut over** —
  and dropping the Neo4j vector indexes today would simply break semantic search.

  **This is a gap in the plan, not a slip in the work.** Phase 3 goes T22 build the image → T23
  write the adapter → T24 dual-write → T25 cut over, and **no task ever wires the port into the
  read path.** The plan half-knows this: line 1340 already notes "no consumer holds a port yet…
  there is no assembly path that goes through". T24's dual-write store is likewise composed by
  nobody, which means `vector_dual_write_total{outcome="secondary_failed"}` — the cutover gate — is
  structurally stuck at zero because no write reaches it. **A gate that reads zero because nothing
  is wired looks exactly like a gate that reads zero because nothing failed.** That is the most
  dangerous shape in this whole phase and it must not be read as a pass.

  (depends on T24)

- [x] **T25a** — The composition root Phase 3 never had ✅ *(added after T25 measured the gap)*
  `app/adapters/vector_store_provider.py`; **4135 green**.

  **Writes are wired; reads are not — and that IS dual-write.** Write both, read the primary,
  compare. The three vector write sites (`passage_ingester`, `glossary_passage`,
  `entity_embedder`) now go through `VectorStore`. Swapping reads is the cutover itself and
  cannot honestly happen until the secondary has been fed for a while.

  **The gate can now move, and a test makes it move.**
  `tests/integration/db/test_vector_dual_write_live.py` asserts with `SELECT`s against a real
  Postgres, not mock call counts, because the entire failure mode is "the secondary is never
  reached" and only the secondary's own database can testify to that. One test deliberately
  drives `secondary_failed` up — a counter that cannot be made to move is not a gate.
  **Bite:** delete the secondary write → two of the three go red.

  **Default-off, and off means byte-identical.** With `KNOWLEDGE_VECTOR_DB_URL` unset the factory
  returns a plain `Neo4jVectorStore` — same repo calls, one method deeper. No second database, no
  new failure mode; turning the migration on is an explicit act of configuration.

  **The composition root supplies the entity-existence oracle** that `PgVectorStore` refused to
  guess at (T23), asking Neo4j through the *user-scoped* `get_entity` rather than
  `get_entity_by_id_any_owner` — an any-owner read would let one tenant's write be authorised by
  another's row. It is the only layer that can see both stores, which is exactly why the oracle
  belongs here.

  **Test seam:** `tests/unit/_vector_seam.py` forwards the record's fields to the same mock as
  keyword arguments, so ~32 existing assertions keep testing what they tested rather than being
  rewritten — and if `PassageVectorRecord` ever drifts from `upsert_passage`'s parameters the
  names stop matching and they fail, which is what you want from a shim.

  **Review of my own change** caught the store being constructed **per chunk** inside the ingest
  loop (and per entity in the embedder); both are now resolved once per batch.

- [ ] **QC-3** — Vector cutover: recall on real data, then **STOP for POST-REVIEW**
  `/review-impl` (data migration — deeper than `/aif-review`). Then **live**: re-run
  `flat_knn_rawsearch.py` against the real corpus on both backends and publish **recall@10 and
  latency ratios**, not absolutes.
  **Restore drill (mandatory):** back up the vectors, drop them, restore, re-run recall. Decision T4
  says vectors are durable primary data — **an untested restore is not a backup.**
  ⏸ **POST-REVIEW checkpoint — present evidence and WAIT.**
  ---
  **QC-3a ✅ — the rebuild measurement above the threshold, and the RTO.**
  Full evidence: [`docs/measurements/2026-08-10-diskann-rebuild-scale.md`](../measurements/2026-08-10-diskann-rebuild-scale.md).

  **The threshold was the wrong variable; `maintenance_work_mem` is the lever.** At the image
  default (64 MB) every build logs `Builder neighbor cache is full after processing 14717
  vectors` — the *same* 14 717 at every corpus size, because it is a function of memory alone,
  and it binds **four times below** the 65 536 parallel threshold this task was commissioned to
  cross. At 100 000 rows a *second* cache also fills (`Quantized vector … 83887`).

  | rows | 64 MB | 1 GB | speed-up |
  |---|---|---|---|
  | 20 000 | 63.5 s | 65.1 s | 1.00× |
  | 40 000 | 207.0 s | 127.2 s | 1.63× |
  | 70 000 | 502.9 s | 252.9 s | 1.99× |
  | 100 000 | 893.3 s | 497.6 s | 1.80× |

  The benefit tracks the *share* of the build running past the cache limit (26 % at 20 000 → 85 %
  at 100 000), which is why **the drill's own 20 000-row anchor was nearly blind to it**. Re-fitting
  each column on its own anchor: exponent **1.64 at 64 MB** (matching the drill's fitted 1.6) and
  **1.26 at 1 GB** — the memory changes the curve's shape, not just its constant.

  **RTO, on the recovery path** (`vector-backup-drill.sh`, 100 000 rows — the measurement T25 said
  did not exist): **1051.1 s → 437.6 s**, i.e. **17.5 min → 7.3 min**, `passed=6 failed=0` in both
  passes including *every vector byte-identical* and *the exact nearest-neighbour answer
  unchanged*. **Recommendation: raise `maintenance_work_mem` on the image** (per-operation, so
  prefer the restore role over the global default).

  ⚠️ **Two of my own earlier readings were wrong and are corrected in the file rather than
  deleted.** A single 40 000-row point read as *"the drill under-predicts by 68 %"* — that was an
  anchor mismatch across two harnesses, not a modelling error. And a mid-run 1 GB point landing
  within 0.7 % of prediction looked like confirmation; it was two errors cancelling. Both came
  from stopping at one measurement.

  **QC-3b ⚠️ — the `300/200` defaults do NOT survive the corpus growing.**
  Full evidence: [`docs/measurements/2026-08-11-vector-search-effort-at-scale.md`](../measurements/2026-08-11-vector-search-effort-at-scale.md).

  T24 shipped `search_list=300, rescore=200` on **recall@10 = 1.000 at 181 rows**. At 20 000 rows
  the same settings return **0.516** — about half the true top-10 missing, from a search that
  reports success. The knobs themselves are vindicated (**+0.27 recall** over the server defaults
  at both 5 000 and 20 000; the hnsw cells move ~0.03 under their own knob, which is what shows
  the diskann movement is real). What fails is treating them as a constant.

  It is effort-bound, not a dead corpus — and the effort **runs out**:

  | 20 000 rows | recall@10 | p50 |
  |---|---|---|
  | 100/50 (server default) | 0.244 | 5.2 ms |
  | **300/200 (shipped)** | **0.516** | 9.0 ms |
  | 1000/500 | 0.712 | 14.4 ms |
  | 4000/**1000** — rescore at its hard ceiling | 0.824 | 33.0 ms |
  | *exact seq-scan* | **1.000** | 40.9 ms |

  `diskann.query_rescore` is refused above 1000 (`InvalidParameterValueError … (0 .. 1000)`), so
  "turn it up until recall is acceptable" stops being available — and by the ceiling the index
  costs 33 ms for 0.824 against **40.9 ms for a perfect answer**. Harness positive control
  (`exact` = 1.0000 vs numpy ground truth computed outside the DB) held on every run.

  🔻 **`D-QC3B-NO-REAL-CORPUS-AT-SCALE`** — the absolute numbers are **synthetic, and a floor**.
  The real passage corpus is **181 rows**, so *"recall on real data at scale"* cannot be measured
  today. What transfers is the shape, not the value. **Retry when any real book's corpus exceeds
  ~5 000 passages (most plausibly after QC-5) — and before the cutover ships, because this is an
  input to that decision, not a follow-up to it.** Mechanism: `--source neo4j` already exists and
  needs data, not code; its `exact` control voids the run if the harness is broken.

  **Still owed by QC-3:** `/review-impl`, and the recall comparison on the real corpus — which is
  the deferral above. The restore drill is done (T25 built it; QC-3a re-ran it at 100 000).
  ⏸ **This checkpoint is NOT signed off.** It gates the vector cutover, which is independently
  blocked by `D-T25B-SOAK`, so work continues on tasks the checkpoint does not gate.

<!-- Commit checkpoint: T21–T25 — cross-service seam + data migration -->

### Phase 4 · KAL write path and the command surface *(S2)*

**37 `*Core` functions already are the command layer** — documented as the shared SSOT for HTTP +
MCP. What is missing is outbox-in-the-same-transaction as part of their contract.

- [x] **T26** — Move `temporalCapability()` out of the gateway ✅
  `app/kal/temporal.py` + `GET /internal/kal/temporal-capability`; gateway fetches, caches 30s and
  forwards. **4120 python + 25 gateway green.**

  **The layering violation was a correctness bug, which is why it was worth moving.** The gateway
  computed the KG's `as_of` honorability from its OWN `KG_TEMPORAL_ENABLED`, and nothing tied that
  flag to the graph it described. A gateway with it on, in front of an unmigrated
  knowledge-service, advertised `ordinal_valid_time` and forwarded `as_of` to a substrate answering
  in transaction time — **a spoiler leak produced by two processes disagreeing about a boolean.**

  **`kgAsOfOrDrop` is gone.** The gateway forwards `as_of` verbatim and the owner decides — the same
  reason `state`'s `as_of` is forwarded unvalidated (decision B2). The parse guard stays: rejecting
  literal `"NaN"` is a question about the wire, not about the substrate.

  **`scripts/gateway-domain-logic-gate.py`**, wired into pre-commit + `foundation-ci.yml`. AST-ish,
  comment- and string-blanked, so a doc comment describing the old rule is not reported as the rule.

  **The bite failed twice before it fired, and both misses were the gate's fault.** (1) The
  vocabulary matched `capability`/`substrate` but not `temporal`, so re-adding
  `if (process.env.KG_TEMPORAL_ENABLED === 'false')` passed — its only domain word lived inside a
  string literal, which the blanking removes. **A gate that cannot catch its own founding incident
  certifies the absence it cannot see.** (2) After adding `temporal`, `[tT]emporal` still missed the
  upper-case `TEMPORAL`. Now case-insensitive, and the rule is sharpened: handling an `as_of` VALUE
  is forwarding; consulting LOCAL CONFIG alongside it is deciding.

  **Its first clean run found a second instance I had missed** — `health/health.controller.ts:17`
  computed the same capability from gateway config, in a **readiness probe operators trust to
  describe the deployment.** Now forwards.

  **Live smoke** (both images rebuilt): gateway `/health/ready` → `kgTemporal=ordinal_valid_time`,
  which is *not* the `temporal_unsupported` fallback — so the value genuinely crossed the service
  boundary. With `KG_TEMPORAL_ENABLED=false` on the SERVICE, the service reports
  `temporal_unsupported` and drops `as_of`. The authority moved.

  ✅ **Found in passing, now FIXED:** the gateway's `neighborhood` read called
  `/internal/books/{id}/kg/neighborhood`, which **existed nowhere in the repo** — and it was
  not a private detail: the route it backs is published in
  `contracts/api/knowledge-gateway/kal.v1.yaml`, so **the spec advertised a 404** to every
  reader. `app/routers/internal_kg_neighborhood.py` serves it, built on T18's one-hop graph
  read with the project scope in the lookup (the FK is unique per *(user, project)*).
  Cold start — no KG project, or an entity never synced — is a **200 with no edges**, the
  convention `internal_kg_state` already uses; a 404 would make every caller treat a normal
  state as failure. `as_of` is dropped, not raised, per T26, and the response says so.

  **`hops` is refused, not silently narrowed.** The port is one-hop by construction, so
  answering a 2-hop request with 1-hop edges returns a truthful-looking subgraph missing half
  of what was asked for, with no way for the caller to notice. The contract advertised
  `maximum: 2` against an endpoint that did not exist at all; it is now `maximum: 1` — the
  spec narrowed to what is served rather than the endpoint pretending to meet it.

  **Live** (rebuilt image): cold-start book → `200 {"edges":[],…}` where it was a 404;
  `hops=2` → `422`. 8 new tests.

- [x] **T27** — Make outbox-in-transaction part of the `*Core` contract ✅
  `internal/api/outbox_lifecycle.go` + 4 call sites + 3 consumers + a gate. **4120 python + the
  full Go api suite (71 s, live DB) green**, 6 new lifecycle tests.

  **Three events, not one — the plan's warning was the design.** `glossary.entity_deleted` /
  `entity_restored` / `entity_purged`. Emitting only `deleted` would have fixed a third and left
  the worst half: a deleted-then-restored entity stays **archived downstream forever** while the
  glossary shows it live, and no retry converges that, because the corrective event does not exist.
  `purged` is separate from `deleted` because it is a separate fact — soft-delete is reversible and
  maps to archive, purge is not and maps to a cascading delete.

  **Four silent sites, not three.** `softDeleteEntityCore`, `restoreEntityCore`, `purgeEntity`
  **and `bulkDeleteEntities`**. Purge had no `*Core` at all, which is part of why it was
  overlooked — a contract cannot be enforced on code that is not expressed as the thing being
  contracted. Bulk now drives emission from `RETURNING entity_id`, so the count it reports and the
  events it emits come from one list and cannot disagree.

  **The downstream half already existed and had never been called.** `archive_entity` /
  `restore_entity` sat in knowledge-service's Neo4j repo, unused, because nothing told them.
  Handlers registered for all three.

  ⚠️ **A latent bug the consumer work exposed: `archive_entity` sets `glossary_entity_id = NULL`.**
  Correct when a glossary delete meant *gone*; wrong now that restore is an event, because the
  restore payload carries a glossary id and the anchor it would match is severed. A restore handler
  written the obvious way would find no node, do nothing, and report success — **the silent no-op
  this task exists to remove**, reintroduced by the fix. Archive now leaves a
  `prior_glossary_entity_id` breadcrumb and restore/purge match either property.

  **The actor is a parameter, not read from ctx.** The only ctx identity available
  (`userIDFromCtx`) is set by MCP middleware alone, so a REST delete would have silently recorded
  itself as a pipeline write — an audit trail that mislabels who deleted an entity is worse than
  one that says nothing.

  **`scripts/entity-lifecycle-outbox-gate.py`**, wired into pre-commit + `foundation-ci.yml`.
  Its first clean run flagged `mergeOne` / `revertMergeCore`; both were false positives (a merge
  announces itself via `entity_merged`, which the KG already consumes), now an **allowlist with
  stated reasons** where a stale entry is an error.

  **The gate's bite failed twice, and both misses were the gate's own shape.** (1) `_EMITS` lists
  the `*Core` names so a delegating handler counts — which made every `*Core` match its OWN
  signature line, so a silenced `restoreEntityCore` still "emitted". (2) After trimming the
  signature, each function's chunk still swallowed the **doc comment of the next function**, and
  the comment above `purgeEntityCore` names a function in `_EMITS`. Bodies are now cut at their own
  closing brace. The behavioural bite (remove the emit) reds 4 tests.

  ✅ **`D-T27-LIVE-REPLAY` — CLEARED, and it found a bug that had shipped.**
  `scripts/glossary-lifecycle-live-replay.sh`. All four events now carry end-to-end on a live
  stack: **outbox → worker-infra relay → `loreweave:events:glossary` → dispatcher → Neo4j.**

  ⚠️ **T27's delete handler could never have worked, and T28 extended the same broken call.**
  `get_entity_by_glossary_id` REQUIRES `project_id` (D-KG-GLOSSARY-FK-GLOBAL-UNIQUE — the FK is
  unique per *(user, project)*, so one glossary entity can have a node in each of a user's
  projects). `_lifecycle_preamble` resolved the project and **threw it away**, so every archive
  raised `TypeError`, retried 3×, and went to the DLQ. **The dev outbox agreed: lifetime count
  of `glossary.entity_deleted` rows was ZERO** — the T27 events had never once flowed.

  **Nothing could have caught it except this run.** The Go suite proves the producer; the Python
  suite proves which repo call each handler makes — **by mocking that repo, and a bare
  `AsyncMock` accepts any signature.** Every patch is now `autospec=True`, which reds on exactly
  this. *(Bite: drop `project_id` again → `TypeError: missing a required argument`.)*

  Restore and purge were scoped only by `user_id` while the archive was scoped by project, so
  the two disagreed about breadth; both Cyphers now filter `project_id` too.

  **Isolation:** a synthetic `user_id`/`project_id`/`book_id`/`entity_id` that no real row
  references. Every query in this schema is `WHERE e.user_id = $user_id`, so the node is
  unreachable from any real read, and the trap removes it on exit. The **first** run generated
  four EMPTY ids (Git Bash has no `uuidgen`) and its cleanup ran
  `MATCH (e:Entity {user_id: ''}) DETACH DELETE e` against the dev graph. Nothing matched;
  nothing about that was by design. The script now refuses to start unless all four ids are
  UUIDs, because every cleanup in it deletes **by tenant id**.

  Green legs: archive on retire (`archive_reason=glossary_status_rejected`, **anchor
  preserved** — `user_archive_entity`, not `archive_entity`), the reason-scoping boundary
  (a recycle-bin restore does **not** un-archive a rejected entity), un-archive on reinstate,
  archive + breadcrumb on delete, node gone on purge.
  (depends on T26)

- [x] **T28** — Converge the `curation*Core` family ✅
  `internal/api/outbox_curation.go` + 5 call sites + a consumer + the gate on a second axis.
  **4131 python (+11) + the full Go api suite (63 s, live DB) green**, 6 new Go tests, 11 new
  Python tests.

  ⚠️ **The named premise was half wrong, and the half that was right was one layer down.** The
  four `curation*Core` funcs the plan names are the MINT side — they write nothing, they mint a
  confirm card, and they already converge (one core, two MCP tools). The drift the plan
  predicted is real but lives on the WRITE side. Of the four write cores each transition
  actually routes through: `mergeEntitiesCore` and `restoreEntityRevisionCore` emit;
  **`bulkSetEntityStatusCore` and `reassignEntityKindCore` emitted nothing.**

  **`status` is a liveness predicate here, not a label** — `knowledge_client.go:411,451`,
  `server.go:718,725,734,791` and the wiki read all filter `status = 'active'` alongside
  `deleted_at IS NULL`. Retiring an entity to `inactive`/`rejected` removed it from every
  consumer-facing glossary read and announced nothing, so **the KG mirror kept the node and
  kept answering RAG queries about an entity the author had retired** — T27's split brain
  reached by a different verb. A re-key was silent the same way, and `kind` is a field of the
  payload the mirror stores, so a moved entity kept its old kind in the graph forever.

  **Three status entry points, not two.** REST bulk, the confirm effect, **and
  `seedSelfEntityCore`**, whose draft→active promotion flips an entity from invisible to live
  canon. It keeps its own UPDATE (the same statement sets `is_self` and strips provenance tags
  — splitting it would trade one silent write for two non-atomic ones); what is shared is the
  emit. A fourth path, `reconcileEntityFromSnapshot`, restores `status` too, so a revision
  restore now emits `status_changed` when the snapshot moves it.

  `glossary.entity_status_changed` is its own event, not a `status` field on `entity_updated`:
  that event fires from ~a dozen paths and means "re-sync the content", so hanging an
  archive/restore side effect off an optional field makes every one of them a latent archive
  trigger. The re-key goes the other way for the same reason — it IS a content change and the
  payload already carries `kind`.

  ⚠️ **Reviewing my own diff caught two hazards I had just introduced.** (1) I reached for
  `archive_entity`, which nulls `glossary_entity_id` — correct for a delete, wrong here: the KG
  sync MERGEs on that anchor, and a retired entity is still editable, so **the next edit would
  have failed to match the anchorless node and created a second, un-archived twin of it.** Now
  `user_archive_entity` (keeps anchor + score). (2) Two archive sources can now undo each
  other. Restores are scoped by `archive_reason` prefix, and both archive Cyphers `coalesce` it
  so **whoever archived it first owns the un-archive** — otherwise trashing an
  already-`rejected` entity and pulling it back out of the bin resurrects it through a route
  that never mentions status. The reverse order is unreachable (`setEntityStatusCore` filters
  `deleted_at IS NULL`).

  **The gate's bite failed twice more, and both misses were holes in the T27 gate I shipped.**
  (1) Removing the emit left it GREEN because **comments were never blanked** and the
  roll-back comment right below explains itself by naming `bulkDeleteEntitiesCore`, which is in
  `_EMITS`. T27 fixed this class twice at the chunk BOUNDARIES; neither fix touched prose
  *inside* them. Now stripped, with string literals kept (the SQL lives in raw strings).
  (2) Silencing `reassignEntityKindCore` left it green because the SQL sits in the allowlisted
  `rekeyEntityToKind` and **nothing ever checked that the caller the exemption points at still
  emits** — the exemption outlived the exact thing that justified it. Entries now name their
  emitters and the gate holds them to it; its first run caught that I had named
  `resolveEntityKind`, a pass-through that has never emitted anything.

  ⚠️ **T27's entry claimed "the consumers are unit-covered". They were not** — no test in
  knowledge-service named any of the three handlers. `test_glossary_lifecycle_handlers.py` now
  covers both tasks (11 tests), including the Cypher predicates themselves, since a mocked repo
  cannot tell you a query honours its own argument.

  **Bites:** removing the status emit reds 5 of 6 Go tests; unscoping the restore Cypher and
  mislabelling the delete-restore prefix reds 2 Python tests; all three gate bites red the gate.
  (depends on T27)

- [x] **T29** — The `command-or-nothing` gate + KAL command routes + `SR06` tier ✅
  The gate (and the defect it found) · the F5 tier rows + runbooks · the five KAL entity
  commands. Full Go api suite green (74 s, live DB), 25 gateway tests, 9 new command tests,
  all gates + both runbook lints PASS.

  ⚠️ **The rule as written is not enforceable, and enforcing it literally would hide the
  defect rather than catch it.** "No bare `UPDATE`/`INSERT` on `glossary_entities` outside a
  `*Core` command" covers **33 functions** (measured, list in the commit). Most write columns
  **no consumer mirrors** — `dedup_key`, `is_pinned_for_context`, `kind_labels`. Converging all
  33 is a refactor several times this task's size, and a gate written against the literal rule
  would need ~30 allowlist entries — which is precisely the *"or the gate allowlists one
  forever"* failure T28's own line warns about.

  The property the recorded defects actually share is **not** "writes the table". It is
  **"writes a column a consumer keeps a copy of"** — T27 was `deleted_at`, T28 was `status` and
  `kind_id`. So the gate grew a third column family (`short_description`, `cached_name`,
  `cached_aliases` — what `loadEntityEventFields` reads) rather than a table-wide ban. It now
  polices **14** mutations, up from 11.

  ⚠️ **Asking the sharper question found a third instance immediately.**
  `regenerateAutoShortDescription` runs **post-commit** for two callers
  (`applyEntityEdit`, `setEntityAttributes`) that had already emitted `entity_updated`
  **inside** their transaction — so the mirror kept the **pre-edit summary forever**, in the one
  field the composition packer reads for a cast bio. It now reports whether the summary
  actually moved (`RowsAffected` off the existing `IS DISTINCT FROM`, so the signal cannot
  disagree with the write) and those two announce it. The other three callers regenerate
  *before* their emit and were always correct.

  **What the gate cannot check, stated rather than implied:** it proves a mirrored-content
  writer emits or has a named emitting caller. It **cannot** prove the emit happens *after* the
  write — which is exactly what went wrong here. That ordering is covered by a test asserting
  the changed-signal contract (*bite: make it always-true → red*), not by the gate.

  **Verification:** full Go api suite green (63 s, live DB); all three gates PASS.

  **The F5 precondition, landed first.** Three `SR06` rows in `contracts/dependencies/
  matrix.yaml` — `knowledge-gateway`, `glossary-service`, `knowledge-service` — each with a
  paired runbook, because the matrix's own governance says an entry without one is not an
  entry. `TestLoadAndValidate_RealMatrixYAML` pins the shipped file, so the rows are validated
  rather than merely written *(bite: `criticality: P9` → red)*.

  The classes are argued, not defaulted: `knowledge-gateway` is `non_idempotent` because the
  same host serves reads and the write verbs and a caller cannot tell them apart from outside
  (`appendFact` twice is two facts); `glossary-service` is `critical_write` because it is the
  sink every command lands in; its degraded mode is `read_only`, not `limited`, because when
  the sink is down the KAL must **refuse** commands rather than accept and lose them.

  ⚠️ **Recorded in the matrix rather than glossed over:** `kal/downstream.ts` calls both
  backends with a bare `fetch` — **no timeout, no breaker, no bulkhead**. A hung
  glossary-service parks a KAL request until the client gives up. The rows describe the
  discipline the KAL is *required* to have; wiring them through `ClientFactory` is the
  follow-up the dependency lint flips to error mode for.

  ⚠️ **Two premises were already stale:** `kal-write.controller.ts` **existed** (fact verbs
  only), and `SR06` is not a doc to edit but the registry at `contracts/dependencies/
  matrix.yaml` that its §12AI.2 defines.

  **The command routes, and the gap they close.** T27/T28 made five transitions safe but left
  every core reachable only from the browser's REST route and the agent's MCP tool. **A service
  had no sanctioned path at all** — and INV-KAL forbids reaching around the KAL into
  `/internal/*`, so "no route" meant "no way to ask". Now: `internal_entity_commands.go` (five
  thin handlers → the same cores) + the KAL forwards + 5 paths in the published `kal.v1.yaml`.

  The handlers are thin on purpose: book scoping, the found/no-op distinction and the emission
  all live in the core, and a handler re-implementing any of it would be the second place for
  the two to drift — the failure T28 is named after. A no-op is **404, not a 200 with
  `applied:false`**: a caller that cannot tell "I did it" from "nothing to do" retries forever
  or stops too early.

  **The actor is forwarded, never invented.** `X-User-Id` absent ⇒ `uuid.Nil` ⇒ `pipeline` with
  an EMPTY actor id; a garbled value degrades to `pipeline` and warns rather than failing a
  legitimate command, because authority comes from the internal token, not that header.
  *(Bite: synthesise a user for the absent case → red.)*

  **Live** (both images rebuilt): all four entity verbs reach glossary through the gateway and
  return its status faithfully — `downstream 404: GLOSS_NOT_FOUND` for an absent entity,
  `downstream 422: GLOSS_INVALID_STATUS` for an out-of-set status. Cross-book and untokened
  commands emit nothing and change nothing.
  (depends on T28)

- [x] **QC-4** — Emit-wiring live proof (the one that catches a bypass) ✅
  New: `scripts/glossary-lifecycle-live-smoke.sh`
  `/review-impl`. Then on a **live** stack: trash an entity and assert the effect **in every
  consumer** — absent from the KG `<facts>` block, `is_glossary_stale` raised in translation, absent
  from composition's cast read, `archived_at` set in Neo4j.
  **Why live and why per-consumer:** an emit test that asserts the outbox row proves the row, not the
  delivery. The register records three bugs that were declared closed and were not — all three were
  emit/consume gaps.
  **Bite:** revert one `*Core`'s outbox write → the smoke must go red.
  ---
  ✅ **DONE — and it found two real defects plus a stale container, on its first live run.**
  `scripts/glossary-lifecycle-live-smoke.sh`: **10 passed, 0 failed, 0 skipped**, stable across
  repeat runs. Nothing in it writes an outbox row — a real `DELETE /v1/glossary/books/{book}/
  entities/{entity}` drives everything, which is what lets the bite reach it.

  🐞 **FINDING 1 — translation-service dropped all four lifecycle events.**
  `handle_glossary_event` returned early for every event that was not `glossary.entity_updated`,
  so `entity_deleted` / `entity_restored` / `entity_purged` / `entity_status_changed` were
  **acked and discarded**. Every *reading* consumer sees a delete for free (`deleted_at IS
  NULL`); a finished translation is stored TEXT that already contains the term, and nothing
  re-reads the glossary on its behalf. So an already-translated chapter kept rendering a name
  the glossary no longer had, **with nothing marking it for retranslation** — the flag is the
  only mechanism that reaches output already produced. Fixed; the four events now flag, and
  they keep M6b's *precision* path (they carry `glossary_entity_id`, so one deleted entity does
  not stale a whole book). **1170 translation tests green.**
  ⚠️ **A passing test asserted the bug was intentional.** `test_handle_ignores_other_event_types`
  pinned `glossary.entity_deleted` as correctly ignored. Replaced with a parametrised test over
  all four, plus one asserting the precision path — and a narrower ignore-test on
  `entity_created`, which genuinely must not flag (a brand-new entity cannot appear in an
  already-translated chapter). *Bite: restore the `!=` → all 5 new tests red, the other 14 green.*

  🐞 **FINDING 2 — the running glossary container did not contain T27/T28 at all.**
  `grep` of the running binary: `glossary.entity_updated → 1`, but `entity_deleted`,
  `entity_purged`, `entity_status_changed` → **0**, despite the image's build timestamp
  post-dating those commits. So the plan's own warning — *"rebuild the images first; a stale
  container passes for the wrong reason"* — held, except here it produced a false **FAIL**. I
  would have filed a bug against correct code had I trusted the run. **The emit had never once
  been exercised live from the producer**: T27's replay inserts the outbox row itself, and
  T50's parity evidence is Go tests.

  **The mandated bite fired.** Commenting out `emitEntityLifecycleTx` in
  `mutateEntityLifecycleTx`, rebuilding and re-running: **LEG 1, LEG 2 and both LEG 3
  assertions red, exit 1**; LEG 4/5 stayed green, which is itself informative — the cast and
  `<facts>` reads filter `deleted_at IS NULL` and never needed the event. Reverted, verified
  clean against HEAD, rebuilt.

  ⚠️ **Three of my own false passes, fixed, because each one is the failure mode this task
  exists to prevent:**
  1. **Skipped legs reported as success.** The first run picked the book with the most glossary
     entities; it had no knowledge project, so 3 of 6 legs skipped and it printed *"6 passed, 0
     failed"*. Skips are now counted, reported, and make the run exit 3 — **a leg that did not
     run has not asserted anything.** Fixture selection now prefers a KG-capable book.
  2. **LEG 6 crediting the CREATE for the DELETE's effect.** Creating an entity emits *two*
     `entity_updated` rows, which translation already acted on; if either landed after the
     scratch translation row existed, the flag flipped and LEG 6 claimed the delete did it.
     Proven by the bite: with the emit removed entirely, LEG 6 still passed. Three successive
     timing guards (settle-and-clear, consumer `lag=0`, `lag`+`pending`) each failed, because
     **`lag` cannot see an outbox row the relay has not shipped yet.** Now attributed from the
     producer's ledger: the flag must flip *and* `glossary.entity_deleted` must be the only
     event for this entity with `published_at` after the clear. *Bite: with the consumer fix
     reverted, LEG 6 goes red — which is what proves the fix is what makes it pass.*
  3. **LEG 2 matching by proximity.** It grepped for the entity id and looked two lines either
     side for the event type; on a busy stream that window slid off the entry and reported "not
     relayed" for an event Neo4j had visibly already archived on. Now matched by the stream
     entry's own `outbox_id` — the row's primary key.

  **Live evidence (final, twice):**
  ```
  LEG 1  outbox carries glossary.entity_deleted (1 row)
  LEG 2  relay carried THIS entity's glossary.entity_deleted onto loreweave:events:glossary
  LEG 3  KG node archived · anchor severed with a breadcrumb for restore to match
  LEG 4  absent from <facts> (was present before: 2)
  LEG 5  absent from the cast roster (was 1 before)
  LEG 6  translation flagged stale, and the ONLY event for this entity since the delete was
         glossary.entity_deleted
  10 passed, 0 failed, 0 skipped
  ```
  Writes only rows it mints itself (entity via the real create API — the name is an *attribute*,
  `cached_name` is trigger-maintained, so an INSERT would have built a row no writer produces),
  and removes them on exit including on failure.

- [x] **T50** — Bring the entity-lifecycle **MCP tools** onto the new command contract ✅
  *(added by `/aif-improve +check`)*
  `entity_delete_tools.go:59,68` · `entity_attribute_edit_tools.go:56,85` —
  `glossary_entity_delete` · `glossary_entity_restore` · `glossary_entity_rename` ·
  `glossary_entity_set_attributes`
  The `*Core` surface T27–T29 changes is **explicitly shared**: `entity_handler.go:1488` calls
  it *"the single source of truth for the REST DELETE route AND the `glossary_entity_delete`
  Tier-W confirm effect"*, and `effectEntityDelete` routes straight into
  `softDeleteEntityCore`. If the command gains a required story position or new emissions and
  only the HTTP schema is updated, **the MCP contract drifts silently** — a class this repo has
  already recorded twice (FastMCP strips undeclared fields; the REST mirror drops fields the
  MCP tool accepts).
  **Logging:** `DEBUG` the transport (HTTP vs MCP) on every command dispatch.
  **Test:** for each transition, assert HTTP and MCP produce **identical outbox emissions**.
  (depends on T29)

  ✅ **DONE.** `command_transport.go` + a parity suite. Full Go api suite green (65 s, live DB),
  all three gates PASS.

  **The four named tools were already on the contract** — and checking rather than assuming is
  the point. `glossary_entity_delete` writes through `effectEntityDelete` →
  `softDeleteEntityCore`; `glossary_entity_restore` → `restoreEntityCore`;
  `glossary_entity_rename` and `glossary_entity_set_attributes` both converge on
  `setEntityAttributes`, whose post-commit hole T29 closed. Every one already carried an
  explicit actor. So the task's real content was the two things it asked for that did **not**
  exist: the transport record and the parity proof.

  ⚠️ **Three copies of one INSERT, found while looking for somewhere to put the log.**
  `emitEntityLifecycleTx`, `emitEntityStatusChangedTx` and `insertEntityOutboxEvent` each held
  their own `INSERT INTO outbox_events` — three places for a column to be added to two of them,
  which is the shape T27/T28/T29 each spent a task on. Converged onto `insertOutboxEventTx`,
  which is now the ONE place an entity event is written, and therefore the one place the
  transport can be logged. "Every dispatch is logged" is a property of the code's shape rather
  than a promise to remember.

  **The transport is tagged at the boundary, never by the handler** — middleware sets `http` at
  the root, `internal` on the `/internal` subtree, `mcp` in `mcpIdentityMiddleware`; chi runs a
  subtree's middleware after the parent's, so the specific tag wins and a NEW command route
  inherits a truthful transport instead of `unknown`. A handler that tagged itself would be
  reporting its own name rather than how it was reached, and the two diverge the moment a
  handler serves a second transport — which is this entire surface.

  It is a **log** field, not a payload field: a consumer that behaved differently for an MCP
  delete than an HTTP one would be the split brain this phase exists to remove.

  **The parity test compares the outbox PAYLOAD, not the status code** — all three transports
  return 2xx while emitting whatever they like. It asserts the field *key set* matches (the
  FastMCP-strips shape survives equal values) plus `op`/`book_id`/`actor_type`, and asserts the
  entity ids **differ**, so the test cannot pass by comparing one write with itself.

  **Bites:** make the KAL stop honouring the forwarded actor → *"kal delete disagrees with HTTP
  on `actor_type`: http=user kal=pipeline"*, **with both transports still returning 2xx** —
  exactly the silent drift the task names. Drop the transport from the log line → the log-field
  test reds. `LOG_LEVEL` is unset in the dev stack so DEBUG is suppressed there; the assertion
  captures the logger instead, which is repeatable in CI and does not require mutating real
  dev data to read one line back.

<!-- Commit checkpoint: T26–T29 — cross-service seam -->

### Phase 5 · The model

- [ ] **T30** — Close `D-GLOSSARY-EVENTS-NO-SOT` **before any producer moves**
  `contracts/events/_registry.yaml` — 0 `glossary.*` entries; the real list is a Go `const` block
  hand-mirrored by five consumers with no generator and no drift gate.
  (depends on T29)

- [ ] **T31** — Physical lifecycle ledger; emit on delete **and restore and purge**; wire
  `archive_entity(reason='glossary_deleted')` — built, correct, honoured at 38 sites, **only test
  callers** since it was written.
  **Test:** per-consumer conformance — trash an entity, assert absent from that consumer's output.
  (depends on T30)

- [ ] **T32** — Widen `entity_facts_kind_chk`; add the **reveal axis** as a first-class read
  parameter; migrate the spoiler window onto *"read at reveal position P"* (decision Q8).
  Also: `invalidated_reason='episode_superseded'` for chapter revisions (decision Q6).
  ⚠️ **State `glossary_entities.alive`'s disposition explicitly**
  *(added by `/aif-improve +check`)* — it still has live readers (`canon_at_chapter_handler`,
  `extraction_handler`, `entities_by_ids_handler`, `entity_search`, `entity_revisions_handler`,
  `entity_handler`). Introducing liveness-as-a-fact **while leaving the column read** recreates
  the exact two-sources-of-truth condition the design diagnosed (`alive` 7290 true / 0 false
  alongside `:EntityStatus` 0-of-21 reachable). **Deprecate it, migrate every reader to the
  as-of liveness fact, then drop the column or document why it survives.**
  (depends on T31)

- [ ] **T52** — Fix `canon_at_chapter_handler` — the design's own worked example
  *(added by `/aif-improve +check`)*
  `services/glossary-service/internal/api/canon_at_chapter_handler.go:124`
  A **live public route** (`GET /v1/glossary/books/{book_id}/known-entities`, View-gated,
  feeding the composition canon-at-chapter panel) whose **entire purpose is "canon as of
  chapter N"** — and which bounds `chapter_entity_links` by chapter, then filters the
  **timeless** `e.alive = true` and joins the **current** name, aliases and kind.
  T5 adds a *new* as-of endpoint and never touches this one, so **the defect survives on a live
  path after the refactor claims to have fixed it.** The sealed design cites this exact line as
  its worked example.
  **Rewrite** to resolve name, kind and liveness **as-of the requested chapter**.
  **Logging:** `DEBUG` the resolved position and the per-field as-of source; `WARN` if any field
  falls back to a current value.
  **Test:** an entity renamed at ch.30 must render under its **ch.10 name** when queried at ch.10.
  (depends on T32)

- [ ] **T33** — World order as a **partial order over event entities** (**D0.1/D8**)
  Widen `app/extraction/causal_edges.py` from `causes/enables` to `causes | precedes`; copy the
  `motif_link` cycle guard to the event DAG.
  **`unknown` must be a first-class answer** — a wrong order is worse than an absent one for a canon
  check, and the relation proposer already measured 3-of-8 defensible.
  **Bite:** run over the corpus → edge count non-zero **and** the graph acyclic.
  (depends on T32)

- [ ] **T34** — Write-time dedupe (**D7**)
  `emitChapterFacts` — if the incoming `value_hash` equals the currently-open fact's, attach
  evidence instead of opening an interval. **11.7 % of rows carry no new information** (`gender`
  93.2 %), and that grows with chapter count.
  **Bite:** re-extract a processed chapter — fact count must not grow, evidence count must.
  (depends on T33)

<!-- Commit checkpoint: T30–T34 — migration + event contract -->

- [ ] **T35** — Opaque identity; KG holds **mentions**; retire `e.id = hash(name, kind)`
  `app/extraction/glossary_sync.py` — `ON MATCH SET` never updates `e.id`, so the 2026-08-02 kind
  backfill left **77 nodes** whose derived id disagrees with their own properties. 48 Cypher sites
  key on `Entity.id`.
  **Test:** rename + re-kind → no stale node, no minted duplicate.
  (depends on T34)

- [ ] **T36** — Roles as relation facts with story intervals (**M2**)
  Closes `D-CANON-CHECK-BLIND-TO-ROLE`, the refactor's stated acceptance case.
  (depends on T35)

- [ ] **T37** — composition-service becomes a KAL **command producer**
  Roles are plan-authored, not extracted — this is the scope widening M2 implies.
  (depends on T36)

- [ ] **QC-6** — Identity live proof
  `/review-impl`. On a **live** stack: rename an entity, then re-kind it, then re-run extraction on a
  chapter that mentions it. Assert **no stale node**, **no minted duplicate**, and that the 77
  known-stale nodes from the 2026-08-02 backfill are reconciled.
  **Data:** a Cypher count of nodes whose `e.id` disagrees with a recomputed hash — **must be 0**.

- [ ] **QC-5** — 🎯 **Re-run the dogfood book — the design's own acceptance test**
  `docs/specs/.../README.md`: *"Its shape is the design's own test: fix the design, then **re-run
  this book**."*
  Re-run the Mị Đế authoring flow **end-to-end through the real frontend**, same plan, same cast <!-- doc-language-gate: ok -- the book title is the cited corpus subject of the acceptance case -->
  pass, same three chapters.
  **Assert the failure now surfaces:** the trap must be attributed to the cast-designated antagonist,
  **or** the canon check must FAIL — `canon_consistency` scoring 5/5 on a misattributed betrayal is
  the defect, and a pass here with 5/5 means the refactor has not landed.
  **Data to capture:** the plan artifact, the drafted chapters, the critic's per-chapter scores, and
  the glossary delta (entity count before/after the cast pass). Paste into the plan.
  ⏸ **POST-REVIEW checkpoint — present evidence and WAIT.**
  (depends on **T36** — it is T36 that closes the case this test proves)
  *(moved here from Phase 5 by `/aif-improve +check`: the acceptance test was scheduled to run
  one commit BEFORE the task that makes it pass, so it would have failed and read as a regression.)*

<!-- Commit checkpoint: T35–T37 + QC-5 -->

### Phase 6 · Consumers migrate onto the KAL *(S3)*

- [ ] **T38** — Migrate the authored-catalog readers; shrink the gate allowlist per consumer
  ⚠️ The zero-allowlist precedent is **proven in miniature, not at scale** — it covered only the
  bi-temporal reads; this is the remaining **186 routes**.
- [ ] **T51** — Migrate the **frontend** surfaces *(added by `/aif-improve +check`)*
  31 files across nine feature folders consume these contracts — `glossary`, `trash`,
  `knowledge`, `knowledge-temporal`, `studio`, `composition`, `chat`, `wiki`, `world`.
  Concretely: `frontend/src/features/glossary/api.ts` · `features/trash/useTrashItems.ts` ·
  `features/knowledge-temporal/api.ts` (which calls KAL `roster` directly at `:82`).
  T7 changes the cast read and T32 moves the spoiler window onto a reveal position — **both
  change contracts the FE renders against.** Shipping the backend alone leaves those surfaces
  reading a contract that no longer exists, and the recycle-bin view is the one a user hits
  *right after deleting*.
  **Test:** the recycle-bin and spoiler surfaces still render after the reveal-axis change.
  (depends on T38, T32)

- [ ] **T39** — Invalidate the two uninvalidatable caches by digest, not TTL
  `app/context/anchors.py::_CACHE` (300 s) and `jobs/glossary_anchor_cache.py` (*"per-process, never
  cleared"*). Keyed on a coverage digest they become correct by construction.
  (depends on T38)
- [ ] **T40** — Partition `entity_facts` by `book_id`
  The growth table; every query is already book-scoped, so the key is clean.
  (depends on T39)

<!-- Commit checkpoint: T38–T40 — migration -->

### Phase 7 · Engine swap *(S4 — parallel to Phases 4–6)*

- [ ] **T41** — Build the **rebuild-from-Postgres** path
  **It does not exist** — the only sweepers are `reconcile_evidence_count` and `stats_updater`.
  Three claims depend on it: graph HA is unnecessary, P3 rollback, DR. Must be **built**, then run.
- [ ] **T42** — Second `GraphStore` adapter (Postgres-relational recommended; Kuzu the alternative)
  AGE is eliminated. Kuzu: ✅ `MERGE … ON CREATE/ON MATCH SET` · ✅ `current_timestamp()` ·
  ❌ `CALL {}` (14 sites).
  ⚠️ **Decision X1 (PO, 2026-08-09): build BOTH candidates and let T43's shadow comparison choose.**
  Do **not** pre-narrow to Postgres-relational on the grounds that T6's re-open tripwires already
  measure zero (p50 entity degree **0**; zero queries needing variable-length `RELATES_TO` past
  depth 2). That workload is shallow *because relationship extraction is immature* — the design says
  so itself, and T33 is in this plan precisely to change it. Deciding the engine from a
  known-weak extractor's output would settle it on an artefact, which is the argument the sealed
  design rejected. Cost accepted: ~14 `CALL {}` rewrites + 152 mechanical renames for an adapter
  that may be discarded.
  (depends on T41)
- [ ] **T43** — Shadow comparison + **property-based differential suite** + coverage floor
  No cutover while any port operation has **zero shadow observations** — merge/split/restore/coref/
  triage are rare and would diverge silently, and the graph feeds canon checks.
  (depends on T42)

- [ ] **QC-7** — Rebuild drill + shadow evidence, then **STOP for POST-REVIEW**
  `/review-impl`. **Actually run** rebuild-from-Postgres on a real book and time it — the path is
  being built in T41 and has never existed, so its cost is unknown and three claims depend on it.
  Publish the shadow-comparison ratios doc-21 style, and the **shadow-coverage report**: every port
  operation with its observation count. **Any operation at zero blocks cutover.**
  ⏸ **POST-REVIEW checkpoint — present evidence and WAIT.**

<!-- Commit checkpoint: T41–T43 -->

### Phase 8 · TruthStore consolidation *(T7 — last, needs identity first)*

- [ ] **T44** — Rewrite `D-SUBSTRATE-HOME` and SCOPE-3's two-layer row
  They are inputs to a refactor, not blockers — but rewrite them **deliberately**, in the standards,
  not by drift.
  (depends on T43)
- [ ] **T45** — Valid-time as a **scope-dependent axis** (`story_ordinal` | `wall_clock`)
  The one piece that must be *designed*, not ported: book truth is story-ordinal, memory truth is
  wall-clock.
  (depends on T44)
- [ ] **T46** — Port the mature bitemporal machinery Go → Python and merge the stores
  `maintain_chain` (pin-aware supersession), the content-addressed natural key, half-open interval
  invariants, `anchor+delta` fold with `folds_since_reground`. **Move it working — do not rewrite
  from the weaker side.**
  (depends on T45)

<!-- Commit checkpoint: T44–T46 -->

### Phase 9 · Closing controls *(the plan's own Settings demand these)*

- [ ] **T47** — Documentation checkpoint (**`Docs: yes` in Settings makes this mandatory**)
  `/aif-docs`. The refactor changes the KAL contract, the command surface, the storage model and two
  standards — none of which is discoverable from code.
  **Specifically:** `docs/standards/README.md` (INV-KAL scope now covers writes + the authored
  catalog), `docs/standards/scope-separation.md` (SCOPE-3 rewritten by T44), `AGENTS.md` (the
  two-layer rule and the four service sentences), and `contracts/api/knowledge-gateway/kal.v1.yaml`.
  (depends on T46)

- [ ] **T48** — `/aif-verify` against this plan
  Every task fully implemented, nothing silently dropped, tests green, **and every QC task's evidence
  actually pasted** — the evidence gate is the point, not the checkbox.
  (depends on T47)

- [ ] **T49** — Update `SESSION_HANDOFF.md` and archive the plan
  The ▶ NEXT SESSION block, the Deferred Items table, and the standards that moved. Then
  `/aif-archive`.
  **Do not** restate numbers a register or command already prints — that is how a second source of
  truth starts, and the generation-SSOT run recorded that exact mistake as its own debt row.
  (depends on T48)

<!-- Commit checkpoint: T47–T49 -->

---

## Rollback

Each phase is revertible, and the mechanism differs by phase — stated so nobody improvises under
pressure:

| phase | rollback |
|---|---|
| 0 · guards | plain revert; no data written |
| 1 · as-of read | revert; the endpoint is additive and no caller is load-bearing until T7 |
| 2 · ports | revert; adapters are byte-for-byte lifts, behaviour unchanged |
| 3 · vectors | **restore from the vector backup built in T25** — drill it in QC-3 *before* cutover |
| 4 · commands | revert; outbox rows are additive and consumers are idempotent |
| 5 · model | migrations must ship **with a down path**; `entity_facts` is append-only, so prefer invalidation over deletion |
| 6 · consumers | per-consumer; the allowlist shrinks one entry at a time and each entry is independently restorable |
| 7 · engine | point the adapter back; **rebuild-from-Postgres (T41) is the backstop** and is proven in QC-7 |
| 8 · consolidation | the highest-risk revert — do not start until Phases 0–7 are green and the register rows are discharged |

---

## Stop conditions

**Decision X2 (PO, 2026-08-09): all four gate measurements run at their scheduled slices.** T8, T10,
T21 and T41 are already sequenced immediately before the work they gate, and each carries a stop
condition below. Do not front-load them — the cost of context-switching out of an unfinished phase
was judged higher than the value of earlier warning. T9's migration-runner conflict is resolved
**inside T9**, as that task already states, not deferred to migration time.

Any of these means **stop and re-open the design**, not work around it:

1. **T8** shows the KAL hop makes `state@as_of` unaffordable per chapter → §12 needs rethinking.
2. **T21** shows pgvectorscale cannot index 2560/3072 → the vector plan changes.
3. **T33** yields few or low-quality `HAPPENS_BEFORE` edges → D0.1 degrades to *"unknown"* everywhere
   and AC1 stays broken. **This is the highest-risk unknown in the plan.**
4. **T41** shows rebuild-from-Postgres is impractical at book scale → graph HA returns as a
   requirement and Phase 7's rollback story fails.

## Re-open triggers (post-landing)

- p50 entity degree **≥ 3** (today **0**) → re-open the graph-engine choice
- any query needing variable-length `RELATES_TO` beyond depth 2 (today **zero**) → same
