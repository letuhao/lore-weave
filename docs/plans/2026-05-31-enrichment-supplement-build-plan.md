# PLAN — Enrichment-as-Supplement build (fixes F-C13-1 HIGH + F-C13-2 MED)

> Created 2026-05-31 · Track lore-enrichment · Branch `lore-enrichment/foundation`
> Companion to the DESIGN-LOCKED spec: [docs/specs/2026-05-31-enrichment-supplement-canon-model.md](../specs/2026-05-31-enrichment-supplement-canon-model.md)
> Phase: **CLARIFY + DESIGN + PLAN — PO-APPROVED 2026-05-31. BUILD-READY.** BUILD is the next session.
> Size: **L** (3 services; smaller than first thought — see CLARIFY C1).

---

## A. CLARIFY (implementation-level questions, resolved)

**C1 — Entity resolution (B3) is nearly free.** glossary `bulkExtractEntities` already resolves an existing entity by normalized name/alias (`findEntityByNameOrAlias` → MERGE, else create — `extraction_handler.go:437`). The F-C13-2 duplicate arose ONLY because `writeback._anchor_name` passed `target_ref` (`loc:蓬萊`) as the entity name instead of `canonical_name` (`蓬萊`). **Resolution = pass `canonical_name` to extract-entities; glossary matches the existing canonical entity.** No new resolution infra, no need for gaps to carry `glossary_entity_id`. Anchor naming uses `canonical_name` (faithful), never `target_ref`.

**C2 — KG anchor canonization is moot now.** Because facts will anchor on the RESOLVED canonical `glossary_entity_id` (the node glossary_sync already created as `source_type=glossary`), there is NO separate enriched anchor to canonize. The parallel `loc:蓬萊` node simply stops being created. The KG merge key already matches (`{user_id, glossary_entity_id}`).

**C3 — Two-layer dual-store is intentional (keep both).** Per-dimension enriched content lives in BOTH: `entity_enrichments` (glossary — the authored/wiki layer) and KG `:Fact` nodes (the semantic/RAG layer), both anchored to the same canonical entity. This matches the platform two-layer pattern (CLAUDE.md). NOT redundant — different consumers.

**C4 — `short_description` is original-canon only.** Promote STOPS writing makeup into `short_description` (revert the 053 behavior). Enrichment content goes to `entity_enrichments`. (Resolves the B1 "never conflate" requirement.)

**C5 — Variants:** multiple per `(entity_id, dimension)` keyed by `proposal_id` (PO-locked). All variants stay active (no single "current"); retract removes ONE proposal's variant set. Wiki/read shows original canon + each enrichment variant labeled.

**Defaulted (PO may override at review):**
- **C6 existing orphaned data:** fix-forward. The current live broken `蓬萊` (parallel `loc:蓬萊` entity `019e78d4` + its now-retracted facts) is dev/demo cruft — cleaned by a one-off script or left; NOT a production data migration. (Flag for confirm.)
- **C7 wiki read of `entity_enrichments`:** the C5 wiki renderer already distinguishes enriched vs canon; extend it (or the entity read) to surface `entity_enrichments` as the labeled supplement section. (Small follow-up; can be a separate task.)

## B. DESIGN (concrete)

### B1. glossary schema — `entity_enrichments`
```sql
CREATE TABLE IF NOT EXISTS entity_enrichments (
  enrichment_id  UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id      UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  book_id        UUID NOT NULL,
  dimension      TEXT NOT NULL,                 -- 历史/地理/文化/features/inhabitants
  content        TEXT NOT NULL,
  origin         TEXT NOT NULL DEFAULT 'enrichment'
    CHECK (origin <> '' AND origin <> 'glossary'),
  technique      TEXT NOT NULL,
  confidence     NUMERIC(4,3) NOT NULL CHECK (confidence > 0 AND confidence < 1.0),
  proposal_id    UUID NOT NULL,                 -- variant identity
  review_status  TEXT NOT NULL DEFAULT 'proposed'
    CHECK (review_status IN ('proposed','promoted')),
  promoted_by    UUID, promoted_at TIMESTAMPTZ,
  deleted_at     TIMESTAMPTZ,                   -- retract = soft-delete (reversible)
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_id, dimension, proposal_id)    -- multiple variants per (entity,dimension)
);
CREATE INDEX IF NOT EXISTS idx_entity_enrichments_live
  ON entity_enrichments(book_id, entity_id) WHERE deleted_at IS NULL;
```
H0 invariant carried into the table: `confidence < 1.0`, `origin <> 'glossary'`, `review_status` never canon. Added via `UpEntityEnrichments(ctx, pool)` in `migrate.go`, registered in `cmd/glossary-service/main.go`.

