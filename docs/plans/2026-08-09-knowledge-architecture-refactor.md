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

- [ ] **T1** — Add `deleted_at IS NULL` to `entityExistsInBook`
  `services/glossary-service/internal/api/entity_genres_handler.go:37`
  Guards 6 paths; the canonical-translation one fires a **paid LLM call** on deleted content and
  caches the result. Mirror the correct twin at `pipeline_read_tools.go:104`.
  **Logging:** `DEBUG` the entity id + book id + resolved liveness on every guard call; `WARN` when
  a request is refused because the entity is deleted (that WARN is the regression detector).
  **Test:** delete an entity, call canonical-translation, assert 404 and **assert no LLM call**.

- [ ] **T2** — Re-fetch `known_entities` per chapter
  `services/translation-service/app/workers/extraction_worker.py:474` (fetch) vs `:589` (loop)
  A book-wide job holds the list for its lifetime, so a mid-job delete is re-emitted for every
  remaining chapter.
  **Logging:** `DEBUG` the known-entity count at each chapter boundary; `INFO` when the count
  changes mid-job (that is the bug becoming visible).
  **Test:** delete an entity mid-job; assert it is absent from the next chapter's known set.

- [ ] **T3** — Add a lifecycle filter to the outbox payload query
  `services/glossary-service/internal/api/outbox.go:398` — `WHERE e.entity_id = $1` with no filter,
  so editing a trashed entity re-publishes it and knowledge-service re-embeds it. **The deletion is
  silently reversed in the consumer's index.**
  **Logging:** `WARN` when an outbox row is skipped because its subject is deleted.
  **Test:** soft-delete, then edit; assert no `entity_updated` is emitted.

- [ ] **QC-0** — Review + live proof for the three guards
  `/aif-review +check` on the diff. Then **live**: on a running stack, soft-delete an entity and
  (a) call canonical-translation → assert 404 **and zero LLM spend** in `usage_logs`; (b) edit it →
  assert no `entity_updated` on `loreweave:events:glossary`.
  **Why live:** T1–T3 are all *bypass* bugs. A unit test with a mocked pool cannot prove the real
  guard is on the real path — that is the inject-at-the-chokepoint trap.

<!-- Commit checkpoint: T1–T3 -->

### Phase 1 · Prove the read shape *(S-0.5 — ships the reported defect)*

The substrate already works; nothing reads it. `composition-service` passes `as_of` **zero** times.

- [ ] **T4** — Write AC1 + AC2 as failing conformance tests **first**
  New: `services/glossary-service/internal/api/state_asof_test.go`
  **AC1:** character dies ch.40 → `as_of=41` reports dead; **`as_of=39` reports present and ALIVE**.
  The second half is what proves the mechanism is temporal — a `deleted_at`-style implementation
  passes the first and fails the second.
  **AC2:** an attribute changes at ch.10/25/60 → `as_of=30` returns **exactly the ch.25 value**, one
  value per attribute.
  **Both must be RED before T5.**

- [ ] **T5** — `GET /internal/books/{book_id}/state?as_of=N` in glossary-service
  New: `services/glossary-service/internal/api/state_handler.go`; register in `server.go`
  `DISTINCT ON (entity_id, attr_or_predicate)` over the half-open predicate, `cardinality='single'`,
  `invalidated_at IS NULL`. **`as_of` is REQUIRED** — a missing position is `400`, never a default
  (decision: a default returns a silently wrong answer).
  **Logging:** `DEBUG` resolved `as_of`, row count pre/post `DISTINCT ON`, elapsed ms; `WARN` on a
  request without `as_of`.
  (depends on T4)

- [ ] **T6** — Expose `state@as_of` on the KAL
  `contracts/api/knowledge-gateway/kal.v1.yaml` + `services/knowledge-gateway/src/kal/kal-read.controller.ts`
  **Gateway carries no logic** (decision B2): validate, authorize, forward. `temporal_capability`
  is reported by the service, not computed here.
  **Logging:** `DEBUG` inbound `as_of` + downstream latency.
  (depends on T5)

- [ ] **T7** — Migrate composition's cast read off `roster`
  `services/composition-service/app/clients/kal_client.py` · `app/deps.py:300` · the planner/packer
  call sites
  `roster` survives as what it honestly is — an untimed catalogue enumeration.
  **Logging:** `INFO` the story position each drafting run resolves; `WARN` if a caller reaches the
  cast read without one.
  (depends on T6)

- [ ] **T53** — Migrate the *other* roster consumers *(added by `/aif-improve +check`)*
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

- [ ] **T8** — Measure `state@as_of` end-to-end, doc-21 style
  New: `docs/measurements/2026-08-XX-state-asof-ceiling.md`
  Rig stated · durability stated · **ratios not absolutes** · with a bite. Compare in-process vs
  through-the-KAL and **publish the ratio** — this is the gate the design named as most likely to
  invalidate it. Baseline already measured: **8.7 ms flat** at 26k facts.
  (depends on T7)

