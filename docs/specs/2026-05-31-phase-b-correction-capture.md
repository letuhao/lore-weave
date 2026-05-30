# DESIGN — Phase B: Axis-1 correction capture (learning-service + correction event spine)

**Date:** 2026-05-31 · **Status:** DESIGN (no code; checkpoint-commit artifact) · **Workflow:** AMAW · **Size:** XL
**Plan ref:** [`docs/plans/2026-05-31-extraction-accuracy-and-eval-plan.md`](../plans/2026-05-31-extraction-accuracy-and-eval-plan.md) §2.1 / §4 (Phase B)
**Cycle:** session 75 · Builds on session 74 (production ship-ready; eval hygiene Phase A done)

---

## 0 · Scope (locked with PO at CLARIFY)

This cycle = the **Axis-1 correction CAPTURE spine** + the **user edit surfaces that produce relation/event corrections**. PO chose the maximal scope on three forks:

| Fork | Decision |
|---|---|
| Relation/event corrections (no edit endpoint exists today) | **Build** new user-facing relation + event edit/correct endpoints (BE + FE) + outbox emission |
| Corrections store location | **New dedicated microservice** `learning-service` (Python/FastAPI), owns `loreweave_learning` DB |
| This session's stop point | **DESIGN → AMAW review → checkpoint-commit.** No BUILD this session. |

### In scope (Phase B)
1. New `learning-service` (Python/FastAPI): `corrections` table + Redis-Streams consumer + read/query API + gateway route + compose/infra.
2. glossary-service: **additively** enrich `glossary.entity_updated` with `actor_type`/`actor_id` + `before`/`after` (add SELECT-old on PATCH). Backward-compatible — existing knowledge-service consumer ignores new fields.
3. knowledge-service: add a **Postgres transactional-ish outbox** (new for KS) + emit `knowledge.entity_corrected` on its existing user entity edits (PATCH / merge-into / archive).
4. knowledge-service: **build new user-facing relation correction** endpoints (wire the unused `invalidate_relation` + `create_relation`) → emit `knowledge.relation_corrected`.
5. knowledge-service: **build new user-facing event correction** primitives + endpoints (`update_event_fields` / `archive_event`, add `version` to `:Event`) → emit `knowledge.event_corrected`.
6. worker-infra: add `knowledge` to `OUTBOX_SOURCES` + (optional) `learning` if learning-service ever emits.
7. Frontend `features/knowledge`: relation-edit + event-edit UI (mirror `EntityEditDialog` + `useEntityMutations`).

### Explicitly OUT of scope (deferred, tracked)
- **Tier-1 anchor reuse** (corrections → next-extraction anchor index). Per plan §4 sequencing this is **Phase C** (`depends_on: B`). The handoff conflated it into B; we keep B = capture only. → **D-PHASE-C-TIER1-ANCHOR-CONSUME**.
- **Axis-2 config telemetry** (`config_registry`, `config_adjustment_events`, `extraction_runs`). That is **Phase B2**. We **reserve the names/DB** in learning-service this cycle (per "reserve operation names early" lesson) but create no B2 tables. → **D-PHASE-B2-CONFIG-TELEMETRY**.
- Few-shot injection (Tier 2 / Phase D), organic-gold metric migration (Tier 3 / Phase E), fine-tune (Phase F).
- Correction quality/agreement gate before a correction becomes eval-gold (plan §5). Capture now; gating is a Tier-3 concern.

---

## 1 · CLARIFY findings that shaped this design (plan-vs-code divergences)

Three places where the plan's prose assumed code that does not exist:

1. **No actor signal on the wire.** `glossary.entity_updated` fires on **user CREATE** (`POST .../entities`, JWT), **user PATCH** (`PATCH .../entities/{id}`, JWT) **and pipeline bulk** (`POST /internal/.../extract-entities`, internal-token). The route middleware distinguishes user-vs-pipeline (JWT vs `X-Internal-Token`) but the payload (`entityEventPayload`, [outbox.go:46-56](../../services/glossary-service/internal/api/outbox.go)) carries **no actor field**, and `op` ("created"/"updated") does not separate user create from pipeline create. → must thread actor through the 3 emit sites.
2. **`invalidate_relation` is unwired; events have no edit primitive at all.** [relations.py:633](../../services/knowledge-service/app/db/neo4j_repos/relations.py) `invalidate_relation` has **zero production callers** (tests only). [events.py](../../services/knowledge-service/app/db/neo4j_repos/events.py) has `merge_event` only — **no** `update_event` / `archive_event` / `invalidate_event`, and `:Event` has **no `version`** field for If-Match. There is **no user-facing path to correct a relation or event** today. → the "edits → outbox" task requires first building the edits.
3. **knowledge-service has no outbox.** It is consumer-only (not in `OUTBOX_SOURCES`); the graph (entities/relations/events) lives in **Neo4j**, while the outbox table must be **Postgres** → the KS "transactional outbox" cannot be truly atomic with the graph write (see §6.4 cross-store decision).

Also confirmed (reduces risk):
- glossary `outbox_events` + pg_notify trigger + worker-infra relay are solid; the relay keys the Redis stream off the **`aggregate_type` column** (`loreweave:events:{aggregate_type}`), one relay polls many DBs via `OUTBOX_SOURCES`.
- KS already has a robust Redis-Streams consumer (`consumer.py`: group, pending catch-up, DLQ→`dead_letter_events`, retry counter) to clone for learning-service.
- KS user entity edits already set `user_edited=true` and use a clean If-Match/428/412 ETag pattern in [entities.py:52-78](../../services/knowledge-service/app/routers/public/entities.py).

---

## 2 · Architecture — the correction event spine

