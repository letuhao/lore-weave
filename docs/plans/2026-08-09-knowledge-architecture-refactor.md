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

**Phase 0 LANDED (`6ee50af00`). Phase 1 LANDED (`cfbcea8b5`) — T4·T5·T6·T7·T8·T53 + QC-1.
T9·T10 done (Commit 3).** The reported defect is fixed end to end: the drafting stack now reads
the cast at the chapter being written, and the read is index-served. Next is **Phase 2 (T11)** —
pulling Cypher out of the knowledge-service selectors.

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

**RESUME: T11** — pull Cypher out of `services/knowledge-service/app/context/selectors/salience.py`.
Phase 2 slices deliberately: nothing can be abstracted behind a port while Cypher lives inside a
selector, and each slice ships alone (RT-12). T11–T13 are the extraction; T14 onward define the
ports themselves.

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
