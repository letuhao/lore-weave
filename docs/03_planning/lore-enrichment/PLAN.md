# Lore-Enrichment Service — PLAN

> **Status:** PLAN · **Date:** 2026-05-30 · **Branch:** `lore-enrichment/foundation` · **HEAD:** 0cfef567
> **Builds on:** [CLARIFY_GROUND_TRUTH.md](CLARIFY_GROUND_TRUTH.md) (locked boundary) + [SERVICE_DESIGN.md](SERVICE_DESIGN.md) v2.
> **Task size:** **XL** (new service + schema + multi-service contracts + LLM/RAG). Per CLAUDE.md → spec + plan + RAID decomposition; sub-agents recommended.

This doc details the components the design left abstract, enough to decompose into RAID cycles. Cycle breakdown lives in [../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md).

---

## P1. KG-read port (consume knowledge-service / glossary / book-service)

A thin, typed adapter (`app/clients/`) so the enrichment core never talks to upstream services directly and degrades gracefully if KG is down.

| Upstream | What enrichment reads | Endpoint(s) |
|---|---|---|
| knowledge-service | entities, graph, **graph-stats** (gap-detect input), context | `GET /v1/knowledge/projects/{pid}/extraction/graph`, `.../graph-stats`, `/internal/context/*` |
| knowledge-service | per-project embedding-model + **`/internal/embed`** (reuse for technique-b RAG; no new RAG framework) | `GET /v1/knowledge/projects/{pid}/embedding-model`, `POST /internal/embed` |
| glossary-service | canonical entities + kinds + attributes (the SSOT to enrich) | glossary read APIs (entity/kinds/attribute handlers) |
| book-service | source chapter/scene text | `GET /internal/books/{book_id}/chapters/{chapter_id}/hierarchy` |

- **Port interface** `KnowledgeReadPort` (Protocol): `get_graph_stats(project_id)`, `get_entities(project_id, filter)`, `get_context(project_id, query)`, `get_embedding_model(project_id)`. Real impl = HTTP client; a Null/cached impl lets enrichment run read-degraded.
- Auth: `INTERNAL_SERVICE_TOKEN` for `/internal/*`; JWT passthrough for user-scoped reads. Per-project scoping throughout.

## P2. `EnrichmentStrategy` interface + quality/cost gate

```python
class EnrichmentStrategy(Protocol):
    key: str                        # "template" | "retrieval" | "fabrication" | "recook"
    cost_tier: CostTier             # LOW | MED | HIGH
    def applicable(self, gap: Gap) -> bool: ...
    async def propose(self, gap: Gap, ctx: GroundingContext) -> list[Proposal]: ...
```

- **Registry** picks strategies per gap by policy; **feature-flags** enable/disable each (rollout P1→P2→P3).
- **Cost guardrail**: per-job token cap (reuse knowledge-service cost-tracking pattern); job pauses on cap (mirror extraction state machine).
- **Quality gate** (promotion): a strategy is promoted from shadow→active only when its proposals clear the eval harness (P4) threshold. Tracks accept-rate + fidelity score per strategy.
- Rollout order (locked): P1 `template`+`retrieval` (LOW/MED) → P2 `fabrication` (HIGH, gated) → P3 `recook` (HIGH, gated + licensing).

## P3. Proposal store + review gate (mirror `pending_facts`)

Own store (different domain than chat-fact `pending_facts`), same proven pattern.

Tables (Postgres `loreweave_lore_enrichment`):
- `enrichment_job(id, user_id, project_id, book_id, scope_json, technique_policy_json, status, cost_spent, created_at)` — status state machine: `estimated|running|paused|cancelled|done`.
- `enrichment_proposal(id, job_id, user_id, project_id, target_glossary_entity_id NULLABLE, dimension, payload_json, origin DEFAULT 'enriched', technique, provenance_json, confidence, source_refs_json, review_status, promoted_entity_id NULLABLE, promoted_by NULLABLE, promoted_at NULLABLE, created_at)` — `review_status: proposed|author_reviewing|approved|promoted|rejected` (**H0 lifecycle**). On KG write: `source_type='enriched'` + `pending_validation=true` + `confidence<1.0` (quarantined, distinct from `source_type='glossary'` canon); promotion flips to canon but keeps the permanent origin marker.
- `source_corpus(id, project_id, kind, uri, license, provenance, created_at)` — registered canon + external cultural sources.
- `enrichment_template(id, entity_kind, dimension, scaffold_json)` — per entity-kind dimension scaffolds.
- `cultural_grounding_ref(id, proposal_id, corpus_id, chunk_ref, embedding_ref, score)` — what grounded each proposal.