### B2. glossary internal endpoints (X-Internal-Token, mirror `canon_content_handler.go`)
- `POST /internal/books/{book_id}/entities/{entity_id}/enrichments`
  body: `{proposal_id, technique, review_status, promoted_by?, promoted_at?, facts:[{dimension,content,confidence}]}`
  → upsert variant rows for this proposal (ON CONFLICT (entity_id,dimension,proposal_id) DO UPDATE), `deleted_at=NULL`. Emits `glossary.entity_updated` (so C4 sync runs). 200 `{written:n}`.
- `DELETE /internal/books/{book_id}/entities/{entity_id}/enrichments?proposal_id=`
  → `UPDATE entity_enrichments SET deleted_at=now() WHERE entity_id=? AND proposal_id=? AND deleted_at IS NULL`. Emits the event. 200 `{soft_deleted:n}`. **Internal-token — this is what fixes F-C13-1 (no user JWT needed).**

### B3. lore-enrichment changes
- `writeback.py _anchor_name`: return `canonical_name` (faithful) — drop the `target_ref`-first behavior (B3/C1).
- `clients/writeback.py`: add `upsert_enrichment_supplement(book_id, entity_id, proposal_id, technique, review_status, facts, promoted_*)` + `delete_enrichment_supplement(book_id, entity_id, proposal_id)` (internal-token).
- `services/writeback.py`:
  - `write_back`: resolve canonical entity via extract-entities(name=canonical_name) [already returns the matched id]; write supplement rows (`review_status='proposed'`) via the new port; KG quarantine write unchanged (now on the canonical id).
  - `promote`: write supplement rows `review_status='promoted'` (+ promoted_by/at) via the port; **remove the `set_glossary_canon_content` short_description write** (C4); KG `enriched-promote` unchanged (facts on canonical node).
  - `retract`: call `delete_enrichment_supplement` (internal-token) + `retract_enriched_facts` (KG) — **drop `soft_delete_glossary_entity` (user-jwt) for enrichment**; the canonical entity + its original canon are untouched. (F-C13-1.)

### B4. Sequence (promote, after fix)
```
author promote → resolve canonical entity (extract-entities by canonical_name)
  → upsert entity_enrichments rows (review_status=promoted, markers)        [glossary, internal-token]
  → enriched-promote facts → source_type=glossary on the canonical node     [KG]
  → mark_promoted (proposal row)                                            [lore-enrichment pg]
  → NO short_description write
retract → delete_enrichment_supplement(proposal_id) (soft-delete rows)      [glossary, internal-token]
        → retract_enriched_facts (valid_until)                              [KG]
        → original canon entity + short_description untouched
```

## C. PLAN (ordered tasks; each independently testable)

| # | Task | Files | Tests |
|---|---|---|---|
| 1 | `entity_enrichments` table + migration register | `glossary/internal/migrate/migrate.go`, `cmd/glossary-service/main.go` | migrate applies on a fresh DB; table + constraints exist |
| 2 | glossary internal enrichment endpoints (POST upsert + DELETE soft-delete, emit events) | new `glossary/internal/api/enrichment_handler.go` + route reg in `server.go` | Go handler tests (mirror `canon_content_test.go`): 200/auth-401/404-entity/soft-delete-emits/idempotent-upsert |
| 3 | lore-enrichment ports for the 2 endpoints | `lore-enrichment/app/clients/writeback.py` | unit: port builds request, internal-token header, parses resp |
| 4 | `_anchor_name`→canonical_name (B3) + writeback resolves+writes supplement | `lore-enrichment/app/services/writeback.py` | unit: resolves-not-mints (canonical_name passed); supplement rows written `proposed` |
| 5 | promote writes supplement(promoted) + DROPS short_description write (C4) | `services/writeback.py` | unit: short_description untouched; supplement rows `promoted` + markers |
| 6 | retract → internal-token `delete_enrichment_supplement` (DROP user-jwt soft-delete) | `services/writeback.py`, `api/proposals.py` | unit + **API-level (TestClient) retract**: supplement soft-deleted, entity survives |
| 7 | (follow-up) wiki/entity read surfaces `entity_enrichments` as the labeled supplement | `glossary` wiki/entity read | render test |
| 8 | LIVE verify (§ spec 6) | — | fresh promote: no duplicate entity, short_description untouched, supplement carries markers; retract: supplement gone, canon survives — all live |