- [ ] **QC-1** — Contract review + consumer live smoke
  New: `scripts/state-asof-live-smoke.sh`
  `/aif-review +check`. Then drive `state@as_of` **through the KAL from composition** against a real
  book — not through a test client. **A new cross-service contract is proven by its consumer**, and
  the gateway hop is exactly what a unit test omits.
  **Data:** capture p50/p95 and the resolved position for 20 consecutive chapter reads; paste into
  the plan.

<!-- Commit checkpoint: T4–T8 — contract boundary -->

- [ ] **T9** — Covering index for the book-wide as-of read (**D9**)
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

- [ ] **T10** — Synthetic 4,000-chapter ceiling run
  New: `scripts/perf/state-asof-ceiling.sh`, throwaway DB only
  ~1.08 M facts. **Must not touch a real service DB** (`EnsureThrowawayDB`).
  (depends on T9)

<!-- Commit checkpoint: T9–T10 — migration -->

### Phase 2 · The ports *(sliced — each ships alone, per RT-12)*

- [ ] **T11** — Pull Cypher out of the selectors
  `services/knowledge-service/app/context/selectors/salience.py`
  Nothing can be abstracted while Cypher lives in a selector.
  **Logging:** `DEBUG` the repo call replacing each inline query.

- [ ] **T12** — Pull Cypher out of event handlers and extraction
  `app/events/handlers.py` · `app/extraction/coref_detect.py` · `app/extraction/glossary_passage.py`
  (depends on T11)

- [ ] **T13** — Pull Cypher out of `db/neo4j_helpers.py`
  Index creation and schema helpers move behind the port that will own them.
  (depends on T12)

<!-- Commit checkpoint: T11–T13 -->

- [ ] **T14** — Define `VectorStore` + its fake
  New: `app/ports/vector_store.py`, `app/adapters/neo4j_vector_store.py`, `app/adapters/fake_vector_store.py`
  `search(scope, embedding, k, filter)` · `upsert` · `ensure_index` · `drop_index`. Adapter is
  existing code lifted **byte-for-byte**.
  **Logging:** `DEBUG` scope, dim, k, filter cardinality, elapsed.

- [ ] **T15** — Define `OntologyStore` + its fake *(smallest — proves the pattern)*
  New: `app/ports/ontology_store.py` + adapters. 2.5k LOC, low blast radius.
  (depends on T14)

- [ ] **T16** — The `no-cypher-outside-adapters` gate
  New: `scripts/graph-port-gate.py`; wire into pre-commit + `foundation-ci.yml`
  No `MATCH (` / `MERGE (` / `CREATE (` outside `app/adapters/`.
  **Bite:** delete the adapter package → gate must go red.
  (depends on T15)

- [ ] **T17** — Migrate the 67 modules to the two shipped ports
  **Logging:** `DEBUG` adapter selection at construction; `INFO` the bound adapter at startup.
  (depends on T16)

<!-- Commit checkpoint: T14–T17 -->

- [ ] **T18** — Define `GraphStore` + its fake
  Domain operations, not Cypher: `resolve_or_merge_entity` · `find_entities_by_name` ·
  `neighborhood(entity, depth, filters)` · `relations_for(entity, as_of)` · `status_at_order` ·
  `events_in_window(after, before, axis)` · `archive_entity`/`restore_entity` · `upsert_relation`.
  (depends on T17)

- [ ] **T19** — Define `TruthStore` + its fake
  Two adapters from the start — `GlossaryTruthAdapter` (book-scoped authored facts) and
  `MemoryTruthAdapter` (project/global) — routed by scope. Consumers never learn which answered.
  (depends on T18)

- [ ] **T20** — Retire the 561 skips that needed a live Neo4j
  `services/knowledge-service/tests/` — repoint at the fakes; make `-n auto` safe.
  **This is the port's first user-visible win.**
  (depends on T19)

- [ ] **QC-2** — Adapter-parity live proof
  `/aif-review +check`. Then run the **same** context-assembly request against the Neo4j adapter and
  the fake, on a live stack, and diff the rendered block byte-for-byte.
  **Why:** the fake is about to carry 561 tests. If it drifts from the real adapter, every one of
  those tests becomes a lie — the exact failure the skips were hiding.

<!-- Commit checkpoint: T18–T20 -->

### Phase 3 · Vector layer to Postgres *(S1 — the only hard ceiling)*

`summary_index_name(project, model, level)` → ~30,000 HNSW indexes at 10k projects; ~63 M passage
vectors ≈ 390–780 GB. And **D2 needs as-of-filtered semantic search**, which is impossible while
vectors and validity intervals live in different stores.

- [ ] **T21** — Verify pgvectorscale dims > 2000 (**gate**)
  `SUPPORTED_PASSAGE_DIMS = (384, 1024, 1536, 2560, 3072)`. pgvector HNSW caps at 2000 (`vector`) /
  4000 (`halfvec`); StreamingDiskANN's ceiling is undocumented. **Blocks T22.**