Review gate API mirrors pending_facts: list pending by dimension/confidence/technique → `approve|reject|edit`. **Injection-defense** applied at proposal-creation time (reuse knowledge-service defense), so approve writes through as-is. Default: **always human-gate** (auto-admit thresholds calibrated later from eval data).

## P4. Cultural-fidelity eval harness (the promotion gate)

Needed before promoting P2/P3 techniques. Measures more than JSON validity:
- **Schema validity** (game-ready shape conforms — G-KMS normalization-repair pass).
- **Canon consistency** — adversarial LLM check vs the KG/glossary canon (contradiction detection).
- **Cultural faithfulness / anachronism guard** — check generated detail against grounding sources (Shan Hai Jing, Shang–Zhou history); flag culturally-anachronistic claims.
- **Provenance completeness** — every fact tagged technique + source + confidence.
- Output: per-proposal scorecard + per-strategy aggregate that the quality gate (P2) consumes.
- **EXTENDS the existing eval framework (not a standalone harness):** mirror the platform pattern — `scripts/enrichment_eval.py` + `eval/enrichment-eval-suite.toml` (weighted sub-scores + regression thresholds + baseline-diff, like `eval/climate-eval-suite.toml`) + versioned `eval/baselines/enrichment-vX.json`, plus an in-service benchmark module persisting `enrichment_eval_runs` (mirror knowledge-service `app/benchmark/persist.py`). Reuse the multilingual LM-Studio quality-gate pattern (proven on Chinese). **Additive only** — never edit the climate/geo eval files (isolation). Versioned baselines give the longitudinal improvement space.

## P5. API surface (freeze in early cycle → `contracts/api/lore-enrichment/`)

- `POST /v1/lore-enrichment/jobs` · `GET /v1/lore-enrichment/jobs/{id}` · job control `pause|resume|cancel`.
- `GET /v1/lore-enrichment/jobs/{id}/proposals` (filter) · `POST /v1/lore-enrichment/proposals/{id}/{approve|reject|edit}`.
- `POST /v1/lore-enrichment/sources` · `GET /v1/lore-enrichment/templates`.
- Internal: `POST /internal/lore-enrichment/gap-detect`; subscribe `glossary.entity_updated` / `knowledge.*` events.
- Gateway route `/v1/lore-enrichment/*` via api-gateway-bff; internal port (next free, e.g. 8093 / host 8217 — confirm in PRE_FLIGHT).

## P6 + P7. RAID decomposition & size
- Decomposition → [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md). Locked questions → [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md). Pre-flight → [PRE_FLIGHT_CHECKLIST.md](../../plans/2026-05-30-lore-enrichment/PRE_FLIGHT_CHECKLIST.md).
- Size **XXL** (raised from XL by the platform deferrals below); RAID-suitable (mostly-autonomous, well-bounded cycles, evidence-gated).

## P8. Platform deferrals pulled in (Option B — kills long-standing drift)

Conflict-checked safe (foundation branch touches 0 files in these services). Both are prerequisites for a clean enrichment write-back, so they land before the write-back cycle.

- **K14 event pipeline** (glossary + knowledge-service) — glossary emits `glossary.entity_updated` on entity write (incl. `extract-entities`); knowledge-service event consumer triggers `glossary_sync` → Neo4j. **Resolves H1** (glossary→KG propagation becomes automatic, platform-wide) — replaces the manual worker-ai `scope='glossary_sync'` trigger.
- **D4-03 wiki-from-KG** (knowledge-service / glossary) — generate rich wiki **content** (article body) from an entity's KG neighborhood, replacing the empty-body `generateWikiStubs`. **Resolves H3** — gives enriched lore a real renderer. Enriched-origin wiki carries the `source_type='enriched'` distinction (H0) until promotion.
