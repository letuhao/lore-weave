# Lore-Enrichment Track — Session Handoff

> **Last updated:** 2026-05-30 · **Branch:** `lore-enrichment/foundation` (off `origin/main`) · **HEAD:** 175fc811
> Isolated from `mmo-rpg/foundation-mega-task` (another agent, another folder — do not touch).

## What this track is
A new `lore-enrichment-service` that GENERATES the missing "off-page" canon a novel leaves implicit, so a book can become a game world. First demo corpus: **封神演义 (Fengshen Yanyi)** — culturally-dense, under-described (assumes reader knows Chinese history + 山海经). Four techniques: template scaffolding, external cultural retrieval, canon-grounded fabrication, real history/news re-cook.

## Phase status (bottom-up: CLARIFY → DESIGN → PLAN before RAID)
| Phase | Status |
|---|---|
| RAID tooling bootstrap | ✅ `71e6a93b` |
| Market research (3 deep-research passes) | ✅ `905df5ba`, `ff2aa392` — white space confirmed |
| REVIEW round-1 decisions | ✅ `76974490` |
| Bottom-up CLARIFY (code-verified, 6 Qs locked) | ✅ `0106dc1a`, `d90a1e14` |
| DESIGN v2 (corrected boundary) | ✅ `175fc811` |
| PLAN (component designs P1–P7) | ✅ [PLAN.md](PLAN.md) |
| RAID decomposition + artifacts | ✅ `docs/plans/2026-05-30-lore-enrichment/` + `.raid/active-task.yaml` — **`task_config.py validate` → exit 0 (12 keys)** |
| RAID READY TO RUN | ✅ — next action is `/raid` (after PRE_FLIGHT manual sign-off) |

## Key docs (read in this order)
1. [CLARIFY_GROUND_TRUTH.md](CLARIFY_GROUND_TRUTH.md) — code-verified boundary + 6 locked answers. **Most important.**
2. [SERVICE_DESIGN.md](SERVICE_DESIGN.md) — DESIGN v2 (8-step pipeline, 4 techniques phased by cost, principles).
3. [RESEARCH_LANDSCAPE.md](RESEARCH_LANDSCAPE.md) — 3-pass competitive/academic scan; white space + prior art (Graphify Novel, arXiv:2505.24803).

## Locked decisions (do not relitigate without cause)
- Separate Python/FastAPI service; **consumes** knowledge-service KG (real, not planned) — does NOT re-extract.
- Write-back canonical results via glossary `extract-entities` + wiki → `glossary_sync` propagates to Neo4j (single authoritative path).
- Scoping = **per-user/project** (matches knowledge-service).
- All 4 techniques implemented as pluggable strategies; **rollout phased by effectiveness-per-cost** (P1 template+retrieval → P2 fabrication → P3 news-recook) behind cost-cap + quality gate.
- Own proposal store; **mirror** `pending_facts` confirm/reject + injection-defense + confidence/quarantine.
- Keep game-entity schema **isolated** from world-service/game-server (mmo-rpg).

## Next action — RUN RAID (CLARIFY+DESIGN+PLAN+REVIEW done)
PLAN component designs + the adversarial [DESIGN_PLAN_REVIEW](DESIGN_PLAN_REVIEW.md) (findings resolved). RAID decomposed into **19 cycles C0–C18** ([CYCLE_DECOMPOSITION](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)); `.raid/active-task.yaml` validates (cycle_count=19). Size **XXL**.

**Two scope/design decisions baked in this session:**
- **H0 core invariant:** enriched lore ≠ canon — enters as `source_type='enriched'`+quarantine, author-promote-only, permanent origin marker (C2/C11/C13).
- **Option B:** pulled in long-drifting platform deferrals as cycles — **K14 event pipeline** (C4, fixes H1 sync) + **D4-03 wiki-from-KG** (C5, fixes H3 renderer). Conflict-checked safe.

Before `/raid`:
1. Work the [PRE_FLIGHT_CHECKLIST](../../plans/2026-05-30-lore-enrichment/PRE_FLIGHT_CHECKLIST.md) (port 8093/8221, DB, dependency stack-up, secrets, Fengshen test project seeded, pre-commit-hook decision).
2. Invoke `/raid` (or `/raid 0` to start at bootstrap C0). RAID reads `.raid/active-task.yaml`.
3. Demo milestone = after **C14** (P1 end-to-end: Fengshen → gap-detect → template+retrieval → review → author-promote → write-back + K14 auto-sync + D4-03 wiki).

## Reusable infra discovered (adopt, don't reinvent)
confidence/quarantine/pending_validation · pending_facts confirm-reject + injection-defense · extraction job state machine (estimate/start/pause/resume/cancel) · per-project embedding-model · Neo4j graph-stats (gap-detect input) · CJK-aware splitting (`loreweave_extraction`) · Redis Streams event pipeline · chat-service skeleton + `client/` provider-adapter (no direct SDK, no hardcoded model).

## Current Active Work — DEFERRED-053 fix (promote → glossary SSOT content-sync, Q2) [2026-05-30, cold-start]
**Closed 053 the Q2 way (glossary-first, NOT KG-authoritative).** Root cause: promote step 5 called `write_entity_through_glossary` → `extract-entities`, which can't write `short_description` (it is a `glossary_entities` COLUMN, not an EAV `attribute_definition`), so the canonical content stayed NULL while the enriched content lived only in Neo4j facts.

Fix (files touched, all additive):
- `services/glossary-service/internal/api/canon_content_handler.go` (NEW) + route in `server.go`: `POST /internal/books/{book_id}/entities/{entity_id}/canon-content` — service-token-gated; sets `short_description` (≤500 runes, trims, sticky `short_description_auto=false`), book-scoped 404 guard, emits `glossary.entity_updated` → `glossary_sync` → Neo4j (Q2 path). `canon_content_test.go` (NEW): 5 unit + 2 DB-integration tests.
- `services/lore-enrichment-service/app/clients/writeback.py`: NEW `set_glossary_canon_content()` port (injection-neutralized, rune-capped); corrected `write_entity_through_glossary` docstring (anchor = identity-only).
- `services/lore-enrichment-service/app/services/writeback.py`: promote step 5 now calls `set_glossary_canon_content(entity_id, content)` instead of the no-op extract-entities; pre-promote write-back unchanged (identity-only / quarantine).
- `tests/test_review_gate.py`: `FakePorts.set_glossary_canon_content` recorder + assertions (content reaches canon ONLY on promote; never pre-promote/idempotent).

H0 preserved (all 6, re-tested): quarantine pre-promote · `_anchor_name` never makeup · minted-anchor born marked · permanent origin marker · author-only · quarantine distinguishable. `knowledge-service/internal_enrichment.py` UNCHANGED (KG facts path intact; complementary to the glossary `short_description` summary, both end `source_type='glossary'`).

Tests: glossary `go test ./...` green; lore-enrichment 330 pass + 22 skip; ruff clean. **LIVE cross-service smoke:** fresh location entity `short_description` NULL pre → POST canon-content → POPULATED + `auto=false` + `glossary.entity_updated`(op=updated,src=glossary) outbox → Neo4j `Entity.short_description` set, `source_type='glossary'`, conf=1.0. Test entity cleaned up after.

053 moved to DEFERRED "Recently cleared".
