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

## H0 — CORE INVARIANT: enriched lore ≠ original canon (locked 2026-05-30)
Enriched ("makeup") lore MUST be structurally distinguishable from authored canon at all times, and only the **author's explicit promotion** turns it into canon.
- Enriched content NEVER enters the system as canon by default. It lives in the enrichment proposal store and, when written to the KG, carries **`source_type='enriched'` (or `enriched:<technique>`), `pending_validation=true`, `confidence<1.0`** — quarantined and visibly distinct from `source_type='glossary'` (authored canon, confidence=1.0). Aligns with the existing knowledge-service quarantine model.
- Lifecycle: `proposed → author_reviewing → approved → promoted` | `rejected`. Only **promoted** content becomes canon (`source_type='glossary'`, confidence=1.0).
- **Permanent origin marker (locked default):** after promotion, the entity/fact **retains** `origin='enrichment'` + `promoted_from_proposal_id` + `promoted_by` + `promoted_at` + `original_technique` — lifetime traceability of "this canon was originally makeup", not only in change-history/audit.
- Per-reality/project: `source_type` + scope travel with the data so each reality keeps its enriched layer distinct.
- Proposal columns: `origin`, `technique`, `provenance_json`, `confidence`, `source_refs_json`, `cultural_grounding_ref`, `review_status`.

## Scope decision (locked 2026-05-30) — pull in drifting platform deferrals (Option B)
Conflict-checked: foundation branch (54 commits ahead) touches **0** files in knowledge-service/glossary → safe to modify here.
- **K14 event pipeline** — glossary emits `glossary.entity_updated`; knowledge-service consumer triggers `glossary_sync` → Neo4j (fixes H1: automatic glossary→KG propagation, platform-wide).
- **D4-03 wiki-from-KG** — rich wiki **content** generation from the KG/entity (fixes H3: a real renderer for enriched lore; replaces empty `generateWikiStubs`).
- Both become cycles in this effort (task size → **XXL**). Rationale: kill long-standing drift while we are in these services.

## Defaults (overridable)
- Corpora: public-domain classical Chinese texts for the demo; modern/news sources need licensing review gated to P3.
- Admission: **always human-gate** initially; auto-admit thresholds calibrated later from eval data.
