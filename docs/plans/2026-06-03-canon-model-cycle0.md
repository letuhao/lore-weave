# Canon Model — Cycle 0 Implementation Plan

> **Track:** LOOM (Cycle 0) · **Date:** 2026-06-03 · **Phase:** PLAN · **Branch:** `feat/composition-service`
> **Spec SSOT:** [canon-model.md](../specs/2026-06-03-canon-model.md) (§1 primitives · §2 flow · §3 migration · §6 verified evidence)
> **Task size:** **XL** — cross-service contract change (book-service Go · worker-infra · knowledge-service Python · extraction SDK) + a data migration + an event-consumer cutover + backfills. Plan file mandatory; **`/amaw` for CM1 (schema/migration) + CM3 (consumer cutover)**.
> **Why:** fixes **pre-existing platform bugs** (no-op timeline filters, draft prose in the semantic index, dead `extraction_pending`, broken `chapter_range`, live-draft extraction race — spec §0 B1–B5) that already harm knowledge/chat/wiki/enrichment. **Composition surfaced them (first feature to exercise these paths) — it did not cause them.** Justified independently as debt-paydown; it also unblocks composition (OI-1 structural + spoiler-cutoff real). NOT composition scope-creep.
> **Boundary:** touches book/worker-infra/knowledge/**worker-ai**/SDK. **NEVER `services/lore-enrichment-service/`** — Primitive 4 (provenance) is designed to *align* with enrichment H0, not modify it.
>
> **⚠️ CORRECTED 2026-06-03 (/review-impl + a trigger→execute trace) — read [§8](#§8) FIRST.** A trace revealed the extraction architecture is **not** what §1.3/§2/§3 below originally assumed: graph extraction (Pass-2) is **user-triggered + whole-book** (poll-job via `/extraction/start`), NOT event-driven; the `chapter.saved`→`extraction_pending` queue is **dead for chapters**; passage-ingest is a **separate inline** path. **`worker-ai` was missing from the touch-points.** §8 carries the corrected architecture, the redesigned (event-driven, single-chapter, pinned-revision) CM3, CM-FE in-scope, and the folded /review-impl fixes. Where §1.3/§2(CM3)/§3 conflict with §8, **§8 wins.**

---

## §0 Scope lock

**IN (Cycle 0 backend):**
- **P1 editorial lifecycle** — `chapters.editorial_status` + `published_revision_id`; `POST …/publish`; `chapter.published` event; **internal revision-body read** (for the worker).
- **P2 canon=published** — knowledge extracts on `chapter.published` at the **pinned revision**, drops `chapter.saved` from the extraction path.
- **P3 dual-order populated** — `event_order` (reading) at write; `chronological_order` (from `event_date_iso`) incremental + backfill; passage `chapter_index` populated.
- **P4 provenance (minimal)** — knowledge accepts a `provenance` hint on extraction + stamps facts; vocabulary aligned with enrichment H0. No behavior change beyond tagging.
- Migration + backfills (existing chapters → `published`; existing events → orders; passages → chapter_index).

**OUT (deferred / separate):**
- ~~Normal-editor Publish affordance (FE)~~ → **NOW IN SCOPE as `CM-FE` (§8.4)** — pulled in to avoid platform-wide KG/passage staleness (HIGH-2). Composition's own FE also drives publish for its scenes.
- **Provenance-weighted contradiction scoring** — composition's critic concern (its §4) / V1; Cycle 0 only tags.
- **In-world time resolution quality** (relative dates "3 days later") — a future extraction-quality cycle; reading-order is the robust fallback.
- **L5 summaries read-endpoint** — separate future knowledge surface (composition §2.1).

---

## §1 Per-service changes (file-level, grounded in verified code)

> **+ `worker-ai` (added by the trace — see §8.2):** the extraction execution lives in `services/worker-ai/`, which §1.3 below omitted. The redesigned knowledge/worker-ai split is in §8.3.

### §1.1 book-service (Go/Chi)
| File | Change |
|---|---|
| `internal/migrate/migrate.go` | `ALTER TABLE chapters ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'draft' CHECK (… 'draft','in_review','published')` + `ADD COLUMN IF NOT EXISTS published_revision_id UUID`. **Backfill DO-block:** for every existing chapter, set `editorial_status='published'` + `published_revision_id` = latest `chapter_revisions.id` (by `created_at`); **chapters with NO revision → leave `draft`** (nothing canon yet). Idempotent; matching DOWN drops both columns. |
| `internal/api/server.go` | New `publishChapter` handler + route `POST /v1/books/{book_id}/chapters/{chapter_id}/publish` (owner-only, mirrors patchDraft auth). In one tx: ensure a revision exists for the current draft (reuse the existing revision-insert at `:1535`; if draft unchanged since last revision, reuse it), set `published_revision_id` + `editorial_status='published'`, `insertOutboxEvent(ctx, tx, "chapter.published", chID, {"book_id":bookID,"chapter_id":chID,"revision_id":revID})`. Optional `POST …/unpublish` → `draft`. Return `editorial_status` + `published_revision_id` on chapter GET (`getChapter`). |
| `internal/api/server.go` (internal) | **New internal route** `GET /internal/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/body` (or `…/published-body`) — returns a revision's `body` JSONB for the **worker** (no JWT; `requireInternalToken`). The existing revision-read (`:1599`) is JWT-gated `/v1` — the worker can't use it. **This is the contract detail that bites — own deliverable.** |
| `internal/api/outbox.go` | none — `insertOutboxEvent` (`:15`) already takes an arbitrary `event_type`. |

### §1.2 worker-infra (relay)
| File | Change |
|---|---|
| relay config | **Verify the relay is `event_type`-agnostic** (routes by `aggregate_type='chapter'` → `loreweave:events:chapter`). The PG-trigger→pg_notify→Redis relay is generic, so `chapter.published` SHOULD flow with no change. **CM2 = confirm, add only if an explicit event_type allowlist exists.** |

### §1.3 knowledge-service (Python/FastAPI)
| File | Change |
|---|---|
| `app/main.py:198-206` | Register `dispatcher.register("chapter.published", handle_chapter_published)`. **Remove/neuter** the `chapter.saved`→extraction registration (`:199`) — the cutover (§3). |
| `app/events/handlers.py` | New `handle_chapter_published`: resolve project via `book_id` (reuse `:96-125`, keep the no-project skip `:118`), **fetch content AT `revision_id`** via the new internal book endpoint, queue `extraction_pending` with the revision content, ingest passages **with `chapter_index` populated from `sort_order`** (the absorbed old-Mk fix: thread `chapter_sort_order` already fetched at `:203` into `ingest_chapter_passages` instead of `None` at `:237`). |
| `app/clients/book_client.py` | New `get_chapter_revision_body(book_id, chapter_id, revision_id)` → the new internal revision-body route. Keep `get_chapter_sort_orders` (`:141`). |
| `app/extraction/pass2_writer.py:510-523` | Pass `event_order=<reading position>` into `merge_event` — compute from chapter `sort_order` (in scope) × `1e6` + within-chapter index (scene/para). |
| `app/db/neo4j_repos/events.py:163-233` | `merge_event` already accepts `event_order`/`chronological_order` (default None) — supply `event_order`. Add a repo method `rerank_chronological_order(project_id)`: rank project events by `event_date_iso` (NULLs last → NULL chrono), dense-rank → SET `chronological_order`. |
| `app/extraction/passage_ingester.py:284` | ensure `chapter_index` set from `sort_order` (paired with handlers change). |
| `app/events/handlers.py` (post-extract) | After a chapter's events are written, call `rerank_chronological_order(project_id)` (incremental; debounce/skip if no dated events changed). |
| provenance (P4) | `extraction_pending` / the extraction call carries an optional `provenance` (default `human_authored`); `pass2_writer` stamps it on facts/entities alongside the existing `source_type`/`confidence`/`pending_validation`. Vocabulary `{human_authored, ai_assisted, enrichment}` aligned with enrichment. No scoring change. |

### §1.4 extraction SDK (`sdks/python/loreweave_extraction/`)
| File | Change |
|---|---|
| (events) | **No LLM-schema change** — `event_order`/`chronological_order` are assigned at WRITE time (pass2_writer + rerank pass), not extracted from the LLM. `LLMEventCandidate` (`extractors/event.py:111-134`) unchanged. `event_date_iso` already emitted — that is the chronological source. |

---

## §2 Build order — milestones

Each CM is independently VERIFY-able before the next. TDD per BUILD rule.

| CM | Title | Deliverable | Verify gate |
|---|---|---|---|
| **CM1** ⚠️`/amaw` | book-service lifecycle + publish + internal revision-body | migrate (cols + backfill) · `publishChapter` + `chapter.published` event · internal `…/revisions/{id}/body` route · GET returns status | migrate up/down clean (round-trip); **backfill: existing chapter → `published` + pointer; revision-less chapter stays `draft`**; publish snapshots a revision + emits `chapter.published`; internal body read returns the revision JSONB; Go unit + DB suite green |
| **CM2** | worker-infra relay confirm | confirm `chapter.published` reaches `loreweave:events:chapter` (config only if an allowlist exists) | live: publish → message on the chapter stream |
| **CM3** ⚠️`/amaw` | ~~knowledge extract-on-publish~~ **→ SUPERSEDED by §8.3 (CM3a/b/c)** — the trace showed graph extraction is user-triggered-whole-book (not event-driven) and `worker-ai` must be reworked for event-driven single-chapter + pinned-revision. See §8. | — | see §8.3 verify gates |
| **CM4** | dual-order population + backfill | `event_order` at write · `rerank_chronological_order` (from `event_date_iso`) incremental + post-extract call · passage `chapter_index` populated · **backfills** (events orders; passage chapter_index — metadata SET, NO re-embed) | unit: `event_order` from sort_order; chrono rank correct given dates; NULL date → NULL chrono (fallback); live: `timeline?before_chronological=` / reading-order return correct NON-EMPTY sets; backfill stamps existing events + passages |
| **CM5** | provenance hint (minimal) | extraction accepts + stamps `provenance` (default `human_authored`); vocab aligned w/ enrichment; **no enrichment edits** | unit: `ai_assisted`-hinted extraction tags facts; default path = `human_authored`; **enrichment path unchanged (no regression)** |

**Critical path:** CM1→CM2→CM3 (canon-gate spine) → CM4 (ordering) → CM5 (provenance). Composition's Cycle-0 dependency = **CM1–CM4** (CM5 lands with composition's provenance slice).

