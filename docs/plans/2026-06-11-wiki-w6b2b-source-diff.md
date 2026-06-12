# Spec + Plan — W6b-2b (change-feed source diff: endpoint + FE)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** XL (knowledge Py + glossary Go + frontend) · **Workflow:** `/loom` v2.2

## Context
W6b-2a captures the source text used at generation (`wiki_article_source_usage.source_text`, the diff **before**). W6b-2b exposes the red/green diff. **PO (CLARIFY): all types incl. `block` (flagged approximate).**

**Why an "after" re-gather (not a glossary re-read):** the before was produced by knowledge's `gather_entity_context` → text extraction. The after MUST use the *same* code path or format drift creates spurious diffs. **Block is approximate** — its "before" was a retrieval result (top-k passages); re-retrieval can return different passages.

## Plan
### Knowledge
1. `app/wiki/writeback.py` — extract `source_texts(context) → dict[str,str]` keyed `f"{type}:{id}"` (entity=brief, kg=KG items, block=passages, capped); `build_source_usage` reuses it (parity).
2. `app/routers/internal_wiki.py` — `POST /internal/knowledge/books/{id}/wiki/source-text` `{user_id, entity_id, sources:[{source_type,source_id}]}` → resolve project (projects_repo) → `gather_entity_context` (client factories) → `source_texts` → return `{texts:{key:text}}`; not-indexed/None → `{texts:{}}`.

### Glossary
3. `internal/api/knowledge_client.go` — `fetchWikiSourceText(ctx, bookID, userID, entityID, sources) (map[string]string, error)`.
4. `internal/api/wiki_staleness.go` — `GET /v1/glossary/books/{id}/wiki/staleness/{staleness_id}/diff` (owner-gated): load the row (`wiki_staleness` JOIN `wiki_articles` on book) → `source_ref`{type,id} + article `entity_id`; before = `wiki_article_source_usage.source_text`; NULL → `{available:false}`; after = `fetchWikiSourceText` → `{available, source_type, before, after, approximate}`.
5. `internal/api/server.go` — register the route.

### Frontend
6. `features/wiki/api.ts` — `getStalenessDiff(bookId, stalenessId, token) → {available, source_type?, before?, after?, approximate?}`.
7. `features/wiki/components/KnowledgeUpdatesPanel.tsx` — a per-row "View diff" button → fetch → inline red/green (reuse `wikiDiff.diffLines` on `before/after.split('\n')`); `approximate` note for block; `available:false` → "no snapshot" hint (older article).
8. i18n ×4 — `staleness.viewDiff`, `diffApproximate`, `noDiff`, `diffBefore`/`diffAfter`.

## Acceptance
A freshly-generated article whose entity/KG/chapter source changed → "View diff" shows red/green before→after; block is labeled approximate; a pre-W6b-2 article → "no snapshot" + the W6b-1 jump.

## Tests
- knowledge: `source_texts` parity unit + the endpoint (re-gather mocked → texts).
- glossary: diff route (DB row + mocked knowledge `fetchWikiSourceText`; NULL before → available:false; owner gate).
- FE: panel "View diff" fetch + render; `diffLines` already unit-tested (W1).

## Cross-service ⇒ live-smoke token (or `D-WIKI-W6B2B-LIVE-SMOKE`).
## Risk: re-gather cost is on-demand (per click) — acceptable; block diff approximate (retrieval drift) — labeled.
