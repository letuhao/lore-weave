# Spec — Glossary entity versioning + restore (D-GLOSSARY-VERSIONING)

- **Date:** 2026-06-07
- **Branch:** `feat/translation-pipeline-v3` (or a dedicated `glossary/versioning` branch)
- **Size:** XL, full-stack (glossary-service Go + frontend). **Sliced** VG-1/VG-2/VG-3.
- **Priority:** HIGH — recovery-critical. Unblocks D-TRANSL-M4D-2B/2C.
- **PO decisions (2026-06-07):** scope = **whole-entity snapshot** · mechanism = **append-only `entity_revisions`, captured ASYNC as a projection off the `glossary.entity_updated` outbox stream (NOT a sync trigger)** · **actor-granularity** (version human edits always; throttle/skip high-volume machine/bulk writes) · **full-stack** (BE history+restore API **and** FE history/restore UI).

### Mechanism rationale (scale analysis, 2026-06-07)

At 10M+ entities the I/O wall is the **volume** of revision writes, not snapshot-vs-delta row size. Three levers, in order of impact, keep the hot path free and bound the volume — chosen over a sync trigger and over a delta/replay log:

1. **Async capture off the outbox** — the write path already emits `glossary.entity_updated`; a downstream consumer materializes revisions out-of-band. The hot write transaction pays **nothing extra** for history; the revision store is an eventually-consistent projection (~1s lag, fine for history).
2. **Actor-granularity** — the real recovery need is **human** edits (rare + precious + irreproducible). Machine/bulk writes (extract-entities, mui#1, M4d-2b) are **high-volume + reproducible** (re-run extraction). So: human → always version; machine/bulk → **skip or keep rolling last-N**. This caps the table at *human-edit count* (single digits per entity for a curated glossary), not machine-write count.
3. **Snapshot over delta** — with (1)+(2) the volume is bounded and the write path is free, so the delta-log's only wins (storage, write-payload) are neutralized, while its costs (replay-on-read **compute**, complexity) remain. Full snapshot keeps **O(1) restore** + minimal compute + a tiny bug surface (decisive for recovery-critical code). Delta+checkpoint is reserved for an entity edited hundreds of times **by a human** — a pattern a glossary does not have; do not pre-optimize for it.

Net: history is a **projection, not a tax on writes**; "saving storage" via deltas would trade the storage we can afford for the replay-compute we cannot — so we don't.

## 1. Context & problem

Glossary entity data is **destructive on edit/delete with no recovery**:
- `entity_attribute_values` (names/aliases/descriptions) + `attribute_translations` (per-language
  renderings) are **overwritten in place** — no history (`UNIQUE(attr_value_id, language_code)`).
- `trig_trans_snapshot` / the other `trig_fn_*_snapshot` triggers only recompute
  `glossary_entities.entity_snapshot` — a **current-state cache**, not history.
- The only existing trails are the `glossary.entity_updated` **outbox** (system sync, not
  user-browsable) and `wiki_revisions` (wiki articles only).

Contrast: **chapter translations are versioned** (`chapter_translations.version_num` +
`active_chapter_translation_versions`) — a user can browse/restore prior chapter translations.
Glossary — the hand-curated source of truth — has no equivalent. An accidental overwrite or delete
of curated names/translations is **unrecoverable**. This also blocks the M4d-2b machine writeback
(we refuse to ship destructive glossary writes until recovery exists).

## 2. Goal / non-goals

**Goal:** every change to a glossary entity captures a **restorable whole-entity revision**; a user
can **view an entity's history** and **restore it to any prior revision**, from the glossary editor.

**Non-goals (v1):** field-level granular diff/restore (whole-entity restore only); cross-entity
(book-wide) snapshots; revision retention/GC (hobby scale — keep all); versioning of wiki (already
has `wiki_revisions`) or relations graph (Neo4j, separate).

## 3. Design — `entity_revisions`

```sql
CREATE TABLE entity_revisions (
  revision_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id     UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  book_id       UUID NOT NULL,            -- denorm for scoping + partition/cleanup
  revision_num  INT  NOT NULL,            -- sequential per entity (1,2,3…), assigned by the consumer
  snapshot      JSONB NOT NULL,           -- the full entity_snapshot at this point
  op            TEXT NOT NULL,            -- create | update | delete | restore
  actor_type    TEXT NOT NULL DEFAULT 'system',  -- user | pipeline | ai | system
  actor_id      UUID,                     -- the user, when known
  event_id      UUID NOT NULL,            -- source outbox/event id → idempotent consume
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(entity_id, revision_num),
  UNIQUE(entity_id, event_id)             -- at-least-once redelivery never double-writes
);
CREATE INDEX idx_er_entity ON entity_revisions(entity_id, revision_num DESC);
-- Partition by created_at (monthly) for cheap archival of cold revisions (§9).
```

The `snapshot` reuses the **exact JSONB** `recalculate_entity_snapshot` already builds (kind, status,
alive, tags, attributes → original_value + translations + evidences). No new serialization — the
consumer copies the entity's current `entity_snapshot`.

## 4. Capture mechanism (VG-1) — async projection off the outbox

**No sync trigger on the write path.** The glossary write paths already emit a transactional
`glossary.entity_updated` outbox row (`outbox.go`), relayed by worker-infra to the Redis stream
`loreweave:events:glossary` (the same stream the translation M5c staleness consumer reads). A **new
revision-projection consumer** (owned by glossary-service — it owns the data) reads that stream and
materializes revisions out-of-band:

```
glossary write txn ──▶ outbox(glossary.entity_updated) ──▶ relay ──▶ Redis stream
                                                                        │
                                          (NEW: revision projection consumer, async)
                                                                        ▼
                          actor=user?  ──no──▶ skip (or keep rolling last-N for machine)
                                │ yes
                                ▼
              read entity's current entity_snapshot ──▶ INSERT entity_revisions (next revision_num)
```

- **Hot write path cost for history = zero.** No extra INSERT in the write transaction, no trigger;
  the outbox event already exists for other consumers (M5c, knowledge re-merge).
- **Actor-granularity at the consumer:** the event payload carries `actor_type`. `user` → always
  capture. `pipeline`/`system`/bulk → **skip**, or keep a **rolling last-N** per entity (a cheap
  `DELETE … WHERE revision_num < max-N AND actor_type='pipeline'`). Machine writes are reproducible,
  so their history is low-value + high-volume → not worth unbounded capture.
- **Snapshot source:** the consumer reads the entity's *current* `entity_snapshot` column (already
  materialized in the write txn). For human edits (rare, never rapid-fire on one entity) the ~1s
  projection lag carries no race risk. (If we later want exact-at-commit fidelity under bursts, the
  outbox payload can carry the snapshot inline — deferred; fetch-on-user-edit is simplest.)
