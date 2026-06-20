# Data-Architecture / SSOT Consistency — Findings

- **Date:** 2026-06-20 · **Status:** ✅ COMPLETE · **Type:** read-only audit (no code changed)
- **Source:** gap-analysis §11 Task 7.

## Headline
The **distributed-systems core is the strongest part of the platform** — per-reality routing (I5), no-cross-reality-query (I7), `MetaWrite` discipline (I8), lifecycle CAS (I9), and event-sourced projection rebuild are all **EXISTS-SAFE** in code. The risk is concentrated in the **glossary↔knowledge dual-SSOT sync**, which has verified silent-divergence holes.

## Prioritized risk list
| # | Risk | Severity | Status |
|---|---|---|---|
| 1 | Glossary entity **soft-delete emits NO event** → knowledge keeps a `confidence=1.0` Neo4j anchor to a deleted row | **HIGH** | RISK/GAP |
| 2 | Glossary **rename leaves Neo4j `e.id` (name-hash) stale** → primary-key lookups miss the renamed entity | **HIGH** | RISK |
| 3 | **No reconciliation sweep** for dangling `glossary_entity_id` / orphaned anchors | **MED-HIGH** | GAP |
| 4 | `provider-registry` usage-relay `XAdd` outside outbox tx (mark-after-XAdd) | LOW | acknowledged at-least-once |
| 5 | `incident-bot` breach emitter direct `XAdd`, no outbox table at all | LOW-MED | RISK/GAP |
| 6 | Canon-projection drift sampler doesn't yet cover `canon_projection` | LOW | tracked (L5.K) |

## Detail on the HIGH items
- **#1 (verified):** `glossary-service/internal/api/entity_handler.go:1226-1239` soft-deletes with a bare `UPDATE ... SET deleted_at` and returns 204 — **no outbox write**. `outbox.go` defines no `entity_deleted` event; knowledge `app/events/handlers.py` only handles `entity_updated`/`entity_merged`. The Neo4j `:Entity` keeps `glossary_entity_id` + `confidence=1.0` + `source_type='glossary'` pointing at a dead row. `archive_entity()` exists but is never triggered.
- **#2 (verified):** `knowledge-service/app/extraction/glossary_sync.py:86-94` `ON MATCH SET` updates name/aliases/kind but **not `e.id`** (= hash of name, line 63). 15+ Cypher queries key on `e.id` → they miss a renamed entity. (The MERGE key `glossary_entity_id` is stable; the derived `e.id` is the hazard.)
- **#3:** existing repair jobs fix counts + orphan `:ExtractionSource`, but nothing detects Neo4j anchors whose `glossary_entity_id` points at a deleted/nonexistent glossary row, nor recomputes stale `e.id`. Cross-DB, no FK → silent divergence with no alarm.

## What's solid (capture as reference)
- **I5 routing tamper-safe:** reality→DB resolved from the registry (`crates/meta-rs/src/routing.rs`); callers never supply `db_name`/`db_host`; schema CHECK on `db_host` pattern. 
- **I7:** no live cross-reality join found; cross-reality only via `xreality.*` consumed by meta-worker.
- **I8/I9:** `contracts/meta/metawrite.go` writes data+audit+outbox in one tx; audit table `REVOKE UPDATE,DELETE` (append-only); lifecycle CAS on status column via `AttemptStateTransition`.
- **Outbox (I13) core emitters are transactional**; consumers idempotent (`ON CONFLICT (source_service, source_outbox_id) DO NOTHING`); publisher drains `FOR UPDATE SKIP LOCKED`, marks-published in the same tx.
- **Canon immutability:** the only writer into per-reality `canon_projection` is meta-worker (`canon_writer`), event-driven, never gameplay; world-service/game-server are read-only on canon. (Canonization write-back S13 is spec-locked but not yet wired — track.)
- **Projection rebuild path exists** (`crates/rebuilder` + golden/reference oracles); rows carry `source_event_id`/`aggregate_version` so out-of-band writes are detectable.

## Suggested follow-ups (not done)
Emit `glossary.entity_deleted` from the delete handler → knowledge `archive_entity()` (#1); add `e.id` to the rename `ON MATCH SET` or stop keying on the name-hash (#2); nightly cross-DB integrity sweep (#3); DEFERRED rows for incident-bot non-outbox XAdd (#5) and the canon-projection drift gap (#6).