**Build order rationale:** glossary first (1→2, the schema+API other layers call), then lore-enrichment (3→6) bottom-up (ports → writeback → promote → retract), then read-surface (7), then live verify (8). Task 6 closes **F-C13-1**; tasks 4+5 close **F-C13-2**.

**Verification note (F-LIVE-3 / Go):** glossary Go tests need `go test` in the build context (run in a build container or `docker compose run`); lore-enrichment Python tests need pytest (install in a test image / dev venv). Confirm the test runner at BUILD start. The cheap live assertions (DB/Neo4j queries, like the Step-3 audit) are the backstop.

## D. Acceptance (gates BUILD done)
- F-C13-2: a fresh promote attaches to the canonical entity (no parallel `loc:` node); `short_description` original-canon untouched; supplement rows carry origin/technique/markers. Live-proven.
- F-C13-1: retract soft-deletes the supplement via the internal path; canonical entity + original canon survive; live-proven (the inverse of the capstone we just ran).
- H0 intact: supplement quarantined (`proposed`, conf<1.0) until promote; markers permanent; retract reversible.
- No relitigation of H0 / locked baseline; DEFERRED-053 superseded (no short_description overwrite).

## F. PROGRESS TRACKER (single source of truth — update every session)

> Status keys: ☐ TODO · ◐ IN-PROGRESS · ✅ DONE · ⏸️ BLOCKED/PARKED. Update the box + a one-line note (commit sha) as work lands. Keep this in sync with `DEFERRED.md` + `SESSION_HANDOFF.md`.

