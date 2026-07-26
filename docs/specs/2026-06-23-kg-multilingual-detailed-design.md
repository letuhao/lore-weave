# Detailed Design — Multilingual KG (build-ready)

**Date:** 2026-06-23 · **Status:** DETAILED DESIGN (clear-before-build) · **Branch:** `feat/kg-multilingual`
**Parents:** [spec](2026-06-23-kg-multilingual.md) · [plan](../plans/2026-06-23-kg-multilingual.md)

This doc pins concrete schemas, code-sites, algorithms, and idempotency/tenancy keys per milestone,
grounded in a code-recon pass (file:line below). Goal: a continuous long-run build with no mid-flight
clarifications.

---

## 0. Decisions resolved (recon changed several spec assumptions)

| # | Decision | Rationale (recon) |
|---|---|---|
| **DD1** | **`source_lang` is a Neo4j `:Passage`/`:Entity` property ONLY — NO Postgres column.** | Recon: passages are **Neo4j-only**; no Postgres passages table exists (`app/db/models.py` has only Project/Summary/PendingFact). Spec's "Postgres mirror" was wrong. |
| **DD2** | **Cost metering uses the EXISTING `record_spending(pool, user_id, project_id, cost)`** (updates `knowledge_projects` monthly/lifetime counters), with `cost_per_token(model)` — NOT a new usage-billing call. | Recon: that's the established pattern (`jobs/budget.py:228`, used by summary regen `regenerate_summaries.py:720-765`). Drawers already compute embed cost the same way (`drawers.py:280-297`) but don't persist it. |
| **DD3** | **Reader-language → NEW dedicated table `user_book_prefs(user_id, book_id, reader_language, PRIMARY KEY(user_id,book_id))` in book-service.** | `reading_progress` PK is `(user_id,book_id,chapter_id)` → wrong grain (would duplicate per chapter). `auth.user_preferences` is per-user JSONB → per-book value there is a tenancy smell. A small per-(user,book) table is the clean home; co-located with the reading domain. Frontend already separates UI-lang (`user_preferences.ui_language`) from reader-lang (`ReaderPage.activeLanguage`, currently ephemeral). |
| **DD4** | **kind labels → add a `name_i18n JSONB` column to each existing tier table** (`system_kinds`, `user_kinds`, `book_kinds`), NOT a new label table. | Recon: tiers are independent tables with single-tier FKs (no polymorphism) + resolution already merges them (`internal_ontology_read.go:73-108`). A JSONB col inherits each tier's scope key for free (no new tenancy surface) and rides the existing merge. System col admin-seeded; user/book populated by owner (deferred). |
| **DD5** | **`translation.published` emitted at EVERY active-version-set path (manual + auto), not just the manual one.** | Dual-index cares that "a vi version is now active", regardless of how. Recon found the manual chokepoint (`versions.py:set_active_version`); the auto-activation worker path must emit too (verify it during M2). |
| **DD6** | **Soft language preference = post-fusion additive boost + deterministic secondary sort, tuned on eval.** Retriever already degrades gracefully with no reranker (V7 caveat satisfied). | Recon: RRF scores are tiny/rank-based (~0.006–0.05), rerank is optional & replaces `relevance` not `score` (`retriever.py:116-152,244-263`). A scale-matched additive boost + lang as tiebreaker is robust; a multiplicative boost is fragile. |
| **DD7** | **Predicates are an OPEN vocabulary** (LLM emits snake_case) → label = curated map for common predicates + a `humanize(snake_case)` fallback, served from a backend resource. | Recon: predicates are free-form `r.predicate` strings, not a DB enum. No exhaustive table is possible. |

**Flag for explicit sign-off (consequential):** DD3 (new table), DD4 (JSONB vs table), DD5 (which emit
paths). The rest are mechanical.

---

## M1 — Foundation: `source_lang` + lang forward + cost metering

