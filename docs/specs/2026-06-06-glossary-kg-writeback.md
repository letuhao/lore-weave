# Spec — Glossary KG→Writeback Loop (glossary AI-pipeline v2, mũi #1)

- **Date:** 2026-06-06
- **Branch:** `glossary/ai-pipeline-v2`
- **Phase:** CLARIFY ✅ resolved (PO confirmed all defaults 2026-06-06) → DESIGN locked (pre-PLAN). No production code yet.
- **Task size (provisional):** **L** — ≥2 services (knowledge-service Py + glossary-service Go + frontend), side effects (new event/poll path, FE surface, possibly 1 additive column). Cross-service ⇒ live-smoke required at VERIFY.
- **Parent architecture:** `docs/03_planning/GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md` (this is **mui #1**, the foundation that establishes the AI Suggestions inbox reused by **mui #1c** entity-resolution/merge).
- **Author:** session glossary-ai-pipeline-v2 audit

---

## 1. Context & Problem

The glossary pipeline was built before RAG + knowledge-service existed. Today the ecosystem (knowledge-service, lore-enrichment, composition) is built on glossary, but the **glossary↔knowledge seam is one-way**:

- ✅ **glossary → KG**: `glossary.entity_updated` event → knowledge-service MERGEs into Neo4j, anchored via `glossary_entity_id`.
- ❌ **KG → glossary**: knowledge-service extracts entities with an LLM (Pass 2) but **never writes its discoveries back to the glossary SSOT**. The AI's findings die in Neo4j; the user's glossary stays manually curated.

This is the core "CRUD-like / rời rạc / lãng phí" complaint: the strongest extractor in the system (knowledge-service) does not feed the authored surface (glossary).

**Irony confirmed in audit:** lore-enrichment-service *does* write back to glossary (via `extract-entities`); knowledge-service does not.

## 2. Goal / Non-Goals

**Goal:** Close the KG → glossary loop. After knowledge-service extracts a chapter, its newly-discovered, sufficiently-confident entities are **proposed back to glossary as review-able drafts**. The user reviews/promotes; promotion makes them canon (and the existing glossary→KG sync then anchors them, closing the cycle).

**Non-goals (this mui):**
- Attribute/relation/fact writeback (deferred to mui #1b — start with NEW ENTITIES only).
- Semantic retrieval for glossary (that's mui #4).
- Shared grounding port (mui #3).
- Any change to the LLM extraction logic itself.
- Auto-promotion to canon (the human review gate is the whole point).

## 3. What already exists (the wired-up inventory)

Deep-dive (2026-06-06) found ~80% of the infra already built but **unconnected**:

| Piece | Status | Location |
|---|---|---|
| Writeback client `propose_entities(book_id, entities, ...)` → `POST /extract-entities` | ✅ EXISTS, **nothing calls it** | `knowledge-service/app/clients/glossary_client.py:403-435` |
| Query for discovered-unanchored entities (`glossary_entity_id IS NULL` + mention threshold) | ✅ EXISTS | `knowledge-service/app/extraction/entities.py:1323-1354` (`find_gap_candidates`) |
| Extractor→glossary kind map | ✅ EXISTS | `entity_resolver.py:69-75` (`_EXTRACTOR_TO_GLOSSARY_KIND`) |
| Review gate: `extract-entities` lands entities at `status='draft'` (NOT canon) | ✅ EXISTS | `glossary-service/internal/api/extraction_handler.go:753-756` |
| `park_unknown_kinds=false` opt-out (comment *names knowledge-service* as the intended caller) | ✅ EXISTS | `extraction_handler.go:343-351` |
| Hook point after Pass 2 write (best-effort, non-fatal, P3 pattern) | ✅ available | `knowledge-service/app/routers/internal_extraction.py:491-548` |
| Loop safety (draft boundary + name dedup + Neo4j PK idempotent on `glossary_entity_id`) | ✅ LOW risk | see §7 |
| FE review surface for **unknown-kind** parked entities | ✅ EXISTS | `frontend/src/features/glossary/hooks/useUnknownReview.ts`, `components/UnknownEntitiesPanel.tsx` |

**Verified false:** glossary has NO `/facts/{fact_id}/promote` endpoint (an earlier audit report was wrong). lore-enrichment uses `canon-content` + `enrichments`.

## 4. Design — the loop

```
chapter.published → Pass 2 LLM extraction → write_pass2_extraction() → Neo4j
                                                       │
                              (NEW WIRE, best-effort, non-fatal)
                                                       ▼
              find_gap_candidates(source-scoped, conf+mention threshold)
                                                       │  filter unanchored (glossary_entity_id IS NULL)
                                                       ▼
              map kind via _EXTRACTOR_TO_GLOSSARY_KIND, build payload
                                                       ▼
              glossary_client.propose_entities(book_id, entities, park_unknown_kinds=false)
                                                       ▼
        glossary POST /extract-entities → entity rows at status='draft', tag 'ai-suggested'
                                                       ▼
        FE "AI Suggestions" inbox → user promotes (draft→active) / rejects
                                                       ▼
        promote → glossary.entity_updated → knowledge MERGE sets glossary_entity_id  ← cycle closed
```

### 4.1 Payload mapping (knowledge → `extractedEntity`)

`extractedEntity` shape (glossary `extraction_handler.go:353-359`): `{kind_code, name, attributes: map, evidence, chapter_links}`. **No confidence field** — confidence is the knowledge-side filter only; glossary stores draft + tag.

| glossary field | source from KG `:Entity` |
|---|---|
| `kind_code` | `_EXTRACTOR_TO_GLOSSARY_KIND[entity.kind]` (fallback: original kind) |
| `name` | `canonical_name` |
| `attributes["aliases"]` | `aliases` (JSON array) |
| `attributes["description"]` | short summary if available (optional) |
| `evidence` | top evidence snippet (from EVIDENCED_BY) — optional |
| `chapter_links` | source chapter id/index/title for this extraction |
| request `park_unknown_kinds` | **`false`** (opt out of unknown bucket — don't flood triage with experimental KG kinds) |

## 5. Policy decisions — LOCKED (PO confirmed 2026-06-06)

| # | Decision | **LOCKED value** | Rationale |
|---|---|---|---|
| **P1** | **Threshold** to writeback | ✅ `confidence ≥ 0.7` **AND** `mention_count ≥ 10` *(revised from ≥3 per ADJ-1, PO 2026-06-06 — `mention_count` is project-wide cumulative; KSA §3.4.E recommends 50, 10 is the chosen middle)* | Pass 2 writes `pending_validation=False` and there is **no K18 validator yet**, so this threshold is the only quality gate. **Tunable via config** (env/`knowledge_projects` setting), not hardcoded. |
| **P2** | **When** to writeback | ✅ **End-of-extraction-job, best-effort, non-fatal** (P3 enqueue pattern). Not per-entity, not synchronous. | Draft gate already prevents canon pollution, so auto-propose is safe. Batching = fewer glossary calls + dedup. On glossary outage → queue in `extraction_pending` (client already advises this). |
| **P3** | **Scope** | ✅ **NEW entities only** (kind=character/location/item/etc.). Attributes/relations deferred to mui #1b. | One closed loop running beats a half-built bigger one. Entity infra is 100% ready. |
| **P4** | **Provenance marker** | ✅ **Reserved tag `ai-suggested`** on the entity `tags TEXT[]` (no schema change). | `extractedEntity` has no origin field and the entity table has no created-by-AI column; `tags` already exists. Lowest-friction. Revisit a dedicated column only if tag-based filtering proves insufficient. |
| **P5** | **Reject semantics** | ✅ **Soft-archive (`status='inactive'`) + tombstone** so a rejected name is NOT re-proposed by a later job. | Avoids re-reviewing the same entity every extraction. See §8 for tombstone design. |

## 6. FE surface

- **Reuse the review pattern** from `useUnknownReview` / `UnknownEntitiesPanel` (kind-resolution epic E3) — same shape: a queue, per-item resolve, invalidate on action.
- **New surface:** "AI Suggestions" inbox = entities where `status='draft'` AND tag `ai-suggested`. Actions: **Promote** (draft→active, reuse existing PATCH status), **Edit then promote**, **Reject** (→ inactive or delete).
- Needs a glossary list filter by status + tag (verify whether `GET /entities` already supports status filter; if not, additive query param).

## 7. Loop safety (verified LOW risk)

1. knowledge writes glossary draft → glossary emits `glossary.entity_updated` (actor_type=`pipeline`) → knowledge MERGEs Neo4j.
2. MERGE is idempotent on `glossary_entity_id` (Neo4j unique constraint) — re-emit is a no-op.
3. `extract-entities` dedups on `(book_id, kind_id, normalized_name)` — re-proposing the same name won't multiply.
4. Drafts are NOT in knowledge's active-canon query, so they don't re-feed extraction.
5. `actor_type='pipeline'` ⇒ learning-service ignores (no correction-capture loop).
**No infinite loop.** Worst case: a draft proposed, event fires, KG re-merges the same node — idempotent.

## 8. Tombstone design (from P5)

To stop a rejected entity from being re-proposed by a later extraction job, "Reject" must leave a durable marker the writeback step checks before proposing.

**Decision point for PLAN — where the tombstone lives:**
- **Option A (glossary-side, preferred):** Reject sets `status='inactive'` + adds tag `ai-rejected` (and keeps `ai-suggested`). The glossary dedup in `extract-entities` already matches on `(book_id, kind_id, normalized_name)` — extend it so a re-proposed name that matches an `ai-rejected` row is **skipped** (returned as `skipped`, not re-created/re-activated). Zero new table; reuses existing name-dedup path.
- **Option B (knowledge-side):** track rejected `(name, kind)` in a knowledge-service table and filter in `find_gap_candidates`. More work, splits the source of truth.

**Lean: Option A** — the rejection is a glossary fact, and glossary already owns name dedup. Confirm in PLAN after reading the exact dedup code path (`findEntityByNameOrAlias`, `extraction_handler.go:673-741`).

**Edge:** user later wants a rejected entity back → clearing the `ai-rejected` tag / reactivating is the un-reject. In scope for FE (toggle), cheap.

## 8b. CLARIFY resolutions (PO 2026-06-06)

All open questions resolved → see §5 LOCKED table. Summary: auto end-of-job · `conf≥0.7 & mention≥3` (config-tunable) · tag `ai-suggested` · reject = soft-archive + tombstone (Option A leaning) · NEW-entities-only for v1.

## 9. Phasing (provisional, post-CLARIFY)

1. **BE-1 (knowledge):** wire `propose_entities` at job completion — config-driven threshold filter (`conf≥0.7 & mention≥3`), kind-map, payload build, `park_unknown_kinds=false`, best-effort + queue-on-outage. Unit + a live cross-service smoke (chapter → draft appears in glossary).
2. **BE-2 (glossary):** stamp tag `ai-suggested` on entities arriving via writeback; add status/tag list-filter query param to `GET /entities`; extend name-dedup so a re-proposed name matching an `ai-rejected` tombstone is **skipped** (P5 / §8 Option A). Confirm via `findEntityByNameOrAlias` (`extraction_handler.go:673-741`).
3. **FE-1:** "AI Suggestions" inbox (reuse `useUnknownReview`/`UnknownEntitiesPanel` pattern) + promote (draft→active) / edit-then-promote / reject (→inactive + `ai-rejected` tag) / un-reject toggle.
4. **VERIFY:** cross-service live-smoke token mandatory (≥2 services touched) — `live smoke: chapter extraction → ai-suggested draft visible + promote→active→KG anchor`.

---

## review-impl findings (2026-06-07)

- **HIGH-1 — FIXED (commit e564e2f7):** writeback fired per-chapter; now gated to end-of-book via `should_writeback(is_last_chapter_of_book)` + unit coverage.
- **MED-2 — accepted/documented:** confidence floor is applied in Python *after* `find_gap_candidates`' mention-ordered `LIMIT`, so high-confidence/low-mention entities outside the top-N are not proposed. Fine at `limit=100`; push the floor into the Cypher if it bites (shared infra — defer).
- **LOW-1 — accepted/documented:** writeback doesn't pass `source_language`, so `propose_entities` defaults `"en"` and zh entities' name/alias attrs are tagged `en`. Cosmetic metadata; ideally resolve from BookProfile later.
- **LOW-3 — accepted/documented:** discovered entities whose kind isn't a glossary kind are silently dropped by glossary (`park_unknown_kinds=false`, intentional) — no skip count is logged.
- **LOW-2 — addressed:** the gate predicate now has unit coverage; the broader router-hook path (book_id resolution, best-effort swallow) is covered by the live smoke (DEFERRED 061).

## Appendix — files of record

- knowledge writeback client: `services/knowledge-service/app/clients/glossary_client.py:403-435`
- discovered-entity query: `services/knowledge-service/app/extraction/entities.py:1323-1354`
- kind map: `services/knowledge-service/app/extraction/entity_resolver.py:69-75`
- Pass2 completion hook: `services/knowledge-service/app/routers/internal_extraction.py:491-548`
- glossary extract-entities handler: `services/glossary-service/internal/api/extraction_handler.go:339-610` (draft create at 753-756; outbox emit 579-595)
- FE review pattern: `frontend/src/features/glossary/hooks/useUnknownReview.ts`, `components/UnknownEntitiesPanel.tsx`
