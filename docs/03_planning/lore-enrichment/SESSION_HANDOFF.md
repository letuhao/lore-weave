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
| DESIGN v2 (corrected boundary) | ✅ `175fc811` — but still architecture-level, needs component detail |
| PLAN / RAID decomposition | ⬜ NOT STARTED — next |

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

## Next phase — PLAN (what's left before RAID can run)
1. Detail the **KG-read port** (how enrichment queries knowledge-service: REST `/v1/knowledge/...` + Neo4j graph-stats for gap-detection).
2. Define the **`EnrichmentStrategy`** plug-in interface (4 techniques) + the cost-cap + **quality/eval gate** that promotes a technique.
3. Design the **proposal store** schema + review gate (mirror pending_facts).
4. Design the **cultural-fidelity eval harness** (needed before promoting fabrication/re-cook).
5. Freeze API contract `contracts/api/lore-enrichment/` (per monorepo convention).
6. RAID-decompose into cycles → write `.raid/active-task.yaml` + `docs/plans/<slug>/` (CYCLE_DECOMPOSITION, OPEN_QUESTIONS_LOCKED, PRE_FLIGHT_CHECKLIST, RAID_WORKFLOW copy).
7. Classify task size (expected **XL** — new service, schema, multi-service contracts).

## Reusable infra discovered (adopt, don't reinvent)
confidence/quarantine/pending_validation · pending_facts confirm-reject + injection-defense · extraction job state machine (estimate/start/pause/resume/cancel) · per-project embedding-model · Neo4j graph-stats (gap-detect input) · CJK-aware splitting (`loreweave_extraction`) · Redis Streams event pipeline · chat-service skeleton + `client/` provider-adapter (no direct SDK, no hardcoded model).