**Integration points (recon):**
- Passage model + upsert Cypher: `app/db/neo4j_repos/passages.py:53-84,139-186` (fields + `ON CREATE/ON MATCH SET` + `upsert_passage`).
- Ingest chokepoint: `app/extraction/passage_ingester.py:193-209` (`ingest_chapter_passages`), embed call `:304-319` (`embed_result.prompt_tokens` currently discarded), `delete_passages_for_source` at `:329-334`.
- Backfill to mirror: `passage_ingester.py:413-485` (`backfill_published_passages`), wired at `routers/public/extraction.py:1364-1395` (PUT embedding-model).
- Chapter data: `clients/book_client.py:123-180` (`list_chapters`), `:413-483` (text/blocks/revision). **None return language today.**
- Cost: `jobs/budget.py:228-253` (`record_spending`), `cost_per_token` (used in `drawers.py:280-297`).

**Changes:**
1. Add `source_lang: str = "unknown"` to `Passage` model + both `ON CREATE`/`ON MATCH SET` + `upsert_passage` param + `upsert_passages` batch.
2. `BookClient.list_chapters` (and the text fetchers) surface `original_language` per chapter — extend book-service `/internal` chapter responses to include it (additive). Ingester passes it as `source_lang`. Handle `detect_primary_language()=="mixed"` → store dominant + a `mixed: bool` prop.
3. **Cost metering (C10):** after a successful `embed_result`, compute `cost_per_token(model) * prompt_tokens` and call `record_spending(pool, user_id, project_id, cost)` — both in `ingest_chapter_passages` and the drawers path (fix the existing leak). **Skip-gate:** if `delete_passages_for_source` + re-embed would re-embed identical text, short-circuit — compare a content hash per (source_id) before re-embedding so an unchanged republish bills zero.
4. **Backfill:** new one-shot mirroring `backfill_published_passages` that reads each chapter's `original_language` (per-chapter, DD/V2) and sets `source_lang` on existing `:Passage` nodes (a lightweight Cypher SET keyed by `source_id`, no re-embed needed — pure tag backfill).

**Idempotency/tenancy:** Neo4j MERGE by passage id (existing); `record_spending` is additive per (user,project). No new tenant surface.
**Exit:** AC7. `source_lang` dormant until M4 reads it (no behavior change).
**Live-smoke:** ingest a chapter → `source_lang` set + `knowledge_projects.actual_cost_usd` increments; republish unchanged → no increment.

---

## M2 — `translation.published` event + dual-index

**Integration points (recon):**
- Emit chokepoint (manual): `translation-service/app/routers/versions.py:203-287` (`set_active_version`) — already emits `translation.reviewed` to `outbox_events` at `:265-281`. **Also find + patch the auto-activation worker path (DD5).**
- Outbox table: `translation-service/app/migrate.py:197-209`; emit pattern `routers/jobs.py:340-351`.
- Relay: `worker-infra/internal/tasks/outbox_relay.go:154-210` → `aggregate_type` routes to `loreweave:events:<type>`. Add a MAXLEN entry for `translation` (else default 10000 — acceptable).
- Consumer: `knowledge-service/app/events/consumer.py:38-42` (`STREAMS`), `app/main.py:220-252` (dispatcher.register), handler reference `app/events/handlers.py:92-248` (`handle_chapter_published` → `_ingest_published_passages`).

**Changes:**
1. **C3a (producer):** in the same txn as the active-version UPSERT, insert outbox `translation.published`, `aggregate_type="translation"`, payload `{user_id, book_id, chapter_id, chapter_translation_id, target_language, revision_id?}`. Emit at **all** activation paths (DD5).
2. Add `"loreweave:events:translation"` to consumer `STREAMS`; `dispatcher.register("translation.published", handle_translation_published)`.
3. **C3b (consumer)** `handle_translation_published`: resolve project via `book_id`; ingest the **vi** chapter text as `:Passage` nodes with `source_lang=target_language`, **index-only (NO extraction)** (R1). Key vi passages by `(source_id=chapter_id, source_lang=vi)` — distinct from zh `(chapter_id, source_lang=zh)` so delete is language-scoped. Eager re-embed on republish: `delete_passages_for_source` extended to filter `source_lang` then re-ingest (R7).

**Idempotency/tenancy:** outbox dedup by row; consumer MERGE by passage id; vi passages carry the SAME `project_id` ⇒ `purge_project` cascades (AC8). zh untouched (language-scoped delete).
**Exit:** AC5 (Layer-1 unchanged), AC8 (no orphans on purge).
**Live-smoke (≥2 services, MANDATORY):** activate a vi translation → outbox → relay → knowledge dual-indexes → a vi passage is vector-queryable.

