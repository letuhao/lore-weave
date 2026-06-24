# Spec — Producer-Emit Backfill (Unified Job Control Plane P1 completeness)

**Date:** 2026-06-17 · **Branch:** `feat/auto-draft-factory-gaps` · **Size:** L (4 producers, 3 Py services + 1 Go) · **Status:** DESIGN (awaiting PO sign-off)
**Origin:** user hit 3 bugs testing glossary-extract → root-caused to `D-JOBS-GLOSSARY-EXTRACT-UNWIRED`; an audit found the gap is **systematic** — several job producers were never wired into the control plane during P1.

---

## 1. Problem

The Unified Job Control Plane (P1) wires producers via `emit_job_event` → `outbox_events` (`aggregate_type='jobs'`) → worker-infra relay → `loreweave:events:jobs` → jobs-service `job_projection`. A job is visible/monitorable in the unified Jobs screen **only** if it emits. P1 wired the "main" pipelines but **missed 4 producers** — each has a full job table + lifecycle but emits **nothing**, so the job never reaches the projection (invisible in the Jobs screen; cancel/terminal also unrecorded — exactly the user's report "data chưa được insert vào table quản lý job").

### Audit result — un-wired producers

| Producer | Service (lang) | Table | Owner col | User-facing | Native status vocab |
|---|---|---|---|---|---|
| **glossary-extract** | translation (Py) | `extraction_jobs` | `owner_user_id` | ✅ | pending→running→completed/`partial`/failed · cancelling→cancelled |
| **glossary-translate** | translation (Py) | `glossary_translation_jobs` | `owner_user_id` | ✅ | pending→running→completed/`completed_with_errors`/failed · cancelling→cancelled |
| **wiki-gen** | knowledge (Py) | `wiki_gen_jobs` | `user_id` | ✅ (via gateway) | pending→running/paused→`complete`/failed/cancelled |
| **book-import** | book (Go) | `import_jobs` | `user_id` (initiator) | ✅ | pending→running→completed/failed |

Already wired (reference): `translation_jobs`, knowledge `extraction_jobs`, composition `generation_jobs`, `video_gen_jobs`, `enrichment_job`+`enrichment_compose_task`, campaign. `llm_jobs` (provider gateway) is intentionally NOT a unified job (N/A).

---

## 2. Canonical contract (derived from the wired translation_jobs reference)

**Emit** (`loreweave_jobs.emit_job_event(conn, *, service, job_id, owner_user_id, kind, status, [model, cost_usd, tokens_in, tokens_out, params, parent_job_id, detail_status, progress, title, error, occurred_at])`):
- **H1**: emit in the SAME DB tx as the status write (atomic with the row). Use `emit_job_event_safe(pool, **kw)` (best-effort, post-commit) only at worker terminal sites that intentionally decouple (the reconcile sweep backstops).
- **Status coercion**: pass canonical (`pending|running|paused|cancelling|completed|failed|cancelled`); native aliases auto-map; an unmappable status is **skipped, not raised** (B0 fix). Map each producer's natives explicitly: `partial`→`completed`, `completed_with_errors`→`completed`, `complete`→`completed`.

**Visibility is automatic.** Once a producer emits, jobs-service LIST + DETAIL work with **no registration** — the projection mirrors by `(service, job_id)`; LIST filters the `kind` column; DETAIL reads the projection row (no owning-service call). **This is the whole fix for bug #3 (history/monitoring).**

**Reconcile source** (H1 backstop, `jobs-service/reconcile.py _RECONCILE[service] = (url, "/internal/{svc}/jobs")`): each service exposes `GET /internal/{svc}/jobs?since=&limit=` → `{"jobs":[{service, job_id, owner_user_id, kind, status, parent_job_id, detail_status, progress, title, error, occurred_at}, …]}` (all owners; oldest-first; capped). A service with multiple job tables **UNIONs** them here (distinct `kind` per table).

**Control** (only if cancel/pause/resume from the screen is wanted): `jobs-service/control.py _CONTROL[service]=(url, prefix)` forwards `POST {prefix}/{job_id}/{action}` `{owner_user_id}`. The owning endpoint must dispatch to the right table for the job_id.

---

## 3. Design decisions (PO: confirm)

- **D1 — `service` label = physical service; `kind` disambiguates the producer.** Emit glossary-extract as `service="translation", kind="glossary_extraction"`; glossary-translate `kind="glossary_translation"`; wiki-gen `service="knowledge", kind="wiki_gen"`; book-import `service="book", kind="book_import"`. Keeps `_RECONCILE`/`_CONTROL` at one entry per physical service. (Rejected alt: a synthetic service label per producer — more registry churn.) **`kind` must NOT collide with knowledge's existing `extraction`.**
- **D2 — reconcile = UNION in the existing per-service endpoint.** translation's `/internal/translation/jobs` UNIONs `translation_jobs` + `extraction_jobs` + `glossary_translation_jobs`; knowledge's `/internal/knowledge/jobs` UNIONs `extraction_jobs` + `wiki_gen_jobs`. book gets a NEW `_RECONCILE["book"]` source (book-service had none).
- **D3 — MVP = VISIBILITY first, CONTROL where already supported.** The user's priority is "history always recorded + monitorable". Phase 1 of each slice = emit + reconcile (the job shows up + survives cancel). Phase 2 = wire CONTROL only where the owning service already has a cancel/pause path (glossary-extract cancel, glossary-translate cancel, wiki-gen pending/paused cancel + resume). Running-cancel gaps stay their own deferred (e.g. `D-WIKI-M7B-RUNNING-CANCEL`).
- **D4 — book-import Go emit = reuse the outbox + relay (Option A).** worker-infra's relay already routes any `outbox_events` row with `aggregate_type='jobs'` to `loreweave:events:jobs`. Parameterize book-service's `insertOutboxEvent` to accept `aggregate_type`, add a tiny Go `EmitJobEvent` helper writing the canonical payload, call it in the SAME tx as the `import_jobs` status write. No Go SDK package yet (only one Go producer).
- **D5 — glossary-extract's 2 adjacent bugs ride its slice.** #1 FE pick-mode inherits the 'all' default → clear selection when entering 'pick' (`StepBatchConfig`). #2 create endpoint does 2 HTTP + an O(N) per-chapter INSERT loop before 202 → batch the chapter-results INSERT (single statement) + keep profile/estimate but off the hot loop.
- **D6 — test strategy = live producer-proof, not just unit spies.** A producer that emits *nothing* is invisible to a repo-spy test (the lesson behind this whole gap). Each slice's VERIFY must assert the emitted `job.<status>` lands on `loreweave:events:jobs` / the projection (a real producer-proof on a stack-up), or an explicit `LIVE-SMOKE deferred` row. Unit spy tests guard regressions but do NOT count as the wiring proof.

---

## 4. Per-producer wiring plan

### Slice A — glossary-extract (`extraction_jobs`, translation-service) + its 2 bugs
- **Emit** `kind="glossary_extraction"`: `routers/extraction.py create_extraction_job` — emit `pending` in the INSERT tx (model name + params). `workers/extraction_worker.py` — emit `running` at job-start UPDATE, terminal (`completed`/`partial`→completed/`failed`) at the finalize, in-tx. `routers/extraction.py cancel` — emit `cancelled` (the UPDATE to `cancelling`/the worker's flip to `cancelled`; emit the canonical terminal). *Confirm the exact worker job-status sites at BUILD.*
- **Reconcile**: UNION `extraction_jobs` into `/internal/translation/jobs` (kind `glossary_extraction`, `partial`→`completed`).
- **Control** (P2): translation `_CONTROL` already exists; make its control endpoint dispatch a `glossary_extraction` job_id to the extraction cancel path (kind-routed — jobs-service forwards `kind`, see D3/§5).
- **Bug #1 (FE)**: `StepBatchConfig.handleModeChange('pick')` → `onChapterIdsChange([])` (start pick empty).
- **Bug #2 (BE)**: replace the per-chapter INSERT loop with a single bulk INSERT (unnest); leave profile/estimate (needed for the row) but ensure no per-chapter await.

### Slice B — glossary-translate (`glossary_translation_jobs`, translation-service)
- **Emit** `kind="glossary_translation"`: `routers/glossary_translate.py` create — `pending` in-tx; `workers/glossary_translate_worker.py` — `running` at the claim UPDATE (in-tx), terminal (`completed`/`completed_with_errors`→completed/`failed`) at the finalize UPDATE, `cancelled` at the worker's cancel flip. (The worker already publishes informal `publish_event`s — add the durable `emit_job_event` alongside, in the same acquire/tx.)
- **Reconcile**: add to the translation UNION (kind `glossary_translation`).
- **Control** (P2): cancel via kind-routed dispatch.

### Slice C — wiki-gen (`wiki_gen_jobs`, knowledge-service)
- **Emit** `kind="wiki_gen"` (owner = `user_id`): `repositories/wiki_gen_jobs.py` — emit in each repo mutation's tx: `create`→`pending`, `mark_running`→`running`, `complete`→`completed`, `fail`→`failed`, `pause`→`paused`, `resume`→`pending`/`running`, `cancel`→`cancelled`. (Repo methods already own their conn — add emit in the same `async with conn.transaction()`.)
- **Reconcile**: UNION `wiki_gen_jobs` into `/internal/knowledge/jobs` (kind `wiki_gen`, `complete`→`completed`).
- **Control** (P2): wiki already has cancel(pending|paused)/resume — wire via kind-routed dispatch. Running-cancel stays deferred.

### Slice D — book-import (`import_jobs`, book-service, Go)
- **Go emit helper** (`internal/jobs/emit.go`): write `outbox_events(aggregate_type='jobs', aggregate_id=job_id, event_type='job.<status>', payload=<canonical JSON>)`; parameterize `outbox.go insertOutboxEvent` to take `aggregate_type`.
- **Emit** `kind="book_import"` (owner = initiator `user_id`): `startImport` → `pending` in the create tx; `updateImportJobStatus` → `running`/`completed`/`failed` in the status-UPDATE tx.
- **Reconcile**: new `_RECONCILE["book"]` + a book-service `GET /internal/book/jobs?since=&limit=` over `import_jobs`.
- **Control**: cancel only if book-import supports it (assess at BUILD; else visibility-only + a deferred).

---

## 5. Control kind-routing (the one shared change)

To let one physical service host multiple producers' control, `jobs-service control.py forward_control` must include the projection row's **`kind`** in the forwarded body (today it sends only `owner_user_id`). The owning control endpoint then dispatches by `kind` to the right table. Small, additive (kind is already on the projection row the GUI clicked). Alternative if we want zero jobs-service change: the owning endpoint does a table-by-table job_id lookup — uglier. **Recommend forwarding `kind`.** (CONTROL is P2 per D3; this change lands with the first control-wiring slice.)

---

## 6. Sequencing & size

Each slice is independently shippable (a producer becomes visible the moment it emits + reconciles). Suggested order by user impact: **A (glossary-extract, the reported bug + 2 adjacent fixes) → C (wiki-gen) → B (glossary-translate) → D (book-import, the Go one, last).** Slices A–C are Python (same pattern); D adds the Go emit helper. CONTROL kind-routing (§5) lands with the first slice that wires control.

VERIFY per slice: unit spy (emit fires at each transition) + **a live producer-proof** (emitted `job.<status>` lands in the projection on a stack-up) OR `LIVE-SMOKE deferred to D-PRODUCER-EMIT-<X>-LIVE-SMOKE`. Rebuild touched images first (stale = false-green).

---

## 7b. Architecture review (2026-06-17) — premise verified + folded-in findings

**Verified the load-bearing premise "visibility is automatic":**
- `job_projection` PK = `(service, job_id)` → no cross-service collision (translation's `extraction_jobs` vs knowledge's `extraction_jobs` are distinct rows; uuidv7 makes a same-service same-uuid clash negligible).
- No `kind` allowlist anywhere: `JobEvent.from_payload` does `kind=d["kind"]` unvalidated; the projection consumer/store never drop an unknown kind.
- FE `JobsFilters.KINDS` is open-ended ("the list still shows any kind"); default filter `""` = All kinds → a new kind appears with no FE change.

**Folded-in findings (now part of each slice):**
- **FE polish (per producer)**: add the new kind to `frontend/.../jobs/components/JobsFilters.tsx KINDS` + i18n `jobs:kind.<kind>` (×4 locales) so it gets a filter option + a real label (not the raw string); verify the job DETAIL panel degrades gracefully for the new kind (generic render, no crash). Visibility works without this; it's UX completeness.
- **Slice A create-tx**: glossary-extract's create is currently non-transactional (job INSERT + an O(N) chapter-results loop as separate awaits → a mid-loop failure leaves a half-created job). Wrap (job INSERT + `emit_job_event pending` + the bulk chapter-results INSERT from bug #2) in ONE `async with db.transaction()` — satisfies H1 AND fixes the latent half-create.
- **Sequence the reconcile UNION early in each slice**: the sweep reads the table directly, so the UNION alone **backfills pre-existing in-flight jobs** into the projection on the first sweep (current stuck jobs become visible even before any new live emit).
- **BUILD notes**: each UNION branch needs its own effective-`ts` expression (translation_jobs has no `updated_at` → `GREATEST(created,started,finished)`; check the others); confirm whether `extraction_worker`/`glossary_translate_worker` have a job-level `running` UPDATE to emit at (else `pending→terminal` is acceptable — some single-call jobs skip `running`).

## 7. Out of scope / deferred
- Running-cancel for wiki-gen (`D-WIKI-M7B-RUNNING-CANCEL`, pre-existing).
- A shared Go jobs SDK package (revisit if a 2nd Go producer appears).
- Pause/resume for glossary-extract / glossary-translate (cancel-only today; not multi-unit-pause).
- Backfill of already-finished historical jobs (only NEW jobs emit; the reconcile `since` window covers in-flight + recent).
