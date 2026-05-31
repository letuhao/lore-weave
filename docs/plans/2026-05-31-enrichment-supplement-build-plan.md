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
- ✅ T1 glossary `entity_enrichments` table + migration register  *(migrate.go `UpEntityEnrichments` + main.go reg; 4 Go tests green incl. H0 conf<1.0 / origin<>'glossary' / multi-variant unique — DB `glossary_test`)*
- ☐ T2 glossary internal endpoints (POST upsert + DELETE soft-delete + emit)
- ☐ T3 lore-enrichment ports for the 2 endpoints
- ☐ T4 `_anchor_name`→canonical_name + writeback resolves+writes supplement  *(closes F-C13-2 pt.1)*
- ☐ T5 promote writes supplement(promoted) + DROP short_description write  *(closes F-C13-2 pt.2)*
- ☐ T6 retract → internal-token delete_enrichment_supplement (DROP user-jwt)  *(closes F-C13-1)*
- ☐ T7 wiki/entity read surfaces `entity_enrichments` (separate, non-blocking)
- ☐ T8 LIVE verify (no dup entity · short_description untouched · retract removes supplement · canon survives)

### Cluster 2 — wire the built-but-not-wired (PO ruling D1/D2)
- ☐ D1 gap-auto-detection wired to a production path (C7 engine has no caller)
- ☐ resume: persist request on job row + resume entrypoint that skips done gaps (DEFERRED-051)
- ☐ corpus-register API (currently a C3 501 stub)
- ☐ F-LIVE-1 stale-image guard: pin knowledge image ≥ C13 + CI check (recurs on plain `docker start`)

### Cluster 3 — quality/policy (PO rulings C1/C3)
- ☐ C1 real token metering, per-platform convention (DEFERRED-052, now MED)
- ☐ C3 defenses: hybrid flag-for-human + AUTO-REJECT egregious — needs design pass first (F-C12-1 + 050 + 058)
- ⏸️ C2 judge-diversity gate — PARKED until `main` merge (DEFERRED-056); re-decide post-merge

### Done this QC/fix arc (for the record)
- ✅ F-LIVE-2 circular import (`9a1555f0`) · ✅ do-nows 044+046 (`7be1b18d`) · ✅ QC review C0–C18 (`eed8b055`,`b42d1135`) · ✅ PO rulings (`f5cb9ae4`) · ✅ spec+plan (`9b2f012d`,`b92076e0`,`41f01c7f`,`0df29c72`)
- ✅ Cleared live: F-C2-1 (trigger installed), F-C1617-1 (licenses clean) · stale-resolved defers 048/049

---

## E. Open confirmations for PO (before BUILD) — ✅ APPROVED 2026-05-31
1. **C6 — APPROVED:** fix-forward only (no data migration for the existing broken `蓬萊` orphan; clean manually or leave dev cruft).
2. **C7 — APPROVED:** wiki read surfacing of `entity_enrichments` is a separate task (#7), NOT blocking the F-C13 fix.
3. **Scope — APPROVED:** this plan covers ONLY the F-C13-1/F-C13-2 cluster. D1 (gap-auto-detect), resume, corpus-register, C1 (token metering), C3 (auto-reject design) each get their own plan AFTER this cluster ships.