```
                         ┌──────────────────────────────────────────────┐
 USER edits an entity →  │ glossary-service (Go)                         │
   POST/PATCH /entities  │  outbox_events (PG, aggregate_type='glossary')│──┐
                         │  glossary.entity_updated (ENRICHED: actor,    │  │
                         │   before/after)                                │  │
                         └──────────────────────────────────────────────┘  │
                                                                            │
 USER edits entity/      ┌──────────────────────────────────────────────┐  │
  relation/event in   →  │ knowledge-service (Py)                         │  │
   the memory UI         │  Neo4j write (graph SoT)                       │  │
                         │  + outbox_events (PG, aggregate_type='knowledge')│─┤
                         │  knowledge.entity_corrected / .relation_corrected│ │
                         │  / .event_corrected                            │  │
                         └──────────────────────────────────────────────┘  │
                                                                            │
                         ┌──────────────────────────────────────────────┐  │
                         │ worker-infra outbox-relay (ONE instance)      │  │
                         │  OUTBOX_SOURCES += knowledge:<dsn>            │◄─┘
                         │  ships PG rows → Redis Stream                 │
                         │   loreweave:events:{aggregate_type}           │
                         └───────────────┬──────────────────────────────┘
                                         │ XADD
              loreweave:events:glossary  │  loreweave:events:knowledge
                                         ▼
                         ┌──────────────────────────────────────────────┐
                         │ learning-service (Py, NEW)                    │
                         │  consumer group "learning-collector"          │
                         │  handler: filter actor=='user' (glossary) +   │
                         │   all knowledge.*_corrected → derive diff_class│
                         │   → INSERT corrections (PG loreweave_learning) │
                         │   idempotent on (origin_service, origin_event) │
                         │  read API: GET /v1/learning/corrections        │
                         │  DLQ: dead_letter_events                       │
                         └──────────────────────────────────────────────┘
                                         ▲
                         api-gateway-bff  │  /v1/learning/* → learning-service:8094
```

**Why this shape:**
- **Reuse the established outbox→relay→stream→consumer pipeline** (resilient, replayable, idempotent) rather than direct service-to-service HTTP. glossary already emits; KS gains a Postgres outbox; the single relay picks up the new source by config alone (no relay code change).
- **learning-service is a pure consumer + read API** this cycle (it does not emit). It owns the corrections SoT and is the forward home for B2 telemetry + organic-gold assembly.
- **diff classification computed in ONE place** (learning-service consumer, which holds before+after) — emitters stay dumb and we avoid drift between glossary's Go classifier and KS's Python one.

---

## 3 · Data model — `corrections` (learning-service / `loreweave_learning`)

Idempotent DDL string in `learning-service/app/db/migrate.py` (chat-service house style; no Alembic).

```sql
CREATE TABLE IF NOT EXISTS corrections (
  id                        UUID PRIMARY KEY DEFAULT uuidv7(),
  -- tenancy (strict per-user isolation; project optional)
  user_id                   UUID NOT NULL,   -- the CORPUS OWNER (tenancy key) — see note below
  project_id                UUID,
  book_id                   UUID,
  -- what was corrected
  target_type               TEXT NOT NULL,   -- entity|relation|event|attribute|alias|wiki_suggestion
  target_id                 TEXT NOT NULL,    -- glossary_entity_id | neo4j canonical id | relation_id | event_id
  op                        TEXT NOT NULL,    -- create|update|rename|rekind|merge|split|delete|invalidate|predicate_fix|accept|reject
  -- PRIVACY SPLIT (R2: redact-by-default — NO raw novel text persisted in Phase B):
  before_structural         JSONB,            -- controlled-vocab / non-content fields only (kind, predicate, ids,
  after_structural          JSONB,            --   valid_until, confidence). null = whole-snapshot absent.
  before_content_hash       TEXT,             -- SHA-256 of the CONTENT fields (name/aliases/summary/title/time_cue)
  after_content_hash        TEXT,             --   — leak-safe, dedup-able, minable cross-tenant. NULL when no content.
  before_content            JSONB,            -- RESERVED, NULL in Phase B. Raw content only when a tenant opts into
  after_content             JSONB,            --   raw retention (Phase E gold) — see note. Strictly owner-isolated.
  diff_class                TEXT,             -- kind-change|boundary|spurious-drop|missing-add|predicate-fix|merge|other (derived)
  -- provenance (links the correction back to the run that produced the original)
  source_extraction_run_id  UUID,             -- nullable until B2 extraction_runs exists
  source_chapter            TEXT,
  source_span               JSONB,            -- {start,end} or null
  -- actor
  actor_type                TEXT NOT NULL,    -- user (pipeline rows are NOT persisted as corrections)
  actor_id                  UUID,
  -- capture provenance / idempotency
  origin_service            TEXT NOT NULL,    -- glossary|knowledge
  origin_event_id           TEXT NOT NULL,    -- = the producer's OUTBOX ROW id (uuidv7), carried on the
                                              --   stream via the new XADD `outbox_id` field (§4.0). NOT
                                              --   aggregate_id (that is the target id, reused per edit — F2),
                                              --   and NOT the Redis message_id (changes on relay re-emit — F1).
  origin_event_type         TEXT NOT NULL,    -- glossary.entity_updated | knowledge.*_corrected
  emitted_at                TIMESTAMPTZ,      -- producer timestamp
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT corrections_origin_uniq UNIQUE (origin_service, origin_event_id)
);
CREATE INDEX IF NOT EXISTS idx_corrections_user_project ON corrections(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_corrections_target       ON corrections(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_corrections_diff_class   ON corrections(diff_class) WHERE diff_class IS NOT NULL;

-- DLQ for the consumer (cloned from knowledge-service)
CREATE TABLE IF NOT EXISTS dead_letter_events ( ... );  -- verbatim from KS migrate.py
```

