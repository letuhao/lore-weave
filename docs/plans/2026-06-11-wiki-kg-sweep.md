# Plan — D-WIKI-P2-KG-SWEEP (KG-neighbourhood drift sweep)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** L (cross-service, load-bearing)

## Goal
Flag AI wiki articles stale when the Neo4j 1-hop KG neighbourhood they were built
from has changed since generation (GAP A: KG edits emit no event → pull-tier only).
PO: fold into the existing `/wiki/staleness-sweep`; degrade gracefully when
knowledge-service is unreachable (skip KG half, keep recipe-drift).

## The parity guarantee (the central correctness risk)
The "current" hash MUST be computed by the **exact** generation path or every article
false-positives. Generation: `_gather_kg` (context.py) → fact texts →
`stable_hash(sorted(texts))` (fingerprint.py, stored as
`build_inputs.kg_neighborhood_hash`). The sweep reuses **the same two functions**
with the same `kg_limit=DEFAULT_KG_LIMIT (20)`. Glossary never hashes — it only
compares two strings.

**Neo4j-down false-positive guard:** `_gather_kg` returns `[]` AND sets
`degraded["kg"]="unavailable"` when Neo4j is down. The endpoint MUST skip (omit) such
entities, never return the empty-list hash — else a transient outage flags everything.

## Changes

### knowledge-service — `app/routers/internal_wiki.py`
`POST /internal/knowledge/books/{book_id}/wiki/kg-hashes`, body `{user_id, entity_ids}`
→ `{hashes: {entity_id: kg_hash}}`. Resolve the project (`projects_repo.list(user, book,
limit=1)`); no project → `{hashes: {}}` (degrade). Per entity: fresh `degraded={}`,
`facts = await _gather_kg(entity_id, user_id, project, kg_limit=DEFAULT_KG_LIMIT,
degraded)`; if `degraded.get("kg") == "unavailable"` → omit; else
`hashes[eid] = stable_hash(sorted(facts))`. Imports `_gather_kg`, `DEFAULT_KG_LIMIT`
from `app.wiki.context`, `stable_hash` from `app.wiki.fingerprint`.

### glossary-service — `internal/api/knowledge_client.go`
`fetchKgHashes(ctx, bookID, ownerID, entityIDs) (map[string]string, error)` — POST the
endpoint, parse `{hashes}`. Returns an error on unreachable/non-200 (caller degrades).

### glossary-service — `internal/api/wiki_staleness.go`
- `sweepKgDrift(ctx, bookID, ownerID) (int, error)`: select AI articles with a stored
  `build_inputs.kg_neighborhood_hash`; batch their entity_ids; `fetchKgHashes`; for each
  entity whose current hash is present AND ≠ stored → insert a `kg_drift` row
  (`severity='content'`, `source_ref={source_type:'kg', source_id:<stored>,
  current_hash:<current>}`) + flip `is_knowledge_stale`. Idempotent on
  `(article_id, reason_code, source_ref->>'source_id')`. On `fetchKgHashes` error → log,
  return `(0, nil)` (graceful skip, Q2).
- `sweepWikiStaleness`: add optional `user_id` to the request body; after recipe-drift,
  if `user_id` present, run `sweepKgDrift(... , ownerID)`; response
  `{flagged: <recipe>, kg_flagged: <kg>}`. Absent user_id → KG half skipped.

## reason_code
New `kg_drift` (severity `content`) — joins entity_changed/merged/chapter_regrounded/
citation_broken/recipe_drift. No migration (reason_code is free text; the feed CASE
sort already defaults non-hard/structural → content tier).

## Tests
- knowledge `tests/unit/test_wiki_kg_hashes.py`: hash == `stable_hash(sorted(facts))`
  (mock `_gather_kg`); **parity test** — same facts → same hash as a `build_inputs`
  computation; Neo4j-unavailable entity (degraded marker) is OMITTED (no empty-hash);
  no-project → empty map.
- glossary (DB + knowledge stub): `sweepKgDrift` flags on hash mismatch (kg_drift
  pending + flag set), no-op on match, idempotent re-run; knowledge-unreachable →
  `(0, nil)` and recipe-drift still returns. Client hop URL/body/propagation (no DB).

## VERIFY
Cross-service (knowledge + glossary) → live-smoke token or
`LIVE-SMOKE deferred to D-WIKI-P2-KG-SWEEP-LIVE-SMOKE`. The live-smoke that matters:
generate an article, run the sweep with NO KG change → **0 kg_drift** (parity proof);
then invalidate/add a relation → sweep flags exactly that article.

## Out of scope
A push event on KG change (GAP A stays pull-only); an FE "check for updates" button
wiring the sweep; severity escalation for removed-vs-added relations (all `content`).
