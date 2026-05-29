# Lore-Enrichment — Locked Questions

> Locked during CLARIFY + REVIEW (2026-05-29/30). RAID cycles MUST honour these; reopening requires explicit user sign-off.

## From REVIEW (2026-05-29)
- **Q-R1 Service boundary** → **Separate service** `lore-enrichment-service` (Python/FastAPI, own DB).
- **Q-R2 Technique scope** → Implement **all 4** as pluggable strategies, but **roll out phased by effectiveness-per-cost**: P1 `template`+`retrieval` → P2 `fabrication` → P3 `recook`. Cost-cap + quality gate promote each.

## From bottom-up CLARIFY (2026-05-30, code-verified)
- **Q1 Review queue** → Own proposal store; **mirror** knowledge-service `pending_facts` (confirm/reject + injection-defense + confidence/quarantine). No competing queue.
- **Q2 Write-back path** → Author through **glossary SSOT** (`POST /books/{book_id}/extract-entities` + wiki); `glossary_sync` propagates to Neo4j. Enrichment does not write Neo4j canonical content directly.
- **Q3 Scoping** → **Per-user/per-project** (matches knowledge-service).
- **Q4 Generative overlap** → None. knowledge-service is **extractive**; its D4-03 wiki-from-KG only renders known facts. Enrichment generates NEW grounded canon and **feeds** that machinery — does not fork the plan.
- **Q5 Game-entity schema** → Enrichment owns its schema-governed entity/wiki shape; **kept isolated** from `world-service`/`game-server` (mmo-rpg). No coupling unless a real engine contract is needed.
- **Q6 Dependency/deploy** → Depends on knowledge-service + glossary + book-service up (via `infra/docker-compose.yml`). Thin **KG-read port** for graceful degradation.

## Defaults (overridable)
- Corpora: public-domain classical Chinese texts for the demo; modern/news sources need licensing review gated to P3.
- Admission: **always human-gate** initially; auto-admit thresholds calibrated later from eval data.
