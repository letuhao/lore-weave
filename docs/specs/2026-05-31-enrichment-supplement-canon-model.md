# Spec — Enrichment-as-Supplement Canon Model (fixes F-C13-2 + F-C13-1)

> Created 2026-05-31 · Track: lore-enrichment · Branch `lore-enrichment/foundation`
> Origin: QC review of the RAID run (QC_REVIEW_C0-C18.md) + PO decision rulings B1/B2/B3.
> Status: **CLARIFY/DESIGN — awaiting PO confirmation of the data-model option + open questions.**
> Size: **L/XL** (2 services + a glossary schema change) → spec-first per the workflow.

## 1. Problem (live-confirmed)
The QC live audit proved the promote→canon path is broken at the entity level:
- **F-C13-2 (MED, live):** a promoted enrichment is ORPHANED from the canonical entity. After promote, Neo4j has TWO 蓬萊 nodes — the canonical `蓬萊` (`019e7850`, `source_type=glossary`) and a parallel `loc:蓬萊` (`019e78d4`, stuck `enriched:retrieval`/pending). The 5 promoted facts are canon but hang off the parallel anchor, not the canonical entity. A RAG/graph consumer querying canonical 蓬萊 sees none of the enrichment.
- **Root causes:** (1) `writeback._anchor_name` prefers `target_ref` and passes it as the glossary entity *name* → glossary mints a NEW entity instead of resolving the existing canonical one; (2) `enriched-promote` (KG) flips only `:Fact` nodes, never the `:Entity` anchor; (3) promote step 5 OVERWRITES the entity's `short_description` with enriched content — conflating makeup into original canon.
- **F-C13-1 (HIGH):** retract's glossary recycle is unreachable (handler passes no jwt; `Principal` has no token) AND it soft-deletes the WHOLE entity — which, once enrichment resolves onto the real canonical entity, would wrongly delete original canon.

## 2. Constraints (PO rulings — binding)
- **B1:** glossary = the SINGLE SSOT. Enrichment is a **distinguished supplement / `dị bản` (variant)** of the original canon — never merged into / overwriting original canon, never a parallel entity. Must stay tellable-apart for life (else lore disputes).
- **B2:** enrichment MAY add glossary-service endpoints/schema.
- **B3:** writeback must **RESOLVE the existing canonical glossary entity** (via `glossary_entity_id`), never mint from `target_ref`-as-name.
- **H0 (unchanged):** enriched ≠ canon until author promote; permanent origin marker; quarantine.

## 3. Data-model options (THE decision needed)
Where does the enrichment supplement live on the canonical entity?

| | Option | Pros | Cons |
|---|---|---|---|
| (a) | New column on `glossary_entities` (`enrichment_description` + origin meta) | simplest; 1 migration | one supplement per entity only; no per-dimension structure; no multiple `dị bản`; provenance cramped |
| (b) | EAV attribute (`enrichment` kind) | reuses attribute system; flexible | mixes makeup into the authored-attribute space (blurs the B1 "distinguish" line); retract = delete attr value; provenance awkward |
| (c) **★rec** | **Separate linked table `entity_enrichments`** (FK→entity) | physically separates enrichment from original canon (best B1 fit); per-dimension rows; supports multiple variants; full provenance (origin/technique/confidence/proposal_id/promoted_by/at/review_status/deleted_at); clean soft-delete retract | most work (new table + migration + endpoints) |

**Recommendation: (c).** It is the only option that *structurally* guarantees original canon and enrichment never conflate (the B1 core requirement) and makes retract a clean per-supplement soft-delete.

## 4. Proposed design (assuming option c — adjust if PO picks a/b)
**glossary-service (Go):**
- New table `entity_enrichments(enrichment_id, entity_id FK, book_id, dimension, content, origin='enrichment', technique, confidence, proposal_id, promoted_by, promoted_at, review_status, deleted_at, created_at, updated_at)`.
- New internal endpoints (internal-token, mirroring `canon-content`):
  - `POST /internal/books/{book_id}/entities/{entity_id}/enrichments` — upsert the supplement rows (quarantined on write-back, promoted on promote). Emits `glossary.entity_updated` for C4 sync.
  - `DELETE /internal/books/{book_id}/entities/{entity_id}/enrichments?proposal_id=` — soft-delete (set `deleted_at`) the supplement for a proposal (retract). Emits the sync event. **Internal-token — fixes F-C13-1 without depending on a user JWT.**
- `short_description` (original canon) is **never written by enrichment** (revert the 053 overwrite).

**knowledge-service (Python):**
- `enriched-writeback`/`enriched-promote` anchor on the RESOLVED canonical `glossary_entity_id` (no parallel node). `enriched-promote` canonizes the facts AND ensures the anchor `:Entity` is the canonical node (or leaves anchor to glossary_sync since keys now match). Retract soft-retracts facts (unchanged).

**lore-enrichment-service (Python):**
- `writeback`: resolve the existing canonical glossary entity by `glossary_entity_id` (from the gap/target) or exact canonical-name match; only create a NEW canonical entity when the entity genuinely doesn't exist — never a `target_ref`-named duplicate. Drop `_anchor_name`'s `target_ref`-as-name behavior (B3).
- `promote`: write the supplement via the new glossary enrichment endpoint (not `set_glossary_canon_content` on `short_description`).
- `retract`: call the internal `DELETE …/enrichments?proposal_id=` (internal-token) + soft-retract KG facts. No user JWT needed. (F-C13-1.)

**Read/wiki:** render original canon + a clearly-labeled "enrichment (`dị bản`)" section from `entity_enrichments` (distinguished, per B1).

## 5. Open questions (PO)
1. **Data-model: confirm (c)**, or pick (a)/(b)?
2. **Multiple variants per (entity,dimension)** — does `dị bản` mean we keep several alternative enrichments, or one-current per dimension? (c supports either; affects the unique key.)
3. **New-entity case:** when enrichment targets an entity with NO original canon yet, do we still keep it purely as an enrichment supplement (leave `short_description` empty/marked), per B1? (Recommend yes.)
4. **Read surface:** separate "enrichment" section in the wiki/entity read (recommend), or inline-marked?

## 6. Verify plan (must live-prove, given F-LIVE-1 history)
- Rebuild knowledge-service (F-LIVE-1) so enriched-* routes exist.
- Live e2e on a fresh promote: assert (1) NO duplicate entity — the enrichment attaches to the canonical `glossary_entity_id`; (2) original `short_description` untouched; (3) the supplement rows carry origin=enrichment + markers; (4) `enriched-promote` canonizes facts on the canonical node; (5) **retract** soft-deletes the supplement (internal-token, no user JWT) while the canonical entity + original canon survive (`glossary_recycled`-equivalent = true).
- Unit: writeback resolves-not-mints; promote doesn't touch `short_description`; retract removes only the supplement. API-level (TestClient) retract test (the gap F-C13-1's unit test missed).

## 7. Acceptance
- F-C13-2 closed: no parallel entity; enrichment on the canonical entity; original canon distinguishable.
- F-C13-1 closed: retract removes the enrichment supplement via the wired internal path; original canon survives; live-proven.
- H0 intact: enriched supplement quarantined until promote; markers permanent; retract reversible (soft-delete).
- Also resolves/clarifies DEFERRED-053 (no `short_description` overwrite).