### Cluster 1 — F-C13-1 (HIGH) + F-C13-2 (MED): enrichment-as-supplement  [this plan, §C]
- ✅ T1 glossary `entity_enrichments` table + migration register  *(`aff2c505` — migrate.go `UpEntityEnrichments` + main.go reg; 4 Go tests green incl. H0 conf<1.0 / origin<>'glossary' / multi-variant unique — DB `glossary_test`)*
- ✅ T2 glossary internal endpoints (POST upsert + DELETE soft-delete + emit)  *(`enrichment_handler.go` + 2 routes in `server.go`; 13 Go tests green: auth/400/404/422 · upsert writes proposed rows + short_description untouched + emits · idempotent upsert · promoted markers · soft-delete + entity survives + idempotent. Pre-existing unrelated `TestListEntities_*` backfill failures noted — my code path isn't reached by them.)*
- ✅ T3 lore-enrichment ports for the 2 endpoints  *(`clients/writeback.py` `upsert_enrichment_supplement` + `delete_enrichment_supplement`; 7 respx tests green: request shape · internal-token (no JWT) · query param · promoted markers · neutralize · idempotent-0 · retryable 503/timeout)*
- ✅ T4 `_anchor_name`→canonical_name + writeback resolves+writes supplement  *(closes F-C13-2 pt.1)* — *`services/writeback.py`: `_anchor_name` prefers `canonical_name` (蓬萊) over synthetic `target_ref` (loc:蓬萊); `write_back` upserts supplement `proposed` on the resolved entity, never short_description. 26 pytest green (2 new: resolves-canonical-name, proposed-supplement-not-short-desc).*
- ✅ T5 promote writes supplement(promoted) + DROP short_description write  *(closes F-C13-2 pt.2)* — *promote (both first + idempotent re-promote branches) upserts the PROMOTED supplement via `_write_promoted_supplement`; removed `_heal_glossary_canon_content` + the `get/set_glossary_canon_content` ports (dead). short_description never written by enrichment.*
- ✅ T6 retract → internal-token delete_enrichment_supplement (DROP user-jwt)  *(closes F-C13-1)* — *retract soft-deletes the supplement via the internal token (no JWT); removed `soft_delete_glossary_entity`; `RetractResult.glossary_recycled`→`supplement_retracted`; API returns `supplement_retracted`. Added API-level TestClient retract test (the gap the unit tests missed) — proves no JWT threading + 403 non-owner. 58 pytest green (review-gate 36 + ports 7 + clients 15).*
- ✅ T7 wiki/entity read surfaces `entity_enrichments` (separate, non-blocking)  *(`wiki_render.go`: new `Enrichments` input + 增补设定（dị bản）section — distinct heading, non-canon disclaimer, 【增补·dim】per-variant items, source_type=enriched marker; `wiki_handler.go` `loadEntityEnrichments` (live rows) wired into `generateWikiStubs`. 2 render tests + DB suites green.)*
- ✅ T8 LIVE verify (no dup entity · short_description untouched · retract removes supplement · canon survives)  *(rebuilt glossary+lore-enrichment; migration live on `loreweave_glossary`. `tests/live_verify_t8.py` + real-Qwen `live_smoke_c14_job.py`: promote resolved CANONICAL 蓬萊 `019e7850-aa72` (NO parallel mint), short_description UNCHANGED (`蓬萊海島…`), 5 PROMOTED supplement rows (origin=enrichment, promoted_by set); retract API 200 NO-JWT → supplement_retracted=5, canonical entity SURVIVES, short_description still unchanged. **F-C13-1 + F-C13-2 LIVE-PROVEN fixed.**)*

### Cluster 2 — wire the built-but-not-wired (PO ruling D1/D2)
- ◐ D1 gap-auto-detection wired to a production path (C7 engine has no caller) — **read-only detect endpoint DONE** (auto-enrich job mode deferred to a follow-up per PO). glossary `GET /internal/books/{id}/enrichment-coverage` (entities + mention_count + promoted-enrichment dims) → `GlossaryClient.list_enrichment_coverage` → `coverages_from_rows` (label→Dimension, skips unmodeled kinds) → `POST /v1/lore-enrichment/projects/{id}/detect-gaps` (read-only, ranked) via the existing `detect_ranked_gaps`. Spec path added; Go coverage test + pytest builder/endpoint/port tests; full pytest 463 pass. **Live-proven:** demo book → 5 LOCATIONs ranked from 11 scanned (non-LOCATION skipped; retracted enrichment correctly not counted as coverage).
- ✅ resume: persist request + resume entrypoint that skips done gaps (DEFERRED-051 / F-C14-1) — *spec [docs/specs/2026-05-31-resume-worker.md]; PO: separate `enrichment_job_request` table · new `lore-enrichment-worker` service · existing cap · full live verify. `runner.run_job(skip_gap_refs=)` skips done gaps BEFORE charge+run_gap (token-safe); create persists the request; resume enqueues to a Redis stream + 202; the worker consumes, rebuilds via `build_live_runner(spent_so_far=)`, re-drives skipping done. 465 unit pass + 2 runner skip-done tests. **Live-proven:** resume API 202 → worker `→ completed (skipped_done=1, new_proposals=0, spent=1.5)`, no LLM call on the done gap, job completed.*
- ✅ corpus-register API (was a C3 501 stub) — *PO: two-call (metadata register + separate ingest) + real list. `sources.py`: POST /sources (register, idempotent, default-deny license), POST /sources/{id}/ingest (chunk + real bge-m3 embed via the existing `store.ingest_corpus`), GET /sources (real list + chunk_count). Store: `get_corpus`/`list_corpora` + provenance on `upsert_corpus`. Spec + contract tests updated; 469 unit + 4 sources tests. **Live-proven:** register→corpus_id (PD license + provenance), ingest→chunks_embedded=1 (real embed, BYOK), list→chunk_count. (A 502 surfaced the demo fixture's cross-user embed-model ownership — endpoint correctly scopes embed to the acting user; proven with the model owner.)*
- ✅ F-LIVE-1 stale-image guard *(spec [docs/specs/2026-05-31-stale-image-guard.md], PO: stamp+probe / all services / live-smoke+gate)* — `scripts/check_stack_freshness.py` (tier-2 git-SHA-label drift → tier-1 image-`.Created` proxy + H0 route-probe; 7 unit tests) · `x-build-labels` anchor on all 23 compose build blocks + `scripts/build-stack.sh` · wired into `live_smoke_c14_job.py`+`live_verify_t8.py` (probe gate, abort on 404) + `workflow-gate.py check-stack` (advisory). Live-proven: stamped knowledge rebuild → `FRESH sha=2fb036b8 (tier-2)`; probe distinguishes present vs 404. Route-probe = authoritative gate; drift = advisory (over-warns safely on build-then-commit — documented §6b).

### Cluster 3 — quality/policy (PO rulings C1/C3)
- ☐ C1 real token metering, per-platform convention (DEFERRED-052, now MED)
- ☐ C3 defenses: hybrid flag-for-human + AUTO-REJECT egregious — needs design pass first (F-C12-1 + 050 + 058)
- ⏸️ C2 judge-diversity gate — PARKED until `main` merge (DEFERRED-056); re-decide post-merge

### /review-impl round (post-T8 adversarial pass — 2026-05-31)
Deep adversarial review of the 8 commits found 0 HIGH, 2 MED, 5 LOW/COSMETIC + a C6 note. **All fixed:**
- ✅ MED-1 wiki surfaced PROPOSED (quarantined) enrichments → `loadEntityEnrichments` now filters `review_status='promoted'` (only author-approved supplements reach the public wiki).
- ✅ MED-2 retract trusted client `glossary_entity_id` over the proposal's record → precedence flipped to `promoted_entity_id` → `writeback_entity_id` → client (last resort), so a wrong/stale id can't orphan the supplement.
- ✅ LOW-3 Go endpoint now neutralizes the `dimension` label too (reaches the wiki render), not just content.
- ✅ LOW-4 `promoted_at` validated as RFC3339 → clean 400 (was a DB 500 on garbage).
- ✅ LOW-5 the per-fact upsert loop now runs in ONE transaction (no partial-write window); validate-all-before-write.
- ✅ LOW-6 `promoted` row must carry `promoted_by` — handler 400 + DB CHECK `entity_enrichments_promoted_has_marker`.
- ✅ LOW-7 `live_verify_t8.py` gained a Neo4j assertion (facts anchor on the canonical node).
- ✅ COSMETIC-8 render test uses promoted-only inputs (matches the loader contract).
- ✅ C6 cruft: `scripts/cleanup_loc_orphans.py` (dry-run default) soft-deleted 4 glossary `loc:` orphans + detach-deleted 4 Neo4j nodes / 40 orphan facts.
Tests added: Go promoted-without-promoted_by 400, bad-promoted_at 400, dimension-neutralize, loader-promoted-only; pytest retract-prefers-proposal-id. Go enrichment+wiki suites green; pytest 443 pass.

### Done this QC/fix arc (for the record)
- ✅ F-LIVE-2 circular import (`9a1555f0`) · ✅ do-nows 044+046 (`7be1b18d`) · ✅ QC review C0–C18 (`eed8b055`,`b42d1135`) · ✅ PO rulings (`f5cb9ae4`) · ✅ spec+plan (`9b2f012d`,`b92076e0`,`41f01c7f`,`0df29c72`)
- ✅ Cleared live: F-C2-1 (trigger installed), F-C1617-1 (licenses clean) · stale-resolved defers 048/049

---

## E. Open confirmations for PO (before BUILD) — ✅ APPROVED 2026-05-31
1. **C6 — APPROVED:** fix-forward only (no data migration for the existing broken `蓬萊` orphan; clean manually or leave dev cruft).
2. **C7 — APPROVED:** wiki read surfacing of `entity_enrichments` is a separate task (#7), NOT blocking the F-C13 fix.
3. **Scope — APPROVED:** this plan covers ONLY the F-C13-1/F-C13-2 cluster. D1 (gap-auto-detect), resume, corpus-register, C1 (token metering), C3 (auto-reject design) each get their own plan AFTER this cluster ships.