---

## M3 — Reader-language preference storage

**Integration points (recon):**
- book-service `reading_progress`: `migrate.go:173-182` (wrong grain — informs DD3).
- auth `user_preferences`: `auth-service/migrate.go:63-67` + `/v1/me/preferences` (`handlers.go:820-867`) — per-user (UI lang lives here).
- Frontend reader lang (ephemeral): `ReaderPage.tsx:69-74` (`activeLanguage`), picker `TOCSidebar.tsx:108-126`.

**Changes (DD3):**
1. New book-service table `user_book_prefs(user_id UUID, book_id UUID, reader_language TEXT, updated_at, PRIMARY KEY(user_id, book_id))`.
2. Endpoints: `GET/PUT /v1/books/{book_id}/reader-language` (auth = book view-grant). Server SSOT, cross-device.
3. A resolver helper consumed by retrieval (M4) + consumers (M7): reader-lang(user,book) → fallback detected query lang → fallback source.

**Tenancy:** per-(user,book), grant-gated read/write. Not localStorage.
**Exit:** AC3 (set on A, seen on B).
**Live-smoke:** PUT then GET from a second session.

---

## M4 — Language-aware retrieval (D5) + eval

**Integration points (recon):**
- Retriever: `app/search/retriever.py:155-271` (`run_hybrid_search`), fusion `app/search/hybrid_fusion.py:38-58` (RRF k=60, no weights), rerank `:116-152,244-263` (optional, replaces `relevance`, degrades).
- Hit shapes: semantic `passages.py` cosine `[0.68,0.82]`; lexical `book-service/search.go:299-326` (`score`, `relevance`); RRF score `[~0.006,0.05]`.
- Endpoint: `app/routers/public/raw_search.py:65-129`.
- Benchmark: `app/benchmark/golden_set.yaml`, runner `app/benchmark/core.py:302-407`, orchestration `runner.py:177-312`, per-dimension thresholds hook exists.

**Changes (DD6):**
1. `language` param on `raw_search` + `run_hybrid_search` (optional; default = resolver from M3).
2. **Soft boost, post-fusion / pre-rerank:** each hit carries `source_lang` (semantic from passage prop; lexical from book-service chapter lang — book-service returns it). Compute
   `final_score = rrf_score + w_lang · 1[hit.source_lang == reader_pref]`, then sort by
   `(final_score desc, lang_match desc, rrf_score desc)` (deterministic). `w_lang` default ≈ one
   RRF-rank step (~0.016), **tuned on the eval set** — not guessed. Optional per-language top-K quota
   as a soft cap. Must work with rerank OFF (it already degrades).
3. **Coverage (C12):** response carries per-hit `lang` + a `coverage` note when the reader-pref
   language is absent for the queried scope (computed from which chapters have vi passages).
4. **Eval (C13):** extend `golden_set.yaml` queries with a `language` field + zh/vi/en fixture
   entities; add `recall_at_3_by_language` + per-language threshold gate via the existing
   `thresholds_by_dimension` hook. Gate: no same-language regression + improvement on
   vi-reader-on-zh-source vs baseline.

**Exit:** AC2, AC4 + eval gate.
**Live-smoke:** real vi query on a dual-indexed book → vi-first + coverage note; benchmark run green.

---

## M5 — Labels (Layer 0→2)

**Integration points (recon):**
- Tiers: `system_kinds` `migrate.go:27-38` (UNIQUE code), `user_kinds` `:1595-1617` (UNIQUE owner_user_id,code), `book_kinds` `:1704-1721` (UNIQUE book_id,code). Resolution `internal_ontology_read.go:73-108`.
- Admin: `system_admin_handler.go:74` (RS256 `admin:write`), cores `admin_core.go:185+` (shared HTTP+MCP).
- Entity names: `attribute_translations` `migrate.go:111-121` (UNIQUE `attr_value_id, language_code`); display_name = first `name`/`term` attr value (`entity_handler.go:148-153`); per-lang alias read `composePerLanguageAliases` (`select_for_context_handler.go:40-87`).
- Timeline labels: `graph_views.py:97-102` (GraphNode.name), `:121-127,295` (TimelineInstance.target_label = `obj.name`), Cypher `:270-279`. Nodes carry `glossary_entity_id`.