**Idempotency:** consumer does `INSERT ... ON CONFLICT (origin_service, origin_event_id) DO NOTHING`. Stream redelivery (consumer crash before XACK) is safe.

**Tenancy `user_id` vs `actor_id` (review-impl LOW-4).** Today all edits are **owner-only** — glossary `verifyBookOwner` ([entity_handler.go:340/467/653/686/847](../../services/glossary-service/internal/api/entity_handler.go)) and the per-`user_id` KS graph — so `user_id == actor_id` always. `corrections.user_id` is defined as the **corpus owner** (the tenancy/eval-gold key); `actor_id` is the editor. sharing-service is read-visibility only today, so they never diverge. **If write-collaboration is ever added**, they split and the read-API scoping (`WHERE user_id=JWT.sub`) must be revisited (an editor seeing their own correction on someone else's corpus). Documented so that feature doesn't silently break the read path.

**Reserved for B2 (NOT created this cycle — documented so the schema is forward-shaped):** `config_registry(config_hash PK, resolved_config JSONB, base_default_version)`, `config_adjustment_events(...)`, `extraction_runs(run_id, config_hash, outcome, ...)`. `corrections.source_extraction_run_id` is the forward FK to `extraction_runs`.

**Snapshot schema — PINNED per `target_type`, split STRUCTURAL vs CONTENT** (review-impl MED-2 "pin the mirrored contract" + R2 redact-by-default). Go-glossary and Python-KS MUST emit the identical shape. The emitter classifies each field; the consumer stores `*_structural` raw, hashes the content concatenation into `*_content_hash`, and does **NOT** persist raw content in Phase B:
| target_type | STRUCTURAL (stored raw) | CONTENT (hashed only) |
|---|---|---|
| entity | `kind` | `name, aliases[], short_description` |
| relation | `subject_id, object_id, predicate, confidence, valid_until` | *(none — endpoint ids are structural)* |
| event | `event_date_iso` | `title, summary, time_cue, participants[]` |
`null` whole-snapshot = absence (create→before null; delete→after null). A relation/event has no `kind` → diff_class `kind-change` is guarded on `target_type=='entity'`.

**diff_class works entirely on structural + hash (no raw content needed):** `kind-change` reads structural `kind`; `predicate-fix` reads structural `predicate`; `boundary` (name changed, kind same) = `before_content_hash != after_content_hash` while structural `kind` equal; `missing-add`/`spurious-drop` = whole-snapshot null; `merge` = `op`. So redaction does **not** break classification.

> **R2 redact tradeoff (explicit, PO-chosen).** Phase B persists **no raw novel text** — only structural fields + content hashes (leak-safe by construction; few-shot/fine-tune cross-tenant mining uses structural+hash). **Consequence:** Tier-3 organic eval-gold (plan §2.2.3 / Phase E) needs the *raw* before/after text → it requires a **per-tenant raw-retention opt-in** that populates `before_content`/`after_content` (reserved, NULL now), strictly owner-isolated + retention-bounded. Until a tenant opts in, their corrections feed Tiers 1/2 (anchor/few-shot via hashes + structural) but cannot become raw gold. → **D-PHASE-E-RAW-CONTENT-OPTIN**.

**Diff-class derivation (consumer, from before/after).** Evaluated **top-to-bottom; `op` is authoritative and checked FIRST** (F6, Adversary r2 — otherwise a merge whose merged-away side has `after=null` mis-classes as `spurious-drop`, and a rename+rekind drops the rename signal). Compound entity edits (rename AND rekind) resolve to `kind-change` by design (the kind change is the higher-signal correction); pin this precedence:
| Order | Condition (structural + hash only — no raw content) | diff_class |
|---|---|---|
| 1 | `op` ∈ {merge, split} | `merge` |
| 2 | `op` == predicate_fix OR (relation & structural `predicate` changed) | `predicate-fix` |
| 3 | `before_structural` null & `after_structural`/`after_content_hash` present | `missing-add` |
| 4 | `after_structural` null & `after_content_hash` null (delete/invalidate) | `spurious-drop` |
| 5 | entity & `before_structural.kind != after_structural.kind` | `kind-change` (wins over rename on compound edits) |
| 6 | entity & `kind` equal & `before_content_hash != after_content_hash` (name/alias changed) | `boundary` |
| 7 | else | `other` |

---

## 4 · Event contracts

### 4.0 · Relay change — carry the outbox row id on the stream (F1/F2 fix — REQUIRED, platform-wide)

**Found by Adversary r1 (BLOCK).** The shared worker-infra relay ([outbox_relay.go:155-165](../../services/worker-infra/internal/tasks/outbox_relay.go)) currently XADDs only `event_type`, `aggregate_id`, `payload`, `source` — it scans the outbox row `id` (`idStr`, line 149) but **never puts it on the stream**. So:
- **No consumer can dedup a relay re-emission** (relay XADDs, then best-effort `UPDATE published_at` line 180; a crash between them re-selects the row → a *new* Redis `message_id` for the same logical event). The Redis `message_id` only dedups consumer-side redelivery, not relay re-emit.
- `aggregate_id` is the **target node id** (reused on every edit of that target, [outbox.go:146-148](../../services/glossary-service/internal/api/outbox.go)) → cannot be the dedup key (F2: would `ON CONFLICT`-drop the 2nd+ correction of every entity — and the *sequence* of corrections is the entire value).

**Fix (additive, backward-compatible, benefits every consumer):** add `"outbox_id": idStr` to the relay XADD `Values` map ([outbox_relay.go:159-164](../../services/worker-infra/internal/tasks/outbox_relay.go)). The outbox row `id` is **stable across relay re-emissions of the same row** (it's the PK), so `(origin_service, outbox_id)` is a correct end-to-end idempotency key. Existing consumers ignore the new field. In-scope for Phase B; lands in BUILD sub-session A.

**N-place sync — ALL 5 points MUST change together (F4, Adversary r2; "new field = N-place sync, <N hits = orphan" lesson). Missing any one defaults `origin_event_id` to `""` → `ON CONFLICT (origin_service, origin_event_id)` collapses every correction to one row — re-introducing the exact F2 bug:**
1. **Producer:** relay XADD `Values` gains literal key `"outbox_id": idStr` — [outbox_relay.go:159-164](../../services/worker-infra/internal/tasks/outbox_relay.go).
2. **Dataclass:** `outbox_id: str = ""` field on `EventData` — **[dispatcher.py:19-28](../../services/knowledge-service/app/events/dispatcher.py)** (NOT consumer.py — that file only *constructs* EventData).
3. **Parser:** `outbox_id=fields.get("outbox_id", "")` in `_parse_event` — [consumer.py:252-260](../../services/knowledge-service/app/events/consumer.py) (the literal `"outbox_id"` must match the relay key byte-for-byte).
4. **Clone:** the learning-service consumer/dispatcher are cloned from KS → carry the same two changes.
5. **Reader:** learning-service handler fills `corrections.origin_event_id = event.outbox_id`. **R3-W1 (Adversary r3) — fail loud, never silent:** if `outbox_id` is empty/missing (relay rolled out without the Python side, or a rollback desync), the handler MUST route to DLQ / raise, **NOT** `INSERT` with `""` (an empty key + `ON CONFLICT` would silently collapse every correction to one row per service — the exact F2 catastrophe). The dataclass default `= ""` is only for constructor back-compat; the *reader* treats `""` as a hard error.
- **Test gate:** grep `outbox_id` across the repo → expect ≥5 hits before VERIFY passes (orphan-detection per lesson). Plus a lock: "empty `outbox_id` → DLQ/error, not a silent collapse."

> Net: `corrections.origin_event_id := EventData.outbox_id`. NOT `aggregate_id` (target id, reused per edit), NOT `message_id` (changes on relay re-emit).
>
> **Why the wire, not `event_log`:** the relay already writes `event_log(source_service, source_outbox_id)` with a `UNIQUE` constraint ([outbox_relay.go:173-177](../../services/worker-infra/internal/tasks/outbox_relay.go)) — but `event_log` lives in **worker-infra's** events DB, not reachable from learning-service. The Redis-wire `outbox_id` is the clean cross-service channel; `event_log` stays the relay's own internal re-emit guard. Deliberately parallel, not redundant.

### 4.1 `glossary.entity_updated` — enriched (ADDITIVE, backward-compatible)

Add to `entityEventPayload` ([outbox.go](../../services/glossary-service/internal/api/outbox.go)). Existing KS glossary_sync consumer reads only the old fields → unaffected.

```go
// NEW fields appended:
ActorType  string          `json:"actor_type"`            // "user" | "pipeline"
ActorID    string          `json:"actor_id,omitempty"`    // user UUID (empty for pipeline)
Before     *EntitySnapshot `json:"before,omitempty"`      // null on create
After       *EntitySnapshot `json:"after,omitempty"`
// EntitySnapshot = {name, kind, aliases[], short_description}
```

- **CREATE** (transactional path, `emitEntityUpdatedTx`): `actor_type="user"`, `actor_id=<jwt sub>`, `before=null`, `after=<created snapshot>`.
- **PATCH** (`emitEntityUpdated`): `actor_type="user"`, `actor_id=<jwt sub>`, `before=<old snapshot>`, `after=<new snapshot>`. **Requires a SELECT-old before the UPDATE** (handler currently does a blind UPDATE — add it; capture old `cached_name/cached_aliases/short_description/kind`).
- **BULK extract** (`insertEntityOutboxEvent` inline): `actor_type="pipeline"`, `actor_id=""`, `before`/`after` omitted. learning-service **does not persist pipeline rows as corrections** (they are the original output, relevant to B2 runs, not Axis-1).

> **Decision:** keep one event type (per plan §2.1 "enrich `glossary.entity_updated`"), do NOT add a separate `glossary.entity_corrected`. learning-service filters on `actor_type=="user"`.
>
> **Redaction happens at the CONSUMER, not the emitter (R2).** Emitters (glossary Go, KS Python) put the FULL before/after snapshot (structural + content) on the wire — keeps emitters simple and preserves the future opt-in path. The **learning-service consumer performs the privacy split**: store `*_structural` raw, SHA-256 the content fields into `*_content_hash`, **discard raw content** (do not write `*_content`) unless the tenant has opted into raw retention (Phase E). **Content-exposure note:** content therefore transits + is retained *transiently* in the outbox / `event_log` / Redis stream (internal infra, bounded retention) — only the durable *analytical* store (`corrections`) is redacted. The replay-retention knob (§10.1) and the content-transport-exposure window are **the same knob**; documented tension, accepted (transport is internal + access-controlled).

### 4.2 New `knowledge.*` correction events (KS Postgres outbox)

Common payload core (mirrors `corrections` columns):
```json
{
  "user_id": "...", "project_id": "...", "book_id": "...",
  "target_type": "entity|relation|event", "target_id": "...",
  "op": "...", "before": {...}|null, "after": {...}|null,
  "source_chapter": "...", "source_span": {...}|null,
  "actor_type": "user", "actor_id": "...",
  "emitted_at": "RFC3339"
}
```
| event_type | emitted by | op values |
|---|---|---|
| `knowledge.entity_corrected` | PATCH `/v1/knowledge/entities/{id}`, merge-into, DELETE(archive) | `update`/`rename`/`rekind`/`merge`/`delete` |
| `knowledge.relation_corrected` | new relation correct endpoint | `invalidate`/`predicate_fix`/`update` |
| `knowledge.event_corrected` | new event correct endpoint | `update`/`delete` |

`aggregate_type='knowledge'` on every KS outbox row → relay ships to `loreweave:events:knowledge`.

---

## 5 · glossary-service changes (Go)

1. `entityEventPayload` + `EntitySnapshot` struct (§4.1); `buildEntityEventPayload` gains actor + before/after params.
2. `createEntity` ([entity_handler.go:330](../../services/glossary-service/internal/api/entity_handler.go)): pass `actor_type="user"`, `actor_id=userID`, `after=<snapshot>` to the tx emit.
3. `patchEntity` ([entity_handler.go:672](../../services/glossary-service/internal/api/entity_handler.go)): **add `SELECT` of the old row** (name/kind/aliases/short_description) before the `UPDATE`; pass `before`/`after` + actor to the best-effort emit.
4. `bulkExtractEntities` ([extraction_handler.go:372](../../services/glossary-service/internal/api/extraction_handler.go)): pass `actor_type="pipeline"`.
5. Unit tests: `buildEntityEventPayload` actor/before/after permutations; `patchEntity` before-snapshot capture; bulk → pipeline.

**Risk:** PATCH SELECT-old adds one query to a user write path — negligible, and the row is already locked by the subsequent UPDATE within the request. Do the SELECT in the **same tx** as the UPDATE to avoid a TOCTOU before/after skew (currently PATCH is not transactional — wrap it).

---

## 6 · knowledge-service changes (Python)

### 6.1 New Postgres outbox (`app/db/migrate.py`)
Append `outbox_events` (verbatim from glossary/chat shape, `aggregate_type DEFAULT 'knowledge'`) + `idx_outbox_pending`. KS gains its first outbox.

### 6.2 Emit helper (`app/events/outbox_emit.py`, new)
`emit_correction(pool, *, event_type, payload) -> None` — best-effort `INSERT INTO outbox_events(...)`, wrapped in try/except, logs on failure (cross-store; see 6.4).

### 6.3 Entity correction emission (existing endpoints)
[entities.py](../../services/knowledge-service/app/routers/public/entities.py): after a successful Neo4j edit in `patch_entity`, `merge_entity_into`, `archive_user_entity`, call `emit_correction(...)` with before/after. **`update_entity_fields` must return the pre-edit snapshot via SAME-Cypher capture** — `WITH e, {name:e.name, kind:e.kind, aliases:e.aliases, short_description:e.short_description} AS before SET e.name=... RETURN before, properties(e) AS after`. **Do NOT read-before-write in the handler** (review-impl MED-3: a concurrent edit between the read and the SET corrupts the captured `before` — TOCTOU). Same discipline as the glossary PATCH (which we move into a tx for the same reason, §5).

### 6.4 Relation correction — new endpoints (new router `app/routers/public/relations.py`)
Model = **invalidate-then-recreate** (relation_id is derived from `(user,subj,pred,obj)`, so a predicate/endpoint change is structurally a new edge — confirmed in repo).
- `GET /v1/knowledge/relations/{relation_id}` → `get_relation` (read for the FE).
- `POST /v1/knowledge/relations/{relation_id}/invalidate` → `invalidate_relation` (op=`invalidate`, after=null, diff=spurious-drop). The user "this relation is wrong" action.
- `POST /v1/knowledge/relations/correct` → `invalidate_relation(old)` + `create_relation(new, source_type="manual", confidence=1.0, pending_validation=false)` (op=`predicate_fix`). before=old edge, **after=the edge RE-READ via `get_relation` after the write (NOT the request payload)**.
- Auth: `Depends(get_current_user)`, user_id scoping, 404 on cross-user.
- Each success → `emit_correction(event_type="knowledge.relation_corrected", ...)`.

> **F3 fix (Adversary r1 WARN) — predicate-fix identity collision.** `relation_id` hashes `(user, subject, predicate, object)` and `create_relation` MERGEs with **ON MATCH** semantics that do **NOT clear `valid_until`** ([relations.py:183-197](../../services/knowledge-service/app/db/neo4j_repos/relations.py)). So re-pointing a correction onto a tuple that already exists — especially one previously **invalidated** — silently MERGEs onto that dead/foreign edge instead of producing a fresh "after". Two defects: (a) the captured `after` would describe a still-`valid_until`-set edge; (b) the graph shows a "corrected" relation that is actually invalid. **Mitigation:** the correct path must (1) compute the new `relation_id` and check for a pre-existing edge; (2) when recreating onto a previously-invalidated tuple, **explicitly clear `valid_until`** (resurrect); (3) always capture `after` from a post-write `get_relation`, never from the request.
>
> **F5 (Adversary r2 BLOCK) — the resurrect MUST NOT touch the extraction path.** `create_relation` is on the hot extraction path — [pass2_writer.py:478](../../services/knowledge-service/app/extraction/pass2_writer.py) and [pattern_writer.py:271](../../services/knowledge-service/app/extraction/pattern_writer.py) call it per re-extracted SVO, and its ON-MATCH **deliberately preserves `valid_until`** (the temporal invariant in the [relations.py:13-19](../../services/knowledge-service/app/db/neo4j_repos/relations.py) module docstring). If we cleared `valid_until` on ON MATCH, a Pass-2 re-extraction that re-mentions a **user-invalidated SVO would silently resurrect the dead edge back into L2/RAG — undoing the user's correction.** → **REQUIRED:** add a **dedicated `recreate_relation`** (or a `resurrect: bool` param that is **structurally absent from the extraction call signatures**); do **NOT** extend the shared `create_relation` ON MATCH. **Two regression-locks:** (1) correct onto a previously-invalidated tuple → edge has `valid_until IS NULL`, `after` read post-write; (2) **Pass-2 re-extraction of a user-invalidated SVO leaves `valid_until` NON-null** (proves the extraction path can't resurrect). Audit both extraction call sites explicitly at BUILD.
>
> **BUILD-time pins (Adversary r3 WARN, not blocking):** (R3-W2) `recreate_relation` is a NEW Cypher — it does NOT inherit `create_relation`'s max-confidence / `pending_validation` ON-MATCH CASE; the manual path uses `confidence=1.0` so this is safe, but a resurrected edge inherits **stale `source_event_ids`** from the prior extraction → the post-write `after` shows stale provenance (decide: keep, or stamp manual provenance). (R3-W3) a `relation_corrected` op=`update` with predicate UNCHANGED correctly lands in `other`, NOT `boundary` — do **not** add a relation-boundary branch (boundary is entity-name-only by design).

> **`source_type="manual"`** is in the provenance Literal but currently unused — this is its first producer (a user-authored relation). Good fit.

### 6.5 Event correction — new primitives + endpoints
Repo ([events.py](../../services/knowledge-service/app/db/neo4j_repos/events.py)) gains:
- `version` property on `:Event` (ON CREATE `version=1`; bump `coalesce(version,1)+1` on edit) — mirrors entities, enables If-Match.
- `update_event_fields(session, *, user_id, event_id, title?, summary?, time_cue?, event_date_iso?, expected_version) -> Event | None` (raises `VersionMismatchError`).
- `archive_event(session, *, user_id, event_id, reason) -> Event | None` (set `archived_at`; nothing sets it today).
- New router `app/routers/public/events.py` (or extend `timeline.py`): `PATCH /v1/knowledge/events/{id}` (If-Match/428/412), `DELETE /v1/knowledge/events/{id}` (archive). Each → `emit_correction("knowledge.event_corrected", ...)`.
- Extract the duplicated `_parse_if_match`/`_etag` helpers into a shared module (`app/routers/public/_etag.py`) instead of a 3rd copy.

### 6.6 Cross-store atomicity decision (KEY)
The graph edit is in **Neo4j**; the outbox row is in **Postgres** → **no true transactional outbox is possible**. Decision: **Neo4j write is the source of truth; the Postgres outbox insert is best-effort post-success, wrapped in try/except** (mirrors glossary's patch/bulk best-effort emit + my "cross-store best-effort writes need try/except" lesson). A dropped outbox row loses **one correction-log entry** (analytics/eval-gold input), never corrupts the graph. Residual risk: corrections-log under-counts on Postgres hiccup. **Mitigation (Phase-B-acceptable):** log at WARN; a future reconciliation sweep (compare `user_edited`/`updated_at` Neo4j nodes vs corrections rows) is a deferred hardening → **D-PHASE-B-CORRECTION-RECONCILE**. Acceptable because Tier-3 gold already requires an agreement/confidence gate.

### 6.7 Consumer/handlers
No new KS consumer work (KS still consumes glossary for glossary_sync; unchanged). KS only gains the **emit** side.

---

## 7 · learning-service (NEW, Python/FastAPI)

Clone chat-service shell + knowledge-service consumer.
```
services/learning-service/
  Dockerfile  (PORT=8094; no sdks/python unless LLM calls — none this cycle)
  requirements.txt  (fastapi, uvicorn, asyncpg, pydantic, pydantic-settings, redis, PyJWT, httpx)
  app/
    main.py        (lifespan: pool → migrate → start consumer task; /health; /v1/learning router)
    config.py      (LEARNING_DB_URL, REDIS_URL, JWT_SECRET, INTERNAL_SERVICE_TOKEN)
    db/{pool.py, migrate.py}      (corrections + dead_letter_events DDL)
    events/{consumer.py, dispatcher.py, handlers.py}   (cloned; group "learning-collector")
    routers/corrections.py        (read API)
```
- **Consumer** subscribes `loreweave:events:glossary` + `loreweave:events:knowledge`, group `learning-collector` (distinct from KS's `knowledge-extractor` so both services see all messages). Handlers:
  - `glossary.entity_updated`: if `actor_type=="user"` → upsert correction; else ignore (ACK).
  - `knowledge.entity_corrected|relation_corrected|event_corrected` → upsert correction.
  - derive `diff_class` (§3), `INSERT ... ON CONFLICT DO NOTHING`.
- **Read API** (gateway `/v1/learning/*`, JWT, user-scoped):
  - `GET /v1/learning/corrections?project_id=&target_type=&diff_class=&limit=&cursor=` → user's own corrections (strict `user_id` filter from JWT). Cursor pagination (peek-ahead + separate `rowsScanned`, per my pagination lesson).
  - `GET /v1/learning/corrections/stats?project_id=` → counts by diff_class/target_type (feeds the future eval-gold/few-shot tiers).
  - Internal: none this cycle.

---

## 8 · Frontend (`frontend/src/features/knowledge`)

Mirror the existing `EntityEditDialog` + `useEntityMutations` + `ifMatch`/`isVersionConflict` pattern.
- `api.ts`: add `correctRelation`, `invalidateRelation`, `getRelation`, `updateEvent`, `archiveEvent` (with `ifMatch(version)` for event).
- `hooks/useRelationMutations.ts`, `hooks/useEventMutations.ts` (own logic + react-query invalidation + 412 refetch).
- `components/RelationEditDialog.tsx` (predicate/endpoint correct + "mark wrong"→invalidate), wired from the read-only `RelationRow` in `EntityDetailPanel.tsx`.
- `components/EventEditDialog.tsx` (title/summary/time edit + archive), wired from `TimelineEventRow.tsx`.
- Respect MVC rules: components render, hooks own logic; no useEffect for the save action; If-Match concurrency via the existing helpers.
- a11y/mobile: 44×44 tap targets on icon-only CTAs; visibility-transition tests for the new dialogs (per my standing FE lessons).

> FE is the most open-ended slice. Its detailed component-level design + wireframe is deferred to the FE BUILD sub-cycle; this doc fixes the API surface + which components host the CTAs.

---

## 9 · Gateway + infra

- **worker-infra relay (F1/F2 fix, §4.0):** add `"outbox_id": idStr` to the XADD `Values` ([outbox_relay.go:159-164](../../services/worker-infra/internal/tasks/outbox_relay.go)). Additive; lands in BUILD sub-session A (foundation) because learning-service's dedup depends on it. Add a relay unit/integration test asserting `outbox_id` is present on the published message.
- **worker-infra durability (§10.1):** add `"glossary"`/`"knowledge"` to `streamMaxLen` (≈200_000); bump `event_log` retention + `OUTBOX_CLEANUP_RETAIN_DAYS` (≈30d); add the `ReplayCorrections` admin task. Lands in BUILD sub-session A/B.
- `api-gateway-bff` ([gateway-setup.ts](../../services/api-gateway-bff/src/gateway-setup.ts), [main.ts](../../services/api-gateway-bff/src/main.ts)): add `learningUrl` to the urls type, a `learningProxy` (`pathFilter: p => p.startsWith('/v1/learning')`), dispatch branch, `requireEnv('LEARNING_SERVICE_URL')`.
- `infra/db-ensure.sh` (authoritative) **and** `infra/postgres-init/01-databases.sql` (fresh-volume parity): add `loreweave_learning`.
- `infra/docker-compose.yml`: `learning-service` block (build context repo-root, internal 8094, host **8222** [next free in 82xx], DB/redis/jwt/internal-token env, healthcheck, depends_on postgres+redis); add `LEARNING_SERVICE_URL` + `learning-service` depends_on to the gateway block; **append `knowledge:postgresql://…/loreweave_knowledge` to `OUTBOX_SOURCES`** (line ~622) so the relay ships KS's new outbox. (Optional `learning:` source only if learning-service later emits — not this cycle.)
- contracts: `contracts/api/learning.openapi.yaml` (corrections read API) + add the new KS relation/event correction routes to the knowledge contract.

---

## 10 · Migration / rollback

- All DDL is **idempotent `CREATE TABLE IF NOT EXISTS`** run at startup — no destructive migration, no down-migration needed. New tables (`corrections`, KS `outbox_events`, learning `dead_letter_events`) are additive.
- Adding `version` to `:Event` in Neo4j: `coalesce(e.version,1)` everywhere → pre-existing event nodes default to 1 lazily; no backfill required.
- **Rollback:** the feature is dark until the gateway route + FE ship. If a problem surfaces: (a) drop the `knowledge:` entry from `OUTBOX_SOURCES` to stop KS emission; (b) stop learning-service. The graph + glossary keep working — corrections capture is a side-channel, never on the critical write path. `glossary.entity_updated` enrichment is additive so reverting glossary is safe (consumer ignores unknown fields).

### 10.1 · Durability & replay (review-impl MED-1 — PO chose "build replay now")

Corrections are append-only *history* (not re-derivable like glossary_sync's idempotent MERGE), so a lost message is unrecoverable. Redis Streams `MAXLEN` trims by length **regardless of consumer-group read position** ([outbox_relay.go:157](../../services/worker-infra/internal/tasks/outbox_relay.go), glossary→`defaultStreamMaxLen=10000`) → a long learning-service outage (>budget messages behind) silently drops trimmed events. Three-part durability:

1. **Reduce trim probability:** add `"glossary"` + `"knowledge"` to `streamMaxLen` ([outbox_relay.go:20-24](../../services/worker-infra/internal/tasks/outbox_relay.go)) with a high budget (e.g. **200_000**) so trim-before-consume is effectively impossible inside any realistic outage.
2. **Retained replay source = `event_log`** (worker-infra events DB) — the relay already durably archives **every** relayed event keyed by `UNIQUE(source_service, source_outbox_id)` with full payload + `created_at` ([outbox_relay.go:173-177](../../services/worker-infra/internal/tasks/outbox_relay.go)). Bump its retention (and `OUTBOX_CLEANUP_RETAIN_DAYS`) to **exceed the max tolerable learning-service outage** (e.g. 30d). This is the canonical backfill source.
3. **Replay mechanism — hosted in worker-infra** (it already owns pools to `event_log` + every outbox DB, exactly like the relay; keeps learning-service from cross-reading another service's DB). A `ReplayCorrections` admin task/endpoint: given a time window, re-`XADD`s correction-typed `event_log` rows (event_type ∈ {`glossary.entity_updated`, `knowledge.*_corrected`}) back to their streams; learning-service **re-consumes idempotently** via `ON CONFLICT (origin_service, origin_event_id)`. So a missed window is recoverable by an operator-triggered replay. (Precise endpoint shape is a BUILD detail; the design commitment is: high MAXLEN + retained `event_log` + worker-infra-hosted idempotent replay.) → tracked **D-PHASE-B-REPLAY-TOOL** (BUILD sub-session A/B).
- **Monitoring:** a consumer-lag metric on the `learning-collector` group (XINFO GROUPS lag) + alert, so an outage is noticed before it approaches the (now large) MAXLEN budget.

---

## 11 · Test plan (for BUILD VERIFY — checklist, per "design test-plan is a checklist" lesson)

- **glossary (Go):** `buildEntityEventPayload` actor/before/after matrix; `patchEntity` SELECT-old captures pre-state in same tx; bulk emits `actor_type="pipeline"`; create emits `before=null`.
- **knowledge (Py):** outbox row written on entity PATCH/merge/archive; `update_event_fields`/`archive_event` repo (incl. version bump + VersionMismatch); relation correct = invalidate+recreate produces 2 edges with new id; **F3 — correcting onto a previously-invalidated tuple yields an edge with `valid_until IS NULL` (resurrected) and `after` is read post-write**; emit best-effort try/except swallows PG failure without failing the Neo4j edit (cross-store test); If-Match 428/412 on event PATCH.
- **relay (Go, F1):** `processSource` publishes `outbox_id` on the stream; assert the field is present + equals the row PK (regression-lock for the dedup contract). **F4 grep-gate: `outbox_id` ≥5 hits across the repo (orphan-detection).**
- **knowledge (Py, F5):** Pass-2 re-extraction of a user-invalidated SVO **leaves `valid_until` NON-null** (extraction path cannot resurrect — proves the resurrect is scoped to the dedicated `recreate_relation`, not shared `create_relation`).
- **learning (Py):** consumer upserts correction; `ON CONFLICT (origin_service, origin_event_id=outbox_id)` dedup on redelivery (sequential same-message test, per my "test sequential writes" lesson); **F2 regression-lock — TWO edits of the SAME target (same `aggregate_id`, different `outbox_id`) produce TWO correction rows** (proves we keyed on outbox_id not aggregate_id); `actor_type=="pipeline"` glossary event is ACKed but **not** persisted; diff_class derivation per row; DLQ on handler exception; read API strict user-scoping (cross-user → empty); cursor pagination with a filtered row at the page boundary.
- **cross-service LIVE SMOKE (required — ≥2 services):** stack up → user PATCH a glossary entity via gateway → relay ships `glossary.entity_updated` (actor=user) → learning-service `corrections` row appears with before/after + diff_class. Then a KS entity archive → `knowledge.entity_corrected` → corrections row. Token: `dev_internal_token`. (If full stack not bootable: `LIVE-SMOKE deferred to D-PHASE-B-LIVE-SMOKE`.)
- **regression-lock:** existing KS glossary_sync consumer still works against the enriched `glossary.entity_updated` (ignores new fields) — assert glossary_sync unaffected.

---

## 12 · BUILD sequencing recommendation (multi-session XL)

Natural seam (foundation vs integration, per my XL-checkpoint lesson):
1. **Foundation (session A):** learning-service scaffold + `corrections` DDL + consumer + read API + gateway + compose/db-ensure. Glossary `entity_updated` enrichment + actor threading. Live-smoke glossary→learning. ← self-contained, shippable.
2. **KS capture (session B):** KS Postgres outbox + emit helper + entity-correction emission on existing endpoints + `OUTBOX_SOURCES`. Live-smoke KS-entity→learning.
3. **Rel/event edits (session C):** new relation + event correction repo primitives + routers + emission; FE relation/event edit UI. ← largest, most FE.

Each sub-session is its own VERIFY+POST-REVIEW+COMMIT under the workflow gate.

---

## 12.5 · AMAW design-review outcome

3 adversarial cold-start rounds (`docs/audit/AUDIT_LOG.jsonl`, `findings-phase-b-correction-capture-r1.md`):
- **r1 → REJECTED:** F1/F2 (BLOCK) idempotency key `origin_event_id` was absent from the wire + `aggregate_id` collapses per-target; F3 (WARN) relation predicate-fix collision. **Folded** (§4.0 relay carries `outbox_id`; §6.4 F3).
- **r2 → REJECTED:** F4 (BLOCK) `outbox_id` 5-place sync incomplete + dataclass miscited; F5 (BLOCK) resurrect would corrupt extraction hot path; F6 (WARN) diff_class order. **Folded** (§4.0 5-point sync + event_log note; §6.4 F5 dedicated `recreate_relation`; §3 op-first order).
- **r3 → APPROVED_WITH_WARNINGS (clean stop):** BLOCKs verified resolved + internally consistent. 3 residual WARNs: R3-W1 (folded — empty `outbox_id` → DLQ not silent `""`); R3-W2/W3 (BUILD-time pins, §6.4). No filler.

**Pragmatic stop at r3** per AMAW calibration (XL, full rounds). Residual risk = the 3 WARNs above, all tracked into the BUILD test plan / pins.

## 13 · Open questions / residual risks — RESOLVED at POST-REVIEW

- **R1 (cross-store):** KS Neo4j-vs-Postgres outbox non-atomicity → best-effort emit; under-count risk; reconcile deferred (§6.6, D#046). **ACCEPTED for Phase B** (loss now also recoverable via the §10.1 replay tool).
- **R2 (privacy):** ✅ **PO chose REDACT/HASH NOW.** `corrections` stores `*_structural` + `*_content_hash`, no raw novel text (raw reserved for a Phase-E per-tenant opt-in, D#050). diff_class proven to work on structural+hash. See §3.
- **R3 (relation predicate-fix identity):** invalidate-then-recreate leaves the old invalidated edge; before=old/after=new captures intent; FE renders one logical "fix". F3/F5 fixes (§6.4) cover the resurrect-collision. FE concern noted (§8).
- **R4 (Tier-1 boundary):** ✅ **CONFIRMED** — anchor-reuse deferred to Phase C (D#048). Phase B captures; the next extraction is not yet improved by corrections this cycle.
- **R5 (actor_id):** glossary JWT `sub` and KS JWT `sub` are the same auth-service identity domain → interchangeable in `corrections.actor_id`. ACCEPTED.
- **MED-1 (durability):** ✅ **PO chose BUILD REPLAY NOW** — high MAXLEN + retained `event_log` + worker-infra-hosted idempotent replay (§10.1, D#049).