---

## §3 Cutover & migration (the risky part — sequence carefully)

**Deploy order (no canon gap):**
1. **CM1 book-service first** — adds `/publish` + `chapter.published`; `chapter.saved` STILL emitted; migration stamps existing chapters `published` (already-extracted canon untouched).
2. **CM3 knowledge second** — switch consumer to `chapter.published`; drop `chapter.saved` extraction. Between (1) and (2) nothing breaks: existing canon intact; the only change at (2) is that *new draft saves stop auto-canonizing* — which is the intended behavior.

**No-gap argument:** existing chapters are pre-`published` and already in the KG, so cutover adds no re-extraction and loses no canon. New canon flows ONLY on explicit publish from then on.

**Backfills (CM4, idempotent, batch per project):**
- `event_order` ← chapter `sort_order` (+ within-chapter index) for existing events.
- `chronological_order` ← rank by `event_date_iso` (NULLs → NULL).
- passage `chapter_index` ← `sort_order` via `source_id` (metadata SET, **no re-embed** — vectors unchanged).

**FE gap (flagged, OUT):** after CM3, a newly-created chapter stays `draft` and won't canonize until published. The **normal-editor Publish affordance is a separate FE follow-up (`CM-FE`)**; existing chapters are pre-published so nothing regresses; composition's own FE drives publish for its scenes.

---

## §4 Test strategy

- **book-service (Go):** unit + DB round-trip — migrate up/down/up clean; backfill (with-revision → published, revision-less → draft); publish tx (revision + pointer + event atomic); internal revision-body read (internal-token only, JWT rejected); cross-user publish → 403.
- **knowledge-service (Python):** unit (mock) — `handle_chapter_published` resolves project + fetches revision body + queues; **`chapter.saved` no longer extracts**; `event_order` assignment; `rerank_chronological_order` (dated → ranked, undated → NULL); provenance default + hint. Integration/Neo4j — order fields persisted + filterable; backfill stamps.
- **Cross-service live-smoke (CLAUDE.md ≥2-service gate — REQUIRED token):** `live smoke: publish chapter → chapter.published → knowledge extracts pinned revision → event carries event_order + chronological_order → timeline?before_chronological filters correctly`. Needs a stack-up with a `knowledge_projects` row for the book. If infra unavailable: `LIVE-SMOKE deferred to D-CANON-CYCLE0-LIVE-SMOKE` with unit/integration coverage.
- **No-regression:** enrichment path untouched (CM5 default `human_authored`; enrichment still writes `origin='enrichment'`); a normal pre-existing chapter still queryable in KG post-migration.

---

## §5 Risks / watch-items