- **`revision_num`** assigned by the consumer: `COALESCE(MAX(revision_num),0)+1` per entity. The
  consumer is single-writer per entity stream (ordered) → no contention.
- **Idempotency:** the consumer dedups on the outbox/event id (the stream is at-least-once) →
  `ON CONFLICT (entity_id, event_id) DO NOTHING` (add `event_id` to the table) so a redelivery
  never double-writes a revision.
- Soft-deletes (`deleted_at`/`status`) emit `entity_updated` too → a `delete` revision is captured;
  the row remains (FK intact) → **restore re-activates it.**

The consumer mirrors the **proven M5c Redis-Streams consumer** essentials (consumer group, pending
drain, `id="$"` forward-only on first start, ack + retry cap) — `services/translation-service/app/
events/glossary_consumer.py` is the reference pattern (here it lives in glossary-service / Go, or a
worker).

## 5. Restore (VG-2)

`POST /v1/glossary/books/{book_id}/entities/{entity_id}/restore  {revision_id}` (Go handler, txn):
1. Load the target revision's `snapshot`.
2. Re-materialize the live child tables to match: UPDATE `glossary_entities` (status/alive/tags) +
   reconcile `entity_attribute_values` + `attribute_translations` + `evidences` to the snapshot,
   **preserving ids from the snapshot** so `evidences`/`chapter_entity_links`/Neo4j anchors stay
   valid. (The main implementation nuance — reconcile, don't blind-delete-reinsert, to keep FKs.)
3. The reconcile is itself a change → the capture trigger records a new `restore` revision (so a
   restore is undoable too).
4. Emit `glossary.entity_updated` (downstream sync / M5c staleness / knowledge re-merge).

Reads:
- `GET …/entities/{entity_id}/revisions` → list (revision_num, op, actor, created_at, compact preview).
- `GET …/entities/{entity_id}/revisions/{revision_id}` → full snapshot (for view/diff).

## 6. Frontend (VG-3) — React MVC

- `features/glossary/hooks/useEntityRevisions.ts` (list/get) + `useRestoreEntity.ts` (restore +
  invalidate the entity-detail query).
- `components/EntityHistoryPanel.tsx` — revision list (num, op, actor, relative time), "View" +
  "Restore" (ConfirmDialog: "restore to revision N? current state is saved as a new revision").
- Wire into the glossary entity editor (a "History" tab/drawer). i18n ×4 locales.

## 7. Migration + backward-compat

- Additive: new table + a new projection consumer wired into the glossary-service lifespan (best-
  effort bg task, like the M5c consumer). **No change to existing write/read paths** — history is a
  pure downstream projection.
- **Outbox payload:** verify `glossary.entity_updated` carries `actor_type` (and entity_id +
  event_id). If `actor_type` is absent, add it to the emit (a small write-path change) so the
  consumer can apply actor-granularity; default `system`.
- **Backfill (optional):** seed a `revision_num=1` `create` revision for every existing entity from
  its current `entity_snapshot`, so pre-existing entities have a baseline to restore toward.

## 8. Slices

- **VG-1 (BE)** — `entity_revisions` table (migration) + the **revision-projection consumer** off
  `loreweave:events:glossary` (idempotent on `event_id`, actor-granularity: user→capture,
  machine→skip/rolling-N) + ensure the outbox event carries `actor_type` + backfill + tests (capture
  on user edit; skip on pipeline; idempotent redelivery; rolling-N prune). DB-integration vs live DB.
- **VG-2 (BE)** — history list/get + restore endpoints (reconcile-apply, id-preserving) + outbox emit
  + tests (restore round-trips a value; restore is itself versioned; verified data integrity).
- **VG-3 (FE)** — history panel + restore UI + i18n + vitest.

After VG-1/2 land, **unblock D-TRANSL-M4D-2B** (its machine overwrite is now recoverable; and because
2b's writeback is `actor_type=pipeline`, those overwrites are throttled/skipped in history per §4 —
exactly the high-volume-machine case the granularity rule targets).

## 9. Risks
- **Projection lag / loss** — async ⇒ a revision lands ~1s after the change, and a consumer outage
  could miss events. Mitigate: durable consumer group (ack after write, pending-drain on restart) so
  events aren't lost across restarts; the data itself is never at risk (history is supplementary).
- **Restore id-reconciliation** — the real complexity (VG-2); must preserve `attr_value_id`/
  `translation_id` so evidences/chapter-links/Neo4j anchors don't dangle. Reconcile (upsert/prune),
  never blind delete+reinsert.
- **Volume at scale** — bounded by actor-granularity (human-edit count, not machine-write count) +
  **monthly partition** of `entity_revisions` + **archival of cold partitions to object storage**
  (keep recent N hot in PG; cold still restorable, off the hot index).
- **Actor attribution** — depends on the outbox event carrying `actor_type`; absent → `system`
  (captured but not granularity-filtered; degrade, not break).
