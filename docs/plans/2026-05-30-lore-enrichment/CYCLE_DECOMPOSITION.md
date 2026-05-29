# Lore-Enrichment — RAID Cycle Decomposition

> **Task:** `lore-enrichment` · **Slug:** `2026-05-30-lore-enrichment` · **Size:** XXL (XL + platform deferrals K14/D4-03)
> **Source:** [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
> **Principle:** bottom-up, dependency-ordered, evidence-gated. Each cycle ships a verifiable slice. Cross-service cycles require a live-smoke token (CLAUDE.md VERIFY rule).

## Demo milestone
**Scope = enrich ~3–5 under-described LOCATIONS** in 封神演义 (sage dwellings 玉虛宮/碧遊宮, 蓬萊山, cities/passes mentioned without detail) across dimensions 历史/地理/文化. After **C14** the P1 path is end-to-end for these places: ingest Fengshen source → detect location gaps → template + cultural-retrieval (山海经 / Shang–Zhou history) enrichment → schema-governed proposals (Chinese, enriched, quarantined) → review → **author promote** → write-back to glossary (+ K14 auto-sync to KG, D4-03 wiki body). C15+ adds the quality gate and higher-cost techniques (c/d).

## Cycles

| # | Cycle | Goal / key deliverables | Verify / live-smoke | Depends on |
|---|---|---|---|---|
| **C0** | Bootstrap | FastAPI skeleton mirroring chat-service: `config.py` (fail-fast on missing secrets), `/health`, DB pool, `deps.py`, Dockerfile, `infra/docker-compose.yml` wiring, gateway route `/v1/lore-enrichment/*`. | `curl /health` 200 on stack-up | — |
| **C1** | KG-read port + verifies | `app/clients/` for knowledge-service (graph, **graph-stats**, context, embedding-model), glossary read, book-service read; `KnowledgeReadPort` Protocol + Null/cached impl. **Verify: glossary entity scoping (H2), glossary→KG sync trigger (H1), injection-defense/CJK importability (M4).** | live smoke: read graph-stats from a running knowledge-service; scoping/importability findings recorded | C0 |
| **C2** | Data model + **H0** | Migrations for `enrichment_job`, `enrichment_proposal`, `source_corpus`, `enrichment_template`, `cultural_grounding_ref` in `loreweave_lore_enrichment`. **H0 columns:** `origin`, lifecycle `review_status` (proposed→author_reviewing→approved→promoted\|rejected), `promoted_entity_id/by/at`. | migration up/down clean; H0 lifecycle round-trip test | C0 |
| **C3** | API contract freeze | `contracts/api/lore-enrichment/` OpenAPI; stub handlers (jobs/proposals/sources/templates) incl. **author promote** endpoint. | spec lints; stub routes 200/501 | C0 |
| **C4** | **[PLATFORM] K14 event pipeline** | glossary emits `glossary.entity_updated` on entity write (incl. extract-entities); knowledge-service consumer triggers `glossary_sync`→Neo4j. **Resolves H1.** (glossary + knowledge-service) | live smoke: write glossary entity → event → entity appears in Neo4j automatically | C1 |
| **C5** | **[PLATFORM] D4-03 wiki-from-KG** | Generate rich wiki **content** (article body) from an entity's KG neighborhood, replacing empty `generateWikiStubs`. **Resolves H3.** Carries `source_type` distinction. | live smoke: entity → generated wiki body persisted | C1 |
| **C6** | Gap MODEL spec (M1a) | Define dimension set per entity-kind — **demo anchors on entity-kind = LOCATION**: dimensions 历史/地理/文化/features/inhabitants; gap = canon-mentioned place missing these; + ranking. Spec + fixtures (locked 4 places: 玉虛宮, 碧遊宮/金鰲島, 蓬萊, 陳塘關) before engine. | review: location dimension model + ranking on Fengshen fixtures | C1, C2 |
| **C7** | Gap-detection engine (M1b) | Engine over graph-stats + templates + gap-model → typed ranked `Gap` list. | unit: known KG fixture → expected ranked gaps | C6 |
| **C8** | Strategy core | `EnrichmentStrategy` interface + registry + feature-flags + per-job **cost guardrail** + job state machine (estimate/start/pause/resume/cancel). | unit: registry select + cost-cap pause | C2, C3 |
| **C9** | Strategy (a) template | P1 template scaffolding strategy (entity-kind dimension scaffolds). | unit: gap → scaffolded proposal | C7, C8 |
| **C10** | Strategy (b) retrieval | P1 cultural retrieval over OWNED corpora (山海经/Fengshen): `source_corpus` ingest + **reuse knowledge-service `/internal/embed` + per-project embedding** (no new RAG framework, no heavy deps) + similarity search; `cultural_grounding_ref` populated. Web-search OUT of scope (free-OSS later if needed). | live smoke: embed + retrieve over a seeded 山海经 chunk | C8, C9 |
| **C11** | Schema-gov gen + **H0 tag** | Generation + normalization-repair (game-ready) + **provenance/confidence + `origin='enriched'` tagging** on every fact. | unit: malformed→repaired; every fact carries origin/provenance | C9, C10 |
| **C12** | Canon-verify | **Contradiction + anachronism** check vs KG/glossary + injection-defense at proposal creation. (M2: verifies consistency, NOT correctness — correctness rests on human gate.) | unit: contradictory/anachronistic proposal flagged; injection neutralized | C11 |
| **C13** | Review gate + write-back (**H0**) | Proposal review API (list/`approve`/reject/edit + **author `promote`**, mirror pending_facts). Write-back enters KG as **`source_type='enriched'` + quarantine** (NOT canon); promotion → canon keeping permanent origin marker. **Retraction** path via glossary recycle-bin (M6). | live smoke: propose→enriched-in-KG (quarantined) → author promote → canon; retract works | C4, C5, C12 |
| **C14** | Job orchestration | End-to-end job runner + Redis Streams events + cost-cap (incl. **eval cost**, M5). **DEMO milestone** (P1 end-to-end on Fengshen). | live smoke: full P1 job → enriched proposals → review → promote → write-back | C13 |
| **C15** | Eval (EXTEND framework) + gate | **Extend the existing eval framework additively** — `scripts/enrichment_eval.py` + `eval/enrichment-eval-suite.toml` (weighted sub-scores: schema/canon/anachronism/provenance/usefulness + regression thresholds + baseline-diff) + versioned `eval/baselines/enrichment-vX.json` + in-service persist `enrichment_eval_runs` (mirror knowledge-service benchmark). Reuse the **judge-ensemble** methodology now on main (`tests/quality/`: multi-judge majority + Fleiss κ + partial-credit; gemma/qwen-30b/claude judges) for subjective cultural-fidelity. NEVER edit climate/geo eval files. | eval scorecard vs baseline; gate blocks below threshold; run persisted | C14 |
| **C16** | Strategy (c) fabrication | P2 canon-grounded fabrication, behind the gate. | eval: clears threshold before active | C15 |
| **C17** | Strategy (d) re-cook | P3 real history/news re-cook, behind gate + licensing check. | eval clears; licensed sources only | C15, C16 |
| **C18** | Productionize | Observability (logging/tracing/metrics), runbook, deploy pipeline, final secret-scan + prod-isolation lint. | metrics scrape; secret-scan clean | C14 |

## Notes
- **H0 invariant (locked):** enriched lore enters as `source_type='enriched'` + quarantine, NEVER canon by default; only author **promote** canonizes it, keeping a permanent origin marker. Enforced in C2 (schema), C11 (tagging), C13 (write-back + promotion). See [OPEN_QUESTIONS_LOCKED H0](OPEN_QUESTIONS_LOCKED.md).
- **Platform deferrals (Option B):** C4 (K14) + C5 (D4-03) pulled in to kill drift; conflict-checked safe (foundation touches 0 files in glossary/knowledge-service). They touch shared services — keep changes additive/backward-compatible.
- **Parallelism:** {C1,C2,C3} after C0; platform {C4,C5} parallel to enrichment-core {C6–C12}; both must land before C13. {C16,C17} after C15; C18 alongside C15+.
- **Cost discipline (locked):** P1 (C9–C10) before P2/P3 (C16–C17); the gate (C15) must exist before promoting fabrication/re-cook.
- **Isolation:** no edits to `world-service`/`game-server` or other agents' files; enrichment owns its own schema + DB; platform edits (C4/C5) are additive only.
- Cross-service cycles (C1, C4, C5, C10, C13, C14) carry live-smoke evidence.
- Cycle count = **19 (C0–C18)**; first_cycle=0, last_cycle=18, bootstrap_cycle=0.