- [ ] **T22** — Build and publish the Postgres image (**decision T5**)
  New: `infra/postgres-knowledge/Dockerfile` — PG18 + pgvector + pgvectorscale
  Self-hosters must not compile extensions; that would destroy the operability argument for leaving
  Neo4j. **You own this distribution's CVE cadence.**
  (depends on T21)

- [ ] **T23** — `PgVectorStore` adapter
  Per-dim partitioned tables using the **closed dim set already in the code**; tenant filtered in
  the planner (the thing Neo4j cannot do, and the reason per-tenant indexes exist).
  **Logging:** `DEBUG` chosen partition, filter selectivity, recall-relevant params.
  (depends on T22)

- [ ] **T24** — Dual-write + shadow-read, with a recall gate
  Extend `services/knowledge-service/app/benchmark/flat_knn_rawsearch.py`
  Neo4j HNSW vs pgvector vs StreamingDiskANN vs halfvec, same corpus, **recall@k + latency**.
  **Bite:** halfvec must measurably lose recall somewhere; if it never does, the harness is not
  measuring.
  (depends on T23)

- [ ] **T25** — Cut over; drop the Neo4j vector indexes; **build the vector backup path**
  Vectors are **durable primary data** (decision T4) — restored, never recomputed, because
  per-project BYOK means re-embedding spends **the user's** budget. This task creates the backup
  and restore procedure that three other claims depend on.
  (depends on T24)

- [ ] **QC-3** — Vector cutover: recall on real data, then **STOP for POST-REVIEW**
  `/review-impl` (data migration — deeper than `/aif-review`). Then **live**: re-run
  `flat_knn_rawsearch.py` against the real corpus on both backends and publish **recall@10 and
  latency ratios**, not absolutes.
  **Restore drill (mandatory):** back up the vectors, drop them, restore, re-run recall. Decision T4
  says vectors are durable primary data — **an untested restore is not a backup.**
  ⏸ **POST-REVIEW checkpoint — present evidence and WAIT.**

<!-- Commit checkpoint: T21–T25 — cross-service seam + data migration -->

### Phase 4 · KAL write path and the command surface *(S2)*

**37 `*Core` functions already are the command layer** — documented as the shared SSOT for HTTP +
MCP. What is missing is outbox-in-the-same-transaction as part of their contract.

- [ ] **T26** — Move `temporalCapability()` out of the gateway
  `services/knowledge-gateway/src/kal/temporal.ts` → the Python use-case layer
  A domain rule in TypeScript that **D0.1 invalidates**. Gateway forwards what the service reports.
  **Gate:** no conditional on substrate, capability, budget, salience or tenancy semantics inside
  `knowledge-gateway/src`. **Bite:** put one back → red.

- [ ] **T27** — Make outbox-in-transaction part of the `*Core` contract
  `services/glossary-service/internal/api/*.go` — 19 files write `glossary_entities`
  **Delete, restore AND purge are all silent today.** A design emitting only `entity_deleted` fixes
  one third and leaves restored entities permanently archived downstream.
  **Logging:** `DEBUG` command name + entity + emitted event type; `WARN` on a mutation with no
  outbox row (that WARN is the gate's runtime twin).
  (depends on T26)

- [ ] **T28** — Converge the `curation*Core` family
  `curationMergeCore` · `curationReassignKindCore` · `curationStatusChangeCore` ·
  `curationRestoreRevisionCore` — a second entry point to the same transitions is how emission
  drifts. Converge, or the gate allowlists one forever.
  (depends on T27)

- [ ] **T29** — The `command-or-nothing` gate + KAL command routes + `SR06` tier
  New: `scripts/command-outbox-gate.py`; `kal-write.controller.ts`; a row in `SR06`
  No bare `UPDATE`/`INSERT` on `glossary_entities` outside a `*Core` command. The KAL gets a
  dependency tier and a documented degraded mode **before** it owns writes (F5).
  **Bite:** reintroduce `softDeleteEntityCore`'s bare UPDATE → red. *(It is red today.)*
  (depends on T28)

- [ ] **QC-4** — Emit-wiring live proof (the one that catches a bypass)
  New: `scripts/glossary-lifecycle-live-smoke.sh`
  `/review-impl`. Then on a **live** stack: trash an entity and assert the effect **in every
  consumer** — absent from the KG `<facts>` block, `is_glossary_stale` raised in translation, absent
  from composition's cast read, `archived_at` set in Neo4j.
  **Why live and why per-consumer:** an emit test that asserts the outbox row proves the row, not the
  delivery. The register records three bugs that were declared closed and were not — all three were
  emit/consume gaps.
  **Bite:** revert one `*Core`'s outbox write → the smoke must go red.

- [ ] **T50** — Bring the entity-lifecycle **MCP tools** onto the new command contract
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