**Changes:**
1. **Kind labels (DD4):** add `name_i18n JSONB DEFAULT '{}'` to `system_kinds`/`user_kinds`/`book_kinds`. Admin seeds System vi labels via `admin_core` (RS256). Resolution (`internal_ontology_read.go`) carries `name_i18n`; label resolved by reader lang → fallback English `name`. **Tenancy: inherits each tier's scope key — no new shared mutable surface (avoids the `entity_kinds` bug).**
2. **Predicate labels (DD7, C5 backend-served):** curated map for common predicates + `humanize(snake_case)` fallback, exposed via a knowledge-service read endpoint (so chat/MCP/agent consumers get it, not frontend-only).
3. **Entity-name vi (C9):** populate `attribute_translations` for the `name`/`term` attr value, target language vi, via the existing translation-candidate path (`glossary_translate_handler.go:45-150`). Idempotent on `UNIQUE(attr_value_id, language_code)`; only overwrite `confidence in ('draft','machine')`, never `verified`. Glossary-locked for proper-noun consistency.
4. **Timeline/graph-view labels (C7):** resolve returned node `name` → glossary translation by `glossary_entity_id` + reader lang (a batched lookup join), fallback to canonical `name`.

**Tenancy:** System labels admin-only (RS256); user/book labels inherit tier scope; cross-tenant read denied without E0 grant.
**Exit:** AC1, AC6. **Suggest `/review-impl`** (tenancy boundary).
**Live-smoke:** vi reader sees vi kind labels + vi entity names on timeline; cross-tenant read denied.

---

## M6 — Lexical per-language (D12)

**Integration points (recon):** lexical in book-service Postgres `search.go:25-94` (`ILIKE` + `pg_trgm`, no tsvector/CJK), `migrate.go:371-373` (only `pg_trgm`); Neo4j 2026.03 has no full-text index configured.

**Pre-step (V6 live probe):** `db.index.fulltext.listAvailableAnalyzers()` (has `cjk`/`smartcn`?); test whether the Postgres image can load `pg_jieba`/`zhparser` (may need a custom image = infra change).
**Decision deferred to M6 entry:** Neo4j full-text `cjk` index vs Postgres `pg_jieba` tsvector (pick by probe + infra cost).
**Changes:** `source_lang` selects the lexical path; zh → CJK tokenizer; trigram kept as script-agnostic fallback; book-service lexical-search takes a `language` param; BookClient forwards it.
**Exit:** zh 2–3-char keyword recall materially up (measured in M4 eval, lexical subset).
**Checkpoint:** POST-REVIEW (infra change = risk boundary if custom Postgres image needed).

---

## M7 — Consumers wiring + end-to-end

**Integration points (recon):** composition `select_for_context` omits `language` (`composition-service/app/clients/glossary_client.py:45-69`); glossary supports it (`composePerLanguageAliases`). chat context build path. Reader/cowrite UI surfaces.

**Changes:** composition passes `language` (C6); chat forwards reader-language to knowledge context build; reader/cowrite surface per-hit `lang` + coverage note.
**Exit:** full scenario (vi spin-off, query original timeline, readable vi + honest coverage); re-confirm AC1–AC8 E2E.
**Live-smoke (headline E2E, ≥3 services):** translation.published → dual-index → cowrite retrieves a vi passage with vi labels + coverage.

---

## Cross-cutting build notes

- **`source_lang` must reach BOTH legs:** semantic (passage prop, M1) + lexical (book-service returns chapter `original_language`, M1/C2) — M4 boost needs it on every hit.
- **Skip-gate (M1)** doubles as the re-embed guard (M2 R7) — same content-hash check.
- Per CLAUDE.md: each milestone = size → BUILD(TDD) → VERIFY(real output + live-smoke token for M1/M2/M6/M7) → 2-stage REVIEW → POST-REVIEW → SESSION → COMMIT. M5/M7 offer `/review-impl`.
