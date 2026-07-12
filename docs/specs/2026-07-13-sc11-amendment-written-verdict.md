# SC11 Amendment — the written-verdict is MAINTAINED, not derived

> **Status: PROPOSAL — awaiting PO sign-off.** SC11 is a **LOCKED** decision
> ([`22_scene_model_and_crud.md:239`](2026-07-01-writing-studio/22_scene_model_and_crud.md), under *Locked decisions*)
> and BPS-11 is sealed in [`00A:340`](2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md). Nothing here is
> enacted. Author: agent, 2026-07-13. Origin: the PO's rule — *"the GUI is a projection of data state:
> MCP changes BE data → BE data changes FE data → FE data changes the GUI"* — which points the opposite
> way from SC11's *"the browser LEFT JOINs intent client-side"*.

---

## 1. The headline: BPS-11 answered a **different question** than SC11's sentence generalised to

This is the whole opening, and it means the amendment **does not overturn BPS-11**.

**BPS-11** ([`00A:340`](2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md)) asks exactly one thing:

> | **BPS-11** | `22` OQ-1 — server-side **`status`/`pov` filters** on the scene browser? | **Client-side in v1** … | Requires a cross-service join. Revisit on **profiling evidence** from a 10k-scene book (defer gate #4), not on speculation. |

**SC11** ([`22:239`](2026-07-01-writing-studio/22_scene_model_and_crud.md)) states the *implementation* of that answer, and its sentence is broader than the question:

> | **SC11** | **The browser reads book-service and LEFT JOINs intent client-side** via one `composition_list_outline` call keyed by `chapter_id`. A Work-less book renders identity columns and greys the intent columns. | Preserves "a Work-less book still browses." **No new BE join across services.** |

`status` and `pov` are **authored intent** — composition's fields, filtered against a manuscript list. BPS-11
is right about those: filtering intent server-side *would* need a cross-service join, per node, at render time.

**But "is there prose behind this spec node?" is neither a filter nor intent. It is a manuscript FACT**, and
it is the one thing on this seam that book-service *already knows at write time* — it writes
`scenes.source_scene_id` in `parse.go` and `reparse.go`.

**This amendment scopes SC11's sentence back to what BPS-11 actually decided, and moves one fact — the
written-verdict — out of both clients.** The per-node client-side join of *intent* stays exactly as locked.

---

## 2. The evidence: we compute this fact **twice, on the client, with two different bug-guards**

| | Plan Hub | Scene Browser |
|---|---|---|
| Implementation | [`planHubMappers.ts:86-103`](../../frontend/src/features/plan-hub/hooks/planHubMappers.ts) `computeUnionState` | [`sceneUnion.ts:52-95`](../../frontend/src/features/studio/panels/sceneUnion.ts) `joinSceneRows` |
| Fetcher | [`useActualState.ts`](../../frontend/src/features/plan-hub/hooks/useActualState.ts) — **~130 lines** | [`useSceneBrowser.ts`](../../frontend/src/features/studio/panels/useSceneBrowser.ts) |
| Partial-read guard | per-chapter `completeChapters` gate (`planHubMappers.ts:99`) | book-wide `specComplete` gate (`sceneUnion.ts:44-50`) |
| Extra hazards handled | — | duplicate-anchor anomaly (`sceneUnion.ts:66-72`) |

**Two features, one fact, two independent completeness mechanisms.** Both guards exist to stop the *same*
bug class — `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` — and `computeUnionState`
needed a **HIGH-severity fix** to get its guard right. That is the drift this repo bans, and it is already
here; it is simply invisible because both copies are currently correct.

The cost of keeping them correct is real: `useActualState` carries a generation guard against book-switch
races (`:57`), a `requested` dedupe set (`:59`), a `MAX_PAGES = 50` page-walk bound (`:25`), per-chapter
completeness tracking (`:95`), and an `error` field whose documented purpose is that *a failed read must not
paint a written book as unwritten* (`:36-42`). **Every line of that exists because the derivation lives
where data arrives incrementally, out of order, and can be interrupted.** The code is good. That is the tell.

And the fact is **invisible to agents.** It lives in a `useState` and dies when the panel unmounts. An agent
asking *"which scenes have I not drafted?"* — the single most obvious question about a plan — cannot be
answered, while the same spec↔manuscript relation is *already* computed server-side in two other places
(`compute_coverage`, `compute_prose_deleted`), both agent-reachable.

---

## 3. The decision

> **SC11 (amended).** The browser continues to LEFT JOIN **authored intent** client-side, per node, per
> BPS-11 — unchanged. But a **manuscript FACT about a spec node** is **maintained on write**, not derived on
> read, by *either* side. Specifically: `outline_node.written_scene_id` is a **materialised inverse** of
> `scenes.source_scene_id`, stamped by the index owner's own write, and served as a field on the existing
> Plan-Hub read surface.
>
> **No new BE join across services** — the constraint SC11 names — is *strengthened*, not weakened: the
> amendment removes a cross-service read from the client **without adding one to the server**.

### Why not "BE derives it on read" (the option I proposed first, and now withdraw)

My earlier proposal (RUN-STATE §11) was *"one bulk anti-join, server-side."* **I checked the cost and it is
worse than I claimed.** `BookClient` pages at **100 rows/request**
([`book_client.py:326-328`](../../services/composition-service/app/clients/book_client.py)). `compute_coverage`
already eats this for *chapters*: a 10k-chapter book means **100 sequential HTTP calls inside composition,
per call**. Scenes are an order of magnitude more numerous. A whole-book scene anti-join is **the very read
H8.1's budget rejected — moved to the server.** It trades a client-side page-walk for a server-side one.

`scene_decompile._fetch_scenes()`
([`:139-145`](../../services/composition-service/app/engine/scene_decompile.py)) already does exactly this
walk, which proves it is *possible* — and is also the honest measure of what it costs.

**Maintain-on-write has no such walk.** The verdict becomes a column read.

---

## 4. Data model

### 4.1 A NEW column. `status` cannot hold this.

```sql
ALTER TABLE outline_node
  ADD COLUMN IF NOT EXISTS written_scene_id UUID,       -- soft ref → book-service scenes.id (NO FK, cross-DB)
  ADD COLUMN IF NOT EXISTS written_at       TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_outline_node_written
  ON outline_node(book_id) WHERE written_scene_id IS NOT NULL;
```

**`outline_node.status` is the author's INTENT and must not be reused.** It is
`CHECK (status IN ('empty','outline','drafting','done'))`
([`migrate.py:203`](../../services/composition-service/app/db/migrate.py)), it is an agent/author *write* arg
(SC8, [`22:236`](2026-07-01-writing-studio/22_scene_model_and_crud.md)), and the drawer edits it
([`PlanDrawer.tsx:233`](../../frontend/src/features/plan-hub/components/PlanDrawer.tsx)).

**PH16 ([`24:99`](2026-07-01-writing-studio/24_plan_hub_v2.md)) is decisive**: the drawer header shows the
*desired-vs-actual pair* — **spec `status` chip + prose state chip** — and *"the drawer edits the desired
state."* The spec already locks these as **two chips**. Fusing them would:

- delete a distinction PH16 locks;
- fuse desired and actual state in one column — **the exact drift bug BPS-3 deleted `structure_node.pacing`
  to prevent** ([`00A:327`](2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md): *"Two authored
  representations of one fact is the drift bug in miniature"*);
- mean an author marking a scene `done` in the drawer makes an **unwritten** scene render as written.

### 4.2 Why `written_scene_id` (a link), not `written boolean` or `written_at` alone

The Scene Browser needs more than a truth value. `sceneUnion.ts` distinguishes `anchorLost`
(`source_scene_id` set but dangling, `:79` — BPS-13's *"not yet written" ≠ "anchor lost"*) and must render
the `index_only` row *itself* (a manuscript scene with `leaf_text`). A bare boolean cannot serve it.
**`written_scene_id` IS the resolved link** — which is precisely what makes it a *materialised anti-join*
rather than a new truth. `written_at` rides along as the freshness/audit signal.

### 4.3 ⚠ The SC2 / DA-3 tension — name it, or the next agent will "fix" it back

**DA-3 ([`00A:285`](2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md)):** *"The index points at the
spec. `scenes.source_scene_id → outline_node.id`, **never the reverse**."*
**[`scene_decompile.py:29-31`](../../services/composition-service/app/engine/scene_decompile.py):*
*"Composition never writes `book-service.scenes.source_scene_id` (SC2: the sole writing role is the index
owner)."*

`written_scene_id` **is not a second authored anchor and does not re-invert SC2.** It is a **derived,
regenerable cache of the reverse pointer** — the same status `INV-FACTS` gives the EAV projection (*"lazy,
versioned, regenerable caches — never truth"*). The authored anchor remains `scenes.source_scene_id`, owned
solely by the index owner. If the two ever disagree, **`scenes.source_scene_id` wins and the column is
rebuilt from it.** This must be stated in the column comment and in a test, or a future reader will see a
back-pointer on `outline_node`, read it as a DA-3 violation, and delete it.

---

## 5. The write path — and the gap in it

### 5.1 Good news: the event mostly exists

book-service already has a transactional outbox (`outbox_events` +
[`insertOutboxEvent`](../../services/book-service/internal/api/outbox.go)) relayed by worker-infra's
`OutboxRelay` to `loreweave:events:<aggregate_type>`. And **`chapter.scenes_reparsed` is already emitted**
([`reparse.go:275`](../../services/book-service/internal/api/reparse.go)), *already carrying the right
aggregate*, and *already guarded by `counts.changed()`* ([`kg_index.go:199-208`](../../services/book-service/internal/api/kg_index.go))
— a no-op reparse does not fire it. knowledge-service already consumes it
([`main.py:281`](../../services/knowledge-service/app/main.py)).

### 5.2 ⚠ The gap — and the census was wrong TWICE. There are **six** writer sites, not three.

**This section originally said "three places." It was wrong, and the way it was wrong is the lesson.**
Phase 0's own DB test found a fourth; `/review-impl` then found a fifth and a sixth. Every miss was the
same shape: *I generalised a census from the first places I looked.*

| # | Writer | File | Emitted before Phase 0? |
|---|---|---|---|
| 1 | `.txt` import INSERT | [`parse.go`](../../services/book-service/internal/api/parse.go) | ❌ only `chapter.created` |
| 2 | Re-parse — **PUBLISH** | [`server.go`](../../services/book-service/internal/api/server.go) | ✅ `scenes_reparsed` (the most common re-parse of all; **missed by the first census**) |
| 3 | Re-parse — kg-index / mcp-publish | `kg_index.go`, `mcp_actions.go` | ✅ `scenes_reparsed` |
| 4 | Re-parse — **the IX-3 sweeper** | [`reparse_sweeper.go`](../../services/book-service/internal/api/reparse_sweeper.go) | ✅ `scenes_reparsed` (**re-links a book in the BACKGROUND, with no user action at all** — missed by the first census) |
| 5 | **worker-infra HTML/txt import INSERT** | [`import_processor.go`](../../services/worker-infra/internal/tasks/import_processor.go) | ❌ **nothing** |
| 6 | **worker-infra PDF import INSERT** | [`import_processor_pdf.go`](../../services/worker-infra/internal/tasks/import_processor_pdf.go) | ❌ **nothing** |
| 7 | **IX-12 decompile write-back** | `import_processor.go` — best-effort `UPDATE … WHERE source_scene_id IS NULL` | ❌ **nothing** |

**Two failure modes, both whole-book-wrong:**

- **(7)** creates the link for a *decompiled* book. Silent ⇒ a decompiled book renders entirely unwritten.
- **(5)/(6)** are the **ROUND-TRIP** case, and they are the subtler one: a user exports their book and
  re-imports it, so every scene arrives with its `data-scene-id` anchor *already set*. The IX-12
  write-back at (7) **only fills NULLs** — so it never touches them, and never emits. The links exist and
  nothing announces them. **The re-imported book renders entirely unwritten.**

**All seven now emit `chapter.scenes_linked`**, in the same tx as the write (INV-O12), each behind a
no-op guard (`anyLinked` / `counts.changed()` / rows-affected). Two source-level drift-lock tests — one
per service — pin the census so an eighth writer cannot ship silent.

### 5.2b The link also breaks when the SCENE VANISHES — a Phase 2 requirement, not a Phase 0 gap

A chapter trash/purge deletes its scenes without ever touching `source_scene_id`, and a spec node that
*was* written becomes unwritten. Phase 0 needs no new emit for this: **`chapter.trashed` and
`chapter.deleted` already exist**. But **Phase 2's consumer MUST handle them** and clear
`written_scene_id`, or the mirror will keep claiming prose that no longer exists. (The Phase 1 reconcile
sweeper is the backstop, not the primary path.)

### 5.3 composition-service needs its **first** domain-event consumer

Composition today consumes only its own job stream (`CompositionJobConsumer`) plus a grant-revoke *fan-out*
cache-bust. It has **no `EventDispatcher`, no `app/events/` package**. The pattern to mirror is
knowledge-service's (`EventConsumer(BaseProjectionConsumer)` + `EventDispatcher.register(...)`,
[`consumer.py:52`](../../services/knowledge-service/app/events/consumer.py)).

**Load-bearing warning, from knowledge's own comments
([`main.py:256-262`](../../services/knowledge-service/app/main.py)): an unregistered `event_type` is dropped
at DEBUG — *"the event is acked into the void. A perfect silent success."*** Budget for the registration and
a wiring test, not just the emit.

### 5.4 Backfill

One-shot, idempotent, resumable: for each book, page `scenes` where `source_scene_id IS NOT NULL` (the
partial index already exists —
[`migrate.go:594-599`](../../services/book-service/internal/migrate/migrate.go)) and stamp the matching
`outline_node`. Same page-walk as `scene_decompile._fetch_scenes()` — **paid once, offline, not per render.**

---

## 6. What it costs the read budget: **nothing. It refunds it.**

**PH9 ([`24:92`](2026-07-01-writing-studio/24_plan_hub_v2.md))** caps the cold open at **≤5 requests** and
H8.1 asserts it. This amendment adds **no request** — `written_scene_id` rides on the *existing* Plan-Hub
node payload (read surface #2). It **removes** one:
[`coldOpenBudget.test.tsx:115-139`](../../frontend/src/features/plan-hub/hooks/__tests__/coldOpenBudget.test.tsx)
today asserts `listScenes` is called *per loaded chapter after paint*. After the amendment it is **never
called by the Plan Hub at all** — the budget test's forbidden-list gets **stronger**.

⚠ **PH10 ([`24:93`](2026-07-01-writing-studio/24_plan_hub_v2.md)) enumerates the summary field set as a
closed list. It must be amended too** to admit the new field.

---

## 7. Blast radius

**Deleted** (~150 lines + their guards):

| File | Fate |
|---|---|
| [`useActualState.ts`](../../frontend/src/features/plan-hub/hooks/useActualState.ts) (whole hook, ~130 lines) | **DELETED** — with its generation guard, dedupe set, page bound, completeness tracking and error-propagation |
| `planHubMappers.computeUnionState` + its completeness gate | **collapses to a 3-line map** over the server field |
| `planHubMappers.toActualScene` + `types.ActualScene` | **DELETED** (no other plan-hub caller) |
| `usePlanHub.ts:80-87, 105-112, 269-286` | actual-state wiring + the `actual.error` degradation notice removed |

**Survives untouched** — and this is the strongest evidence the refactor is *contained*: every presentation
consumer of `NodeUnionState` (`nodePresentation.ts`, `SceneNode`, `ChapterNode`, `PlanCanvas`) is a pure
`state → className` map. **Zero changes.** `PlanHubView.unionState` keeps its shape; only its *producer*
changes.

**⚠ Tests that must NOT simply be deleted.**
[`planHubMappers.test.ts:84, :90, :102, :106`](../../frontend/src/features/plan-hub/hooks/__tests__/planHubMappers.test.ts)
encode a **real, previously-shipped bug class** (not-yet-loaded ≠ absent). They become meaningless
client-side — so **the server must make that bug structurally impossible, and a BE test must say so.**
Deleting a guard's tests without replacing the guarantee is how the bug comes back.

**⚠ Honest scope limit — the Scene Browser does NOT fully collapse.** `sceneUnion`'s *written-verdict* half
is served by the new column, but it still needs the manuscript list to render `index_only` rows (a scene with
no spec node) and `anchorLost`. Its scenes fetch stays. **If only the Plan Hub is migrated, the two surfaces
can disagree about "is this scene written?"** — a two-consumers-drift we would have *created*. **Both must
move together, or neither.**

---

## 8. Risks

1. **The event lies by omission.** The IX-12 write-back (§5.2) emits nothing today. Ship the consumer
   without fixing that and a decompiled book renders 100% unwritten — a confident, wrong, whole-book answer.
   **This is the single biggest risk and it must be closed first.**
2. **Eventual consistency.** The column lags the prose by the relay's latency. Acceptable for a *verdict*
   chip; **not** acceptable if anything gates on it (publish, a spend, a delete). Nothing does today —
   keep it that way, and say so.
3. **A regenerable cache read as truth.** Mitigated by §4.3 + a reconcile sweeper that rebuilds from
   `scenes.source_scene_id` (the producer's own predicate — the `reconcile-by-truth-mirror-producer-predicate`
   pattern).
4. **Silent-drop on an unregistered event type** (§5.3).

---

## 9. Rollout

| Phase | Work | Gate |
|---|---|---|
| **0** | Close the §5.2 emit gap: emit a scenes-linked event from **all three** writers (incl. the IX-12 write-back) | a test per writer; without this, nothing else is safe |
| **1** | Column + migration + backfill + reconcile sweeper | backfill is idempotent + resumable; sweeper rebuilds from the producer's predicate |
| **2** | composition's first `EventConsumer` + dispatcher + **a wiring test that a registered type is not acked into the void** | live-smoke: save prose → the column stamps |
| **3** | Serve the field on read surface #2 (amend **PH10**'s closed field list) | contract test |
| **4** | Migrate **both** clients together (Plan Hub + Scene Browser). Delete `useActualState`. Rewrite `coldOpenBudget` to forbid `listScenes` outright. | the four bug-class tests are *replaced* by BE tests, never just deleted |

---

## 10. For the PO — the questions this needs answered

1. **Do you accept the framing that BPS-11 answered a narrower question than SC11's sentence?** Everything
   rests on this. If you read BPS-11 as also covering the written-verdict, the amendment dies here and the
   status quo stands.
2. **Is eventual consistency acceptable for the verdict chip?** (Nothing gates on it today.)
3. **Both clients migrate together, or neither** (§7). Confirm that scope — a Plan-Hub-only migration
   *creates* the drift it is meant to remove.
4. **Phase 0 is not optional.** The IX-12 emit gap is a live latent bug regardless of whether this amendment
   ships. Do you want it fixed **now**, independent of the rest?

---

## Appendix — what this amendment does NOT change

- **BPS-11 stands.** `status`/`pov` filters remain client-side. Revisit only on profiling evidence, as sealed.
- **SC11's core constraint stands, and is strengthened:** *no new BE join across services* — this removes a
  cross-service read from the client without adding one to the server.
- **DA-3 / SC2 stand.** `scenes.source_scene_id` remains the sole authored anchor, written only by the index
  owner. `written_scene_id` is a regenerable cache of its inverse (§4.3).
- **PH16's two-chip header stands** — that is *why* `status` is not reused (§4.1).
- **"A Work-less book still browses"** stands: no Work ⇒ no `outline_node` ⇒ no verdict ⇒ the columns grey
  out exactly as SC11 requires.
