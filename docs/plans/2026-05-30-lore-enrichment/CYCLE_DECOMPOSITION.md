# Lore-Enrichment — RAID Cycle Decomposition

> **Task:** `lore-enrichment` · **Slug:** `2026-05-30-lore-enrichment` · **Size:** XL
> **Source:** [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
> **Principle:** bottom-up, dependency-ordered, evidence-gated. Each cycle ships a verifiable slice. Cross-service cycles require a live-smoke token (CLAUDE.md VERIFY rule).

## Demo milestone
After **C11** the P1 path is end-to-end: ingest Fengshen source → gap-detect → template + cultural-retrieval enrichment → schema-governed proposals → review → write-back to glossary. That is the demo-able vertical slice. C12+ adds the quality gate and the higher-cost techniques.

## Cycles

| # | Cycle | Goal / key deliverables | Verify / live-smoke | Depends on |
|---|---|---|---|---|
| **C0** | Bootstrap | FastAPI skeleton mirroring chat-service: `config.py` (fail-fast on missing secrets), `/health`, DB pool, `deps.py`, Dockerfile, `infra/docker-compose.yml` wiring, gateway route `/v1/lore-enrichment/*`. | `curl /health` 200 on stack-up | — |
| **C1** | KG-read port | `app/clients/` for knowledge-service (graph, **graph-stats**, context, embedding-model), glossary read, book-service read. `KnowledgeReadPort` Protocol + Null/cached impl (graceful degrade). | live smoke: read graph-stats from a running knowledge-service | C0 |
| **C2** | Data model | Migrations for `enrichment_job`, `enrichment_proposal`, `source_corpus`, `enrichment_template`, `cultural_grounding_ref` in `loreweave_lore_enrichment`. | migration up/down clean; row round-trip test | C0 |
| **C3** | API contract freeze | `contracts/api/lore-enrichment/` OpenAPI; stub handlers for jobs/proposals/sources/templates. | spec lints; stub routes 200/501 | C0 |
| **C4** | Gap-detection | Engine over graph-stats + templates → typed `Gap` list (entity × dimension coverage). | unit: known KG fixture → expected gaps | C1, C2 |
| **C5** | Strategy core | `EnrichmentStrategy` interface + registry + feature-flags + per-job **cost guardrail** + job state machine (estimate/start/pause/resume/cancel). | unit: registry select + cost-cap pause | C2, C3 |
| **C6** | Strategy (a) template | P1 template scaffolding strategy (entity-kind dimension scaffolds). | unit: gap → scaffolded proposal | C4, C5 |
| **C7** | Strategy (b) retrieval | P1 external cultural retrieval: `source_corpus` ingest + embed via provider-adapter + RAG grounding; `cultural_grounding_ref` populated. | live smoke: embed + retrieve over a seeded corpus chunk | C5, C6 |
| **C8** | Schema-governed gen | Generation + normalization-repair (game-ready shape) + **provenance/confidence** tagging on every fact. | unit: malformed gen → repaired/valid; provenance present | C6, C7 |
| **C9** | Canon-verify | Adversarial consistency check vs KG/glossary (contradiction detection) + injection-defense at proposal creation. | unit: contradictory proposal flagged; injection neutralized | C8 |
| **C10** | Review gate + write-back | Proposal review API (list/approve/reject/edit, mirror pending_facts) + write-back to glossary `extract-entities` + wiki. | live smoke: approve → entity appears in glossary → glossary_sync to Neo4j | C9 |
| **C11** | Job orchestration | End-to-end job runner + Redis Streams events (`glossary.entity_updated`, `knowledge.*`) + cost-cap enforcement. **DEMO milestone.** | live smoke: full P1 job on Fengshen sample → reviewed → written back | C10 |
| **C12** | Eval harness + gate | Cultural-fidelity harness (schema/canon/anachronism/provenance scoring) + promotion quality gate. | eval run produces scorecard; gate blocks below threshold | C11 |
| **C13** | Strategy (c) fabrication | P2 canon-grounded fabrication, behind the gate. | eval: fabrication proposals clear threshold before active | C12 |
| **C14** | Strategy (d) re-cook | P3 real history/news re-cook, behind gate + licensing check. | eval clears; licensed sources only | C12, C13 |
| **C15** | Productionize | Observability (logging/tracing/metrics), runbook, deploy pipeline, final secret-scan + prod-isolation lint. | metrics scrape; secret-scan clean | C11 |

## Notes
- **Cost discipline (locked):** P1 (C6–C7) before P2/P3 (C13–C14); the gate (C12) must exist before promoting fabrication/re-cook.
- **Isolation:** no edits to `world-service`/`game-server` or other agents' files; enrichment owns its own schema + DB.
- DPS/parallelism per cycle decided at brief-generation time; cross-service cycles (C1, C7, C10, C11) carry live-smoke evidence.
- Cycle count = 16 (C0–C15); first_cycle=0, last_cycle=15, bootstrap_cycle=0.