- **CM3 cutover is a platform-wide behavior change** — extraction stops on draft save. Mitigated by deploy order (§3) + pre-published migration. **Watch:** confirm no OTHER `chapter.saved` consumer relies on it for canon (verified: knowledge is the sole extraction consumer — re-confirm at CM3, K6).
- **Internal revision-body endpoint** — the worker has no JWT; the existing revision read is `/v1`-JWT. Missing this = CM3 can't fetch pinned content. **It is a CM1 deliverable, not an afterthought.**
- **`event_date_iso` quality bounds `chronological_order`** — relative/parametric dates rank poorly (K7). Reading-order (`event_order`) is the always-correct fallback; document the in-world residual.
- **`rerank_chronological_order` cost** — O(project events) per publish. Debounce / skip when no dated event changed; acceptable at book scale, watch for very large projects.
- **Revision-less chapters** in backfill — leave `draft` (don't fabricate a revision); they simply need a publish.
- **Stale images** (enrichment F-LIVE-1 lesson) — rebuild book + knowledge (+ worker) images via `scripts/build-stack.sh`; freshness guard before live-smoke.
- **Boundary** — Primitive 4 must align with, not fork, enrichment H0; touch no enrichment file.

---

## §6 Rollback
Each CM is additive + idempotent. **CM1: book-service has NO down-migration (forward-only idempotent `schemaSQL`; adversary-R1#1)** — the new columns are additive `ADD COLUMN IF NOT EXISTS`; "rollback" = leave the (unused) columns in place, revert the handler/route code. (knowledge-service migrations DO have `run_down_migrations`.) CM3 is reversible by re-registering `chapter.saved` + unregistering `chapter.published` (knowledge config). CM4 order fields are nullable/additive. No destructive change to existing rows (backfill only SETs new columns / null order fields).

---

## §7 Definition of done (Cycle 0)
- CM1–CM5 VERIFY-green; book Go unit+DB green; knowledge pytest unit+integration green; enrichment suite unchanged (no regression).
- Migration up/down/up clean; backfills idempotent + proven (existing chapter → published; existing events → orders; passages → chapter_index).
- **Cutover proven:** publish → extraction on pinned revision; bare draft save → NO extraction (the OI-1 structural guarantee).
- **Spoiler real:** `timeline?before_chronological=` returns a correct non-empty filtered set (the no-op is gone).
- Cross-service live-smoke run OR explicitly deferred (`D-CANON-CYCLE0-LIVE-SMOKE`).
- lore-enrichment untouched + its suite green.
- SESSION_HANDOFF updated; clean commits per CM. **THEN composition M0 unblocks.**

---

## §8 CORRECTED architecture + redesigned plan (/review-impl + trace, 2026-06-03)

A /review-impl pass verified the cutover assumptions and traced the real trigger→execute path. Findings + the redesign they force. **This section supersedes §1.3 / §2(CM3) / §3 where they conflict.**

### §8.1 Corrected extraction architecture (verified)
Two **independent** paths hang off `chapter.saved` — they do not connect:
- **Path A — passage ingest (L3/L4 semantic).** Event-driven, **inline + synchronous in the knowledge-service event consumer** (`handlers.py:227-245` → `passage_ingester.py:214`), embeds the **current draft**. This is the *only* path that auto-updates on every save.
- **Path B — Pass-2 graph extraction (entities/relations/events).** **NOT event-driven.** Runs only when a user/FE `POST /v1/knowledge/projects/{id}/extraction/start` creates a **whole-book** `extraction_jobs` row (`extraction.py:266-340`) that **worker-ai polls** (`worker-ai/main.py:86-98` → `runner.py:534`). The `chapter.saved`→`extraction_pending` row is **dead for chapters** — nothing converts it into a worker-ai job; only `chat`-scope reads that table. There is **no single-chapter scope** (`scope_range.chapter_range` is preview-only; `_enumerate_chapters` ignores it — `extraction.py:95-107`, `runner.py:791-823`).
- Worker content fetch = `book_client.get_chapter_text` → `GET /internal/books/{book_id}/chapters/{chapter_id}` → **current draft** text from `chapter_blocks` (`server.go:1860-1916`); takes no revision id.

**Consequences:** (1) the graph is NOT canonized on every save — it's canonized when a user runs build-graph (whole-book, current draft). (2) Passages ARE canonized on every save (inline). (3) Canon=published must therefore gate **both** paths. (4) `worker-ai` is a touched service the original plan omitted.

### §8.2 Touch-points correction — add `worker-ai` (REVISED by the final sweep §8.8 — coalescing drainer, NOT one-job-per-event)
> A unique partial index `idx_extraction_jobs_one_active_per_project` (`migrate.py:313`) caps active jobs at **1 per project** → "one job per `chapter.published`" would 409-storm. So we **coalesce via the existing `extraction_pending` queue + a per-project drainer = ONE job** (respects the index, coalesces rapid re-publishes, keeps one cost cap). This reuses infra and is simpler than the prior draft.

| File | Change |
|---|---|
| knowledge `app/events/handlers.py` | on **`chapter.published`**: queue `extraction_pending(aggregate_type='chapter', aggregate_id=chapter_id, …)` carrying **`revision_id`** (add a column) — re-uses the already-present queue path (idempotent `ON CONFLICT`, coalesces). Stop queuing on `chapter.saved`. |
| knowledge `app/db/.../extraction_pending` | add `revision_id` column (nullable); drain query filters `aggregate_type='chapter' AND processed_at IS NULL` ordered by `created_at`. |
| `services/worker-ai/app/main.py` | **per-project drainer** — a chapter-extraction job (status='running', respecting the 1-active/project index) drains the project's pending chapters as a BATCH; processes each at its pinned `revision_id`; marks `processed_at`. (Trigger: knowledge creates the drain job when it queues + no active job exists, or a light poll; NO job-per-event.) |
| `services/worker-ai/app/runner.py:791-823` | `_enumerate_chapters` reads the **pending set** (the chapters to extract this run) instead of `list_chapters` for the event path; honours per-chapter `revision_id`. |
| `services/worker-ai/app/runner.py` `JobRow`/`process_job`/content fetch | thread `revision_id` → **fetch the pinned revision** (not current draft); `source_id = chapter_id@revision_id` for provenance. |
| `services/worker-ai/app/runner.py:906-923` | **fix B7 (pre-existing):** `_enumerate_pending_chat_turns` lacks an `aggregate_type` filter → it currently mis-reads chapter pending rows as empty chat turns. Add `aggregate_type='chat'` filter so chat and chapter queues don't cross. |
| `services/worker-ai/app/clients.py:537` | new revision-pinned fetch (call the CM3a internal revision-text endpoint). |
| **retraction-before-reextract (CRITICAL-2/B6)** — `persist_pass2` path | **wire `remove_evidence_for_source(chapter_source)` + `cleanup_zero_evidence_nodes` BEFORE `write_pass2_extraction`** (functions exist in `provenance.py:419-455,548`, currently unwired) so re-publishing a chapter that REMOVED content retracts stale entities/relations/events. Mirrors what passage-ingest already does (delete-first). |
| knowledge `/extraction/start` (whole-book, manual) | **also gate canon=published** — skip `editorial_status='draft'` chapters; fetch published content (a manual rebuild never pulls drafts). |

### §8.3 Redesigned CM3 (event-driven · single-chapter · pinned-revision) — supersedes the old CM3 row
| CM | Title | Deliverable | Verify gate |
|---|---|---|---|
| **CM3a** (book) | `chapter.published` carries `revision_id` + internal revision-text endpoint | event payload `{book_id, chapter_id, revision_id}` (capture the revision id inserted in the publish tx); **new `GET /internal/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/text`** returning `text_content` (existing `getRevision` projects it — `server.go:1640-1643`; expose under `requireInternalToken`); **verify `revision ∈ chapter ∈ book` (IDOR)** | internal endpoint returns the revision text (token-only); cross-chapter/book revision id → 404; publish emits revision_id |
| **CM3b** (knowledge + worker-ai) | queue-coalesced, per-project drainer, pinned-revision, **retract-before-reextract** | `chapter.published` → knowledge queues `extraction_pending(+revision_id)`; worker-ai per-project **drainer** processes the pending chapter set as ONE job (respects the 1-active/project index, §8.2); fetch pinned revision; **wire `remove_evidence_for_source`+`cleanup_zero_evidence` before re-extract (CRITICAL-2)**; **fix B7 chat-drain `aggregate_type` filter** | unit: drainer coalesces N publishes into ONE job (no 409-storm); **bare draft save → NO extraction**; **re-publish that removed a fact → stale fact RETRACTED (no canon drift)**; chat/chapter queues don't cross; live: publish → graph updates from the pinned revision |
| **CM3c** (knowledge) | passage-ingest → published + pinned; manual `/extraction/start` skips drafts | switch inline passage-ingest `chapter.saved`→`chapter.published`, fetch pinned revision (passages already delete-first → re-publish self-heals); `/extraction/start` enumeration skips `editorial_status='draft'` | unit: draft save no longer ingests passages; published → passages from the pinned revision; manual rebuild skips drafts |

### §8.4 CM-FE — Publish affordance (NOW IN SCOPE, was deferred)
HIGH-2: cutting draft-save→canon without a publish UX would stale the KG **and** passages platform-wide for all normal editing (chat-grounding, drawers, wiki, translation-glossary, enrichment gap-detect). **Decision: ship the normal-editor Publish affordance inside Cycle 0** (a `CM-FE` milestone): a Publish/Unpublish control on the chapter editor calling `POST …/publish`, showing `editorial_status`. Existing chapters migrate to `published` (no break); new chapters need an explicit publish. **Recorded fallback** (if scope must shrink): an interim *auto-publish-on-save for human edits* bridge that keeps current behaviour, holding only composition AI-authored content as `draft` — chosen against here in favour of the clean "canon = published" model, but available.

### §8.5 Folded /review-impl fixes (MED/LOW)
- **MED-1 (chrono over-claim) — TEMPERED.** `chronological_order` is derived from `event_date_iso`, which for the **target corpus (CJK/cultivation/historical — 封神演义)** is frequently non-ISO/relative ("三日后", "第三年") → often NULL/unsortable. So **`event_order`/reading-order is the dense, reliable V0 spoiler axis**; `chronological_order` is **best-effort/opportunistic**, NULL→falls back to reading-order. Do NOT market flashback-safety as solid; it improves with extraction-time date resolution (future).
- **MED-3 — `rerank_chronological_order` stability.** Stable tiebreak (`event_id`) for equal/NULL dates; run **after** a chapter's events are written; concurrent publishes converge (dense-rank deterministic) — note but acceptable.
- **MED-4 — `/publish` idempotent + concurrency-guarded** (double publish / two devices) via `draft_version`; re-publish advances `published_revision_id`.
- **MED-5 — internal endpoint returns `text_content`** (not raw JSONB) — folded into CM3a.
- **LOW-1 — drop `in_review` from Cycle 0** (CHECK = `draft`|`published`); no transitions defined for it (YAGNI). Re-add when a review-queue feature needs it.
- **LOW-2 — `published_revision_id` FK `ON DELETE SET NULL`** (chapter purge cascades revisions; pointer must not dangle).
- **LOW-3 — `statistics-service` also reads `loreweave:events:chapter`** (separate consumer group, ignores `chapter.published`) — non-breaking; noted so the cutover isn't surprised.

### §8.6 Updated build order
**CM1** (book lifecycle + publish + migration) → **CM3a** (revision_id event + internal revision-text) → **CM2** (relay confirm — no-op, verified generic) → **CM3b** (worker-ai single-chapter + pinned-revision + consumer) → **CM3c** (passage-ingest + manual-rebuild gating) → **CM4** (dual-order, reading-order primary) → **CM-FE** (publish affordance) → **CM5** (provenance). Composition M0 unblocks after CM-FE (no staleness window) — i.e. **all of Cycle 0**.

### §8.7 Verified PASS (de-risked)
- worker-infra relay is **fully generic** (routes by `aggregate_type`, no event_type allowlist — `outbox_relay.go:149-205`) → CM2 truly no-op. ✅
- knowledge `BookClient` already carries `X-Internal-Token` (`book_client.py:36-39`) → new internal call needs no auth plumbing. ✅
- revision `text_content` already computed (`server.go:1640-1643`) → only needs internal exposure. ✅
- no other service extracts on `chapter.saved` (statistics ignores it) → cutover safe. ✅

### §8.8 Final pre-lock sweep (2026-06-03) — verified, folded above
A last adversarial pass on the full-rework path found 2 CRITICAL (corrected in §8.2/§8.3) + 2 more pre-existing bugs + the composition-interface granularity fork:
- **CRITICAL-1 (folded):** one-active-job-per-project unique index (`migrate.py:313`) makes "one job per `chapter.published`" a 409-storm + cost-cap bypass → redesigned to **coalescing per-project drainer over `extraction_pending`** (§8.2). Simpler, reuses infra.
- **CRITICAL-2 (folded):** graph extraction is **upsert-only** (`pass2_writer.py` has no DELETE) → re-publishing a chapter that removed content leaves **stale facts (canon drift)**; retraction fns exist but are unwired (`provenance.py:419-455`). Now wired before re-extract (§8.2/§8.3 CM3b). Passages already delete-first (correct).
- **B6 (pre-existing, spec §0):** re-extraction already drifts today — composition surfaced it.
- **B7 (pre-existing, spec §0):** chat drainer `_enumerate_pending_chat_turns` lacks an `aggregate_type` filter → mis-reads chapter pending rows as empty chat turns (`runner.py:906-923`). Fixed in CM3b.
- **HIGH — composition↔canon granularity (PO: chapter-gate):** composition reviews per-SCENE but `/publish` is per-CHAPTER → **composition publishes a chapter ONLY when ALL its scenes are `status='done'`** (chapter-level gate; the simplest fit for book-service's per-chapter publish). Intra-chapter context for the next scene comes from L3 recent-prose + L2′ planned-synopsis (no graph needed); the graph flywheel is per-chapter. Folded into composition-design §3.1/§11 + V0 plan M9.
- **Verified PASS:** worker poll loop is serial (`runner.py:1611`); `extraction_pending` schema supports coalescing (partial index `(project_id, processed_at IS NULL)`, idempotent `ON CONFLICT`).

### §8.10 CM3b design — graph-extraction cutover (DESIGN-locked 2026-06-04, grounded)
**Scope:** graph-extraction event-driven cutover ONLY (passages + manual-rebuild-gating = CM3c). Default v2.2 self-review (PO override of /amaw). Grounded vs `extraction_pending.py`, `handlers.py:83-245`, `extraction.py:266-329` (`_create_and_start_job`, 409 on unique index), `runner.py:1120-1210` (scope loop), `provenance.py` retract fns.

**knowledge-service:**
- **migrate** (extraction_pending DDL): `ALTER TABLE extraction_pending ADD COLUMN IF NOT EXISTS revision_id UUID;` (idempotent).
- **`extraction_pending.py`:** add `revision_id: UUID|None` to `ExtractionPending` + `ExtractionPendingQueueRequest` + `_SELECT_COLS` + INSERT; **add `aggregate_type: str|None=None` filter to `fetch_pending`** (chapter drainer passes `'chapter'`; **fixes B7** — chat path passes `'chat'`).
- **`handlers.py`:**
  - `handle_chapter_saved`: **DELETE the `queue_event` block (lines 127-142)**; KEEP passage-ingest (moves to published in CM3c). So `chapter.saved` no longer queues graph-extraction.
  - **NEW `handle_chapter_published`:** resolve project via book_id (reuse `:111-125`); `queue_event(aggregate_type='chapter', revision_id=payload['revision_id'], event_id=published-event-id)`; **ensure coalesced drain job:** `_create_and_start_job(scope='chapters_pending', …)` wrapped so `asyncpg.UniqueViolationError` (active job exists) is SWALLOWED (the active drainer picks up the freshly-queued row). NO job-per-event.
  - **NEW `handle_chapter_unpublished`:** resolve project; `neo4j_session` → `remove_evidence_for_source(chapter source_id)` + `cleanup_zero_evidence_nodes` (retract canon; **closes D-CM1-UNPUBLISH-RETRACT**).
- **`main.py`/consumer:** register `chapter.published` + `chapter.unpublished`; `chapter.saved` STAYS registered (passages). Stream already carries them (CM2).
- **`internal_extraction.py` `/persist-pass2` (the retract-before-reextract seam, B6):** before `write_pass2_extraction`, call `remove_evidence_for_source(source_id)`; after, `cleanup_zero_evidence_nodes`. Makes EVERY persist idempotent retract-then-write → re-publish/re-extract drops stale facts. (Cleaner than worker-side retract — provenance fns are knowledge-side; worker just calls persist as today.)
- **JobScope Literal** (`extraction.py:140`): add `'chapters_pending'`.

**worker-ai:**
- **`runner.py` `process_job`:** new branch `job.scope == 'chapters_pending'` → enumerate from `fetch_pending(user, project, aggregate_type='chapter')` → `[(chapter_id, revision_id, pending_id)]`; **drain loop** (re-fetch after each batch until empty → coalesces chapters queued mid-run): per item → status-check + `_try_spend` (one cost cap/job) → `text = book_client.get_chapter_revision_text(book_id, chapter_id, revision_id)` (CM3a) → extract → `persist_pass2` (now retract-then-write) → `mark_processed(pending_id)` → advance cursor.
- **`clients.py`:** `get_chapter_revision_text(book_id, chapter_id, revision_id)` → `GET /internal/books/{bid}/chapters/{cid}/revisions/{rid}/text` (CM3a), return `text_content`.
- **`runner.py` `_enumerate_pending_chat_turns` (B7):** add `AND ep.aggregate_type='chat'` to its query so chat-scope never consumes chapter rows.

**Self-review (REVIEW-design, default v2.2):**
- Coalescing respects the one-active-job/project unique index (ensure-job swallows 409) → no 409-storm, no per-job cost-cap bypass ✅.
- Retract-in-persist makes re-extraction idempotent (B6 closed) ✅; unpublish retracts directly ✅.
- B7 filter on BOTH drains (chapter + chat) ✅.
- `revision_id` survives event→queue→worker via the new column ✅.
- **Watch (BUILD):** the drain loop must re-fetch `fetch_pending` after each item/batch (a chapter published mid-run must be drained by the SAME active job, else it's stuck until the next publish creates a new job — but the unique index means no new job can start while this one runs → MUST drain-to-empty or the late row waits for job completion + next trigger). Decision: **drain loop re-fetches until `fetch_pending` returns empty**, then the job completes. A row queued after the final empty-check + before job completion is the only gap → acceptable (next publish ensures a new job; the row isn't lost, just delayed) — document.
- **Watch (BUILD):** `_create_and_start_job` sets project `extraction_status='building'` — for a `chapters_pending` drain that's fine, but ensure completion resets to 'ready' (reuse existing completion path).

**Build status + RESOLVED worker-half design (2026-06-04):**
- ✅ **Knowledge-half BUILT + verified** (migrate +revision_id +chapters_pending scope; `extraction_pending` revision_id + `aggregate_type` filter + **`upsert_chapter_pending`** keep-LATEST/re-arm; `handle_chapter_published`/`handle_chapter_unpublished` + `chapter_saved` drop-queue; main.py register; persist-pass2 retract-then-write; JobScope ×2). py_compile + imports + extraction_pending tests green.
- ✅ **Worker-half BUILT (safe pieces):** B7 `_enumerate_pending_chat_turns` `+ aggregate_type='chat'`; `clients.get_chapter_revision_text` (CM3a). py_compile green.
- ⏳ **Worker-half REMAINING (intricate — build fresh):**
  - **GROUNDING LOCKED:** `_build_run_config:359` sets `run_snapshot.model_ref = job.llm_model` (project `extraction_config` override is `{}` normally) → **the drain job's `llm_model` IS the extraction model**. A sentinel breaks extraction. So the **ensure-drain-job MUST reuse the project's LAST job's `(llm_model, embedding_model)`** (`SELECT … FROM extraction_jobs WHERE project_id=$1 ORDER BY created_at DESC LIMIT 1`). No prior job → skip (manual `/extraction/start` whole-book run bootstraps; subsequent publishes auto-drain).
  - **ensure-drain-jobs = WORKER-POLL (robust, not handler):** in `poll_and_run`, before `_get_running_jobs`: find projects with unprocessed `aggregate_type='chapter'` pending rows AND no active job → create a `chapters_pending` job reusing last-job models, swallow-409 on the unique index. (Poll-based handles "publish during an active job" without relying on a later publish. Worker already holds the knowledge pool — cf. `_get_project_book_id`.)
  - **`process_job` `chapters_pending` branch:** enumerate `ExtractionPendingRepo.fetch_pending(user, project, aggregate_type='chapter')` → `[(chapter_id, revision_id, pending_id)]`; **drain loop, re-fetch after each batch until empty** (coalesces chapters published mid-run); per item: `_refresh_job_status` + `_try_spend` (one cap/job) → `text = book_client.get_chapter_revision_text(book_id, chapter_id, revision_id)` → (hierarchy as today) → `_extract_and_persist(source_type='chapter', source_id=chapter_id, text=…)` (persist now retract-then-writes, B6) → `_mark_pending_processed(pending_id)` → advance cursor. On completion reset project `extraction_status='ready'` (existing path).
  - Then cross-service VERIFY (publish→queue→drain→extract at pinned revision; re-publish re-arms; unpublish retracts) or `LIVE-SMOKE deferred D-CANON-CYCLE0-LIVE-SMOKE`.

### §8.11 CM3c design — passage-ingest cutover + manual-rebuild draft-gating (CLARIFY-locked 2026-06-04)
**Scope:** complete canon=published for the two paths CM3b left on the draft: (A) inline passage-ingest (L3 semantic) and (B) the manual whole-book `/extraction/start` rebuild. **3 services** (the §8.3 "(knowledge)" label under-counts — the manual path lives in worker-ai/runner + a book-service list-endpoint field gap, the same touch-point miss §8.2 flagged). AMAW (CM3 list). PO checkpoint (2026-06-04): **drop `chapter.saved` entirely**; **passages publish-only** (matches graph).

**book-service** (`internal/api/server.go` `getInternalBookChapters` :1925-2005) — additive + server-side gate (folds BLOCK#1):
- Add `c.editorial_status, c.published_revision_id` to the list SELECT + scan (`editorialStatus string`, `publishedRevID *uuid.UUID`) + items map keys. Single-chapter reads already expose these (:2032); only the LIST was missing them.
- **NEW optional `?editorial_status=published` query param** → when present, filter BOTH the LIST `where` AND the COUNT `countWhere` (so the returned `total` matches the filtered items). **Default unset → all chapters** (backward-compat: existing consumers — chapter browser, etc. — unaffected). Single server-side gate that unifies the worker enumeration AND the knowledge cost-estimate (no count divergence). Validate against `{'draft','published'}`, else 400.
  - **⚠️ Exact positional wiring (folds R2-BLOCK#2):** `buildSortRangeFilter` assigns `$N` via `len(outArgs)`, and `limitPos/offsetPos` are `len(countArgs)+1/+2`. Apply the `editorial_status` predicate AFTER `buildSortRangeFilter` returns: append the value to `countArgs`, emit its placeholder `$%d` using the POST-append `len(countArgs)`, THEN compute `limitPos/offsetPos = len(countArgs)+1/+2`; append the same predicate string to both `where` and `countWhere`; reuse the one `countArgs` slice for COUNT and LIST. (A naive `$N` without appending the value first → pgx bind-count 500, or LIMIT-int mis-bound as the status string → `editorial_status='1000'` → zero rows = silent published-gate blackout.) Test: `total==len(items)` unbounded WITH the param + pagination binds WITH the param + invalid value → 400.

**worker-ai** (`app/clients.py`):
- `ChapterInfo` += `editorial_status: str | None = None` (`revision_id` already exists, used by CM3b drain).
- `list_chapters(book_id, editorial_status: str | None = None)` → append `&editorial_status=` to the URL when set; parse `revision_id=item.get("published_revision_id")` (+ `editorial_status` for completeness) → the manual path pins the published revision via the SAME `ChapterInfo.revision_id` field.

**worker-ai** (`app/runner.py` `_enumerate_chapters` :791) — the gate:
- Call `list_chapters(book_id, editorial_status='published')` → **drafts filtered server-side** (BLOCK#1: keeps the estimate/enumeration consistent). LOW-3 closed.
- For each returned (published) chapter with `revision_id is None` (the §8.9 adversary-R2-NEW-2 purged-pointer edge): **skip with `logger.warning` + a run-log entry** ("published chapter %s has no pinned revision — skipping", folds BLOCK#2 — NOT a silent debug skip; this is a visible canon-omission signal). Filter BEFORE the cursor-resume logic. Shared by `'chapters'` + `'all'` scope.
- **No content-fetch change:** the loop at :1262 already does `if ch.revision_id is not None: get_chapter_revision_text(...)` → manual rebuild now reads the **pinned published revision** for free. `items_total` (:1222) counts the gated list → correct.
- **⚠️ P3 `is_last` scope-guard (folds R2-BLOCK#1):** change `p3_is_last` (:1334) to `job.scope in ('chapters','all') and ch.chapter_id == pre_chapters[-1].chapter_id`. The coalesced `chapters_pending` drain processes a SUBSET of re-published chapters → its `pre_chapters[-1]` is NOT the book tail → must never assert is_last (else every incremental re-publish spuriously re-rolls the whole-book L0 summary — a latent CM3b bug surfaced here). Manual whole-book path is unchanged and canon-correct (published tail = canon tail; cursor-resume strips from the front). The whole-book summary refreshes on the next full manual rebuild. Test: a `chapters_pending` job whose subset tail ≠ book tail does NOT set is_last.

**knowledge-service** (`app/clients/book_client.py`):
- Add `get_chapter_revision_text(book_id, chapter_id, revision_id) -> str | None` (GET CM3a `…/revisions/{id}/text`, return `text_content`, None on any failure) — mirrors worker-ai's; knowledge's BookClient lacked it.
- `count_chapters(..., editorial_status: str | None = None)` → forward `editorial_status` to `getInternalBookChapters` (folds BLOCK#1). The extraction **cost-estimate** caller passes `'published'` so the preview count == what the gated rebuild actually extracts. Grep the call site; default `None` preserves any non-extraction caller.

**knowledge-service** (`app/extraction/passage_ingester.py` `ingest_chapter_passages`):
- Add `revision_id: UUID | None = None` + `delete_stale_on_missing: bool = True`. Step-1 fetch: `revision_id` set → `get_chapter_revision_text(book_id, chapter_id, str(revision_id))`; else `get_chapter_text(...)` (preserve the fallback contract).
- **⚠️ R3-WARN#1:** on `text is None`, only run the delete-stale branch when `delete_stale_on_missing` is True. The **published-revision caller passes `delete_stale_on_missing=False`** → a transient pinned-revision-fetch failure logs a `warning` ("pinned revision text unavailable — keeping existing passages") and returns WITHOUT wiping passages (else L3 passages vanish while the graph half still holds canon = drift). The legacy draft path keeps `True`.

**knowledge-service** (`app/events/handlers.py`):
- **DELETE `handle_chapter_saved`** + drop from `__all__` (graph-queue gone in CM3b, passages move here → fully dead; PO: drop). The C12a `chapter_range` scope-gate + `get_chapter_sort_orders` call go with it (publish is explicit per-chapter → always ingest; the bounded-manual-job range-skip no longer applies on the published path).
- **`handle_chapter_published`**: extend the project lookup to `SELECT project_id, user_id, embedding_model, embedding_dimension`. After `upsert_chapter_pending` (graph-queue first — fast/critical), append passage-ingest at the pinned revision: guard `embedding_model`+`embedding_dimension`+`neo4j_uri`; inline imports (circular-import guard, same as old handler); `async with neo4j_session(): await ingest_chapter_passages(..., revision_id=revision_id, chapter_index=None)`; wrap in try/except non-fatal. `chapter_index` stays `None` (CM4 backfills it — not CM3c scope).
- **`handle_chapter_unpublished`**: add passage retraction symmetry — `delete_passages_for_source(session, user_id=str(user_id), source_type='chapter', source_id=str(chapter_id))` so the semantic index doesn't retain published-era passages after unpublish (mirrors CM3b's graph retract; closes the passage-half of canon-drift-on-unpublish). **⚠️ R3-WARN#2:** run it as an INDEPENDENT best-effort step inside the neo4j session (own try, OR sequenced BEFORE `remove_evidence_for_source`) — NOT after the graph retract in the same try, else a transient graph-retract raise swallows the passage delete and leaves published-era passages indexed. Full kwarg signature (matches `passages.py` + `handle_chapter_deleted`'s call).

**knowledge-service** (`app/main.py`): remove `dispatcher.register("chapter.saved", handle_chapter_saved)` (:201) + its import. `chapter.published`/`unpublished`/`deleted` stay. Unregistered `chapter.saved` events → dispatcher no-op (statistics-service still consumes them on its own group).

**AMAW Adversary round 1 (2026-06-04, findings-cm3c-r1.md): VERDICT BLOCK → 2 folded, 1 accepted.**
- **BLOCK#1 (folded):** server-side `?editorial_status=published` filter on `getInternalBookChapters` (items + COUNT) → worker enumeration + knowledge cost-estimate both gate at the same source (no count divergence).
- **BLOCK#2 (folded):** published-but-NULL-pointer chapter → `logger.warning` + run-log (visible canon-omission), not silent debug skip.
- **WARN#3 (accept-with-note):** passage-ingest stays inline in the consumer — SAME profile as pre-CM3c `handle_chapter_saved` (already inline), not a new regression. Bulk-publish serialization bounded + deferred to CM-FE; moving ingest to worker-ai is cross-service data-layer creep, out of scope.

**AMAW Adversary round 2 (2026-06-04, findings-cm3c-r2.md): VERDICT BLOCK → 2 folded, 1 accepted (regressions from the R1 folds).**
- **R2-BLOCK#1 (folded):** `p3_is_last` scope-guard — drain path never asserts whole-book is_last (closes a latent CM3b spurious-roll-up bug); manual path stays canon-correct.
- **R2-BLOCK#2 (folded):** exact positional-arg wiring for the `editorial_status` predicate vs LIMIT/OFFSET placeholders (avoid bind collision / blackout).
- **R2-WARN#3 (accept-with-note):** dropping C12a un-suppresses publish-driven inline embed during a bounded manual job — idempotent, bounded by publish cadence, documented for CM-FE bulk-publish.

**AMAW Adversary round 3 (2026-06-04, findings-cm3c-r3.md): VERDICT APPROVED_WITH_WARNINGS → pragmatic stop (R2 folds verified sound; 3 WARN folded).**
- **R3-WARN#1 (folded):** `delete_stale_on_missing=False` on the published passage path — transient pinned-revision-fetch None must not wipe canon passages.
- **R3-WARN#2 (folded):** unpublish passage-delete = independent best-effort step, full kwargs, not chained behind the graph retract's try.
- **R3-WARN#3 (folded into test plan):** estimate↔enumerate published-parity regression-lock + live-smoke is the only Go-list-filter coverage → run required-or-explicit-defer.

**Self-review:**
- Manual rebuild now reads pinned revision (not live draft) AND skips drafts server-side → both canon=published guarantees met; the content loop is unchanged (reuses `ch.revision_id`) ✅.
- Passage cadence: publish-only, symmetric retract on unpublish ✅; existing chapters pre-published (CM1) → no regression; new chapters need explicit publish (CM-FE) — PO-confirmed UX change.
- Migrated revision-less chapters stay draft → skipped everywhere (no canon) ✅.
- **Watch (BUILD):** existing `test_handlers*` for `handle_chapter_saved` passage-ingest must migrate to `handle_chapter_published`; grep callers of `handle_chapter_saved`. Worker-ai enumerate tests must assert draft-skip (server-side) + null-pointer-WARN-skip + revision pinning + `is_last` False on a `chapters_pending` subset whose tail ≠ book tail. Book-service test must cover the `editorial_status` param filtering count+items + pagination-binds-with-param + invalid-value 400. Passage tests: `delete_stale_on_missing=False` keeps passages on None (published path); unpublish deletes passages independently of graph-retract failure. **Estimate↔enumerate parity regression-lock** (R3-WARN#3): both `count_chapters(editorial_status='published')` and the all-scope enumeration gate on published.
- **Watch (BUILD):** book-service list endpoint has no DB-backed Go test → string/build-tested; live-smoke (manual rebuild of a book with 1 draft + 1 published chapter extracts ONLY the published one, from its pinned revision) is the ONLY Go-list-filter coverage → run it REQUIRED if infra bootable, else explicit `LIVE-SMOKE deferred to D-CANON-CYCLE0-LIVE-SMOKE`.

### §8.9 CM1 design — book-service editorial lifecycle (CLARIFY-locked 2026-06-04)
**DDL** (`internal/migrate/migrate.go`, additive + idempotent; chapters table is `migrate.go:38-55`):
```sql
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'draft'
  CHECK (editorial_status IN ('draft','published'));            -- in_review dropped (YAGNI)
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS published_revision_id UUID
  REFERENCES chapter_revisions(id) ON DELETE SET NULL;          -- dangling-safe on revision purge
CREATE INDEX IF NOT EXISTS idx_chapters_editorial ON chapters(book_id, editorial_status);
-- Backfill (DO-block, runs once; idempotent via the guard): existing chapters are already canon.
--   editorial_status := 'published' AND published_revision_id := latest chapter_revisions.id
--   FOR chapters that HAVE >=1 revision; chapters with NO revision stay 'draft' (nothing to publish).
--   Guard: only touch rows where editorial_status IS still the fresh default for pre-existing data
--   (e.g. WHERE published_revision_id IS NULL AND EXISTS(revision)) so re-run is a no-op.
```
**`POST /v1/books/{book_id}/chapters/{chapter_id}/publish`** (owner-only; mirror `patchDraft` auth+tx, `server.go:1508-1545`):
- body `{ expected_draft_version?: int64 }` (echo from GET draft; mandatory from composition's prose-source per §13 PS2).
- tx: `SELECT draft_version FROM chapter_drafts … WHERE owner` (404 if no draft → **publish-empty = 400/404**); if `expected_draft_version != curr` → **409 `CHAPTER_DRAFT_CONFLICT`**; snapshot the draft via **`tx.QueryRow("INSERT INTO chapter_revisions(chapter_id,body,body_format,message,author_user_id) SELECT chapter_id,body,draft_format,'publish',$2 FROM chapter_drafts WHERE chapter_id=$1 RETURNING id").Scan(&revID)`** with a **real error check → rollback + 500** (⚠️ adversary-R1#2: do NOT copy patchDraft's fire-and-forget `_, _ = tx.Exec(...)` idiom at `:1535` — the whole canon spine depends on a real `revision_id`); `UPDATE chapters SET editorial_status='published', published_revision_id=$revID, updated_at=now()`; `insertOutboxEvent(tx,"chapter.published",chID,{book_id,chapter_id,revision_id:revID})`; commit. **Idempotent:** re-publish advances the pointer to a fresh snapshot. **Test asserts emitted `revision_id` == persisted `chapters.published_revision_id`.**
- edit-after-publish: a later `patchDraft` leaves `editorial_status='published'` and `published_revision_id` unchanged (draft diverges; canon = the published snapshot until re-publish).
**`POST …/unpublish`** (owner-only): set `editorial_status='draft'`, `published_revision_id=NULL`; emit `chapter.unpublished {book_id,chapter_id}`. **⚠️ adversary-R2-NEW-2:** a `(published, published_revision_id=NULL)` state can ALSO arise if a published chapter's pinned revision is purged (FK `ON DELETE SET NULL`) — **CM3c must tolerate it** (skip, or re-pin the latest revision), not assume a published chapter always has a pointer. (Standalone revision purge may not exist today — defensive note.) ⚠️ **KG retraction NOT wired here** → **D-CM1-UNPUBLISH-RETRACT** (CM3b wires `remove_evidence_for_source` on unpublish). Until then unpublish flips status but stale KG facts linger (documented temporary drift).
**Reads:** `getChapter` + `getInternalBookChapter` (`server.go:1860-1916`) return `editorial_status` + `published_revision_id`.
**Imports:** the bulk-import path (`parse.go:222-252`) already inserts BOTH a draft and a `chapter_revisions` row. Set `editorial_status='published'` **AND** `published_revision_id` = that revision id (⚠️ adversary-R1#3: capture via `RETURNING id` at `parse.go:252`, set in the same tx — else imported chapters are `published` with a NULL pointer and CM3c has nothing to pin → either re-introduces draft-as-canon B4 or silently never extracts the highest-volume content path). **⚠️ adversary-R2-NEW-1:** the import block (`parse.go:245-255`) is currently fire-and-forget (`_, _ = tx.Exec`); the `RETURNING id` conversion **MUST add a rollback+500 error path** (unlike the scene-loop/outbox, these inserts don't currently roll back) — a silent insert failure would put NULL into the pointer, re-creating the R1#3 failure. Import is a per-chapter tx with exactly one revision insert (`parse.go:251-253`), so per-chapter RETURNING is clean. Import keeps emitting `chapter.created` (NOT `chapter.published`) — imported chapters canonize via the **whole-book rebuild** (CM3c, which pins each chapter's `published_revision_id`, NOT a re-snapshot of the current draft), not the per-chapter event.
**Unchanged:** `chapter.saved` still emitted on every draft save (knowledge consumer switch is CM3, not CM1).
**⚠️ Migration mechanism (adversary-R1#1):** book-service has **NO down-migration** — `migrate.go` is a single forward-only idempotent `schemaSQL` blob (`Up()` only; `CREATE/ALTER ... IF NOT EXISTS` + `DO $$ ... EXCEPTION $$`). The "up/down/up" round-trip claim (plan head/§6/spec) is **FALSE for book-service** (it holds for knowledge-service, which has `run_down_migrations`). CM1 verify uses the service's real pattern instead.
**Test plan (Go unit + DB round-trip):** **`Up()` re-run idempotent** (apply twice → both columns + index + CHECK present, no error) + **backfill DO-block re-run safe** (2nd run a no-op) [NOT up/down/up]; backfill (chapter w/ revision → published+pointer; revision-less → draft); publish = revision snapshot (RETURNING id, error-checked) + pointer + status + `chapter.published{revision_id}` atomic, **emitted revision_id == persisted pointer**; publish w/o draft → 400; stale `expected_draft_version` → 409; re-publish advances pointer; **import → published + non-NULL pointer**; unpublish → draft + null pointer + `chapter.unpublished`; edit-after-publish keeps published; cross-user publish/unpublish → 403.
