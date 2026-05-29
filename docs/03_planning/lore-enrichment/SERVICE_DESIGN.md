# Lore-Enrichment Service — Architecture Design (DRAFT)

> **Status:** DRAFT (DESIGN phase) · **Date:** 2026-05-29 · **Branch:** `lore-enrichment/foundation`
> **Grounded in:** [RESEARCH_LANDSCAPE.md](RESEARCH_LANDSCAPE.md) (passes 1, 2 & 3 complete — white space confirmed from research + product sides).
> **Demo target:** 封神演义 (Fengshen Yanyi) worldbuilding for a game.

---

## 1. Problem & thesis

A novel cannot be turned into a game world directly: authors describe "off-page" detail (geography, economy, factions, daily life, minor characters) sparsely, and culturally-dense classics like *Fengshen Yanyi* assume reader knowledge of Chinese history (Shang–Zhou) and myth (山海经 *Shan Hai Jing*, the Taoist pantheon). The world must be **enriched** — expanded with culturally-grounded, canon-faithful detail.

**Research thesis (validated both academically and on the product side):** no existing system fuses (1) an **authored-glossary SSOT**, (2) a **fuzzy/semantic knowledge-graph layer**, (3) **schema-governed, canon-anchored** enrichment, and (4) **cultural grounding** for an under-described classical source. Competitors maintain canon by **keyword injection** (vendor-acknowledged drift/hallucination when context overflows); embeddings are rare and mis-placed. This service targets exactly that gap.

## 2. Position in the platform

- **Language:** Python / FastAPI (per language rule — AI/LLM service). 
- **Two-layer anchoring** (already in `CLAUDE.md`):
  - `glossary-service` (Go) = **authored SSOT**. Canonical entities written back via its existing `/internal/books/{book_id}/extract-entities` bulk API; wiki stubs via `/v1/glossary/books/{book_id}/wiki/generate`.
  - `knowledge-service` (Python, planned) = **fuzzy/semantic entity layer** (Postgres SSOT + Neo4j derived). Enrichment entities anchor via `glossary_entity_id` FK.
- **Provider gateway invariant:** all LLM/embedding calls go through the adapter layer — NO direct provider SDK calls. **No hardcoded model names** (resolved from provider-registry).
- **Gateway invariant:** external traffic via `api-gateway-bff`.
- **Own Postgres DB** (per-service ownership). Jobs via Redis Streams; source/artifact blobs in MinIO.

## 3. Enrichment pipeline (the composition)

The differentiator is composing the four techniques into one governed pipeline. Mirrors the strongest research pattern: **seed-KG → expand → external-refine** (arXiv:2509.03540) + GraphRAG corpus synthesis + schema-governed admission (G-KMS).

```
[1] INGEST & SEED        source canon (book text + glossary entries)
                          → extract seed entity-KG (GraphRAG-style), anchor to glossary_entity_id
        │
[2] GAP DETECTION        per entity × dimension (geography/economy/factions/daily-life/...)
                          → template coverage check → list of under-described gaps
        │
[3] ENRICHMENT PLAN      per gap pick technique(s):
                          (a) template scaffolding   (b) external cultural retrieval
                          (c) canon-grounded fabricate (d) real history/myth re-cook
        │
[4] RETRIEVE & GROUND    internal canon via knowledge-service KG (semantic, NOT keyword)
                          + external cultural corpora (Shan Hai Jing, Shang–Zhou history) via RAG
        │
[5] SCHEMA-GOVERNED GEN  generate enrichment as schema-validated entities
                          (G-KMS: schema-governed gen → normalization repair → engine-aligned)
        │
[6] CANON VERIFY         adversarial consistency check vs canon + cultural-anachronism check
                          → confidence score + provenance tag
        │
[7] HUMAN REVIEW GATE    proposals reviewed/approved (provenance + confidence surfaced)
        │
[8] WRITE-BACK           canonical → glossary bulk-extract API; wiki stubs → wiki generate API;
                          semantic entities → knowledge-service
```

## 4. Design principles (lessons from the landscape)

1. **Semantic KG retrieval, not keyword injection.** Competitors' core weakness; we retrieve over the knowledge-service KG + embeddings, avoiding the documented context-overflow drift.
2. **Schema-governed output, not free text.** Every enrichment is a validated entity (game-engine-ready), per G-KMS / dependency-JSON-pipeline; normalization-repair before admission.
3. **Provenance + confidence on every fact.** Tag each enriched fact by technique (template / retrieved / fabricated / re-cooked) and ground-source + confidence. Canon trust depends on this — and no competitor does it.
4. **Cultural grounding as a first-class step** (CHisAgent Enricher pattern): external structured cultural/historical resources integrated for faithfulness; explicit anachronism guard.
5. **Iterative seed → expand → refine**, not one-shot generation.
6. **Human-in-the-loop admission gate** — enrichment proposes; human/PO approves before it becomes canon (mirrors LoreWeave's authored-SSOT philosophy).

## 4b. Prior art to study (closest analogues — neither fills the white space)

- **Graphify Novel** (`github.com/Anshler/graphify-novel`) — only shipping OSS with a genuine two-layer pattern (bible SSOT + derived NetworkX KG). Its **edge-provenance labels `EXTRACTED / INFERRED / AMBIGUOUS`** validate our per-fact provenance principle (§4.3) — adopt a similar scheme. Reference for KG engine ops (community/path/hub detection). Gaps vs us: single-user, no cultural grounding, bible auto-scaffold+curate (not a separate authored-SSOT service), no benchmarks.
- **arXiv:2505.24803** (IJHCI 2025) — pipeline blueprint for seed → init-KG → iterative scene-by-scene expansion with a **human-editable KG layer** fed back into generation. Mechanism is KG-grounded (NOT RAG+KG — that variant was refuted). Research prototype only.
- **Our durable differentiators** (no verified system combines all): cultural grounding (CHisAgent-style external-resource integration) + anchoring to a *separate authored glossary-SSOT service* + schema-governed game-ready output + per-fact provenance/confidence.

## 5. Data model (first cut)

- `enrichment_job` — per (book/reality, scope), status, technique policy.
- `enrichment_proposal` — generated entity/fact, target `glossary_entity_id`, dimension, **provenance** (technique, source refs), **confidence**, review status.
- `source_corpus` — registered canon + external cultural sources (Shan Hai Jing, history), with licensing/provenance.
- `enrichment_template` — per entity-type dimension scaffolds (city, faction, cultivation-sect, deity, ...).
- `cultural_grounding_ref` — external resource chunks + embeddings used to ground a proposal.

## 6. API surface (sketch — contract-first, freeze before FE)

- `POST /v1/enrichment/jobs` — start enrichment for a book/reality + scope + technique policy.
- `GET  /v1/enrichment/jobs/{id}` — status + progress.
- `GET  /v1/enrichment/jobs/{id}/proposals` — review queue (filter by dimension/confidence/technique).
- `POST /v1/enrichment/proposals/{id}/approve|reject|edit` — human gate → triggers write-back.
- `POST /v1/enrichment/sources` — register source corpus / cultural reference.
- `GET  /v1/enrichment/templates` — list/scaffold templates.
- Internal: `POST /internal/enrichment/seed-kg` (extract seed graph), consumers for knowledge-service events.

## 7. Design decisions & open questions

### Resolved at REVIEW (2026-05-29)

1. **✅ Separate service** — `lore-enrichment-service` (Python/FastAPI, own DB, independent lifecycle). It depends on knowledge-service's KG via API/events. **Sequencing risk:** knowledge-service is still "planned" — so the enrichment service must define a thin KG-layer **interface/port** it depends on, and either (i) stub it initially, or (ii) own a minimal KG slice until knowledge-service ships. Resolve the exact split in PLAN.
2. **✅ Implement all 4 techniques, phased by effectiveness-per-cost** — all four are first-class **pluggable strategies** behind one `EnrichmentStrategy` interface, toggled via feature-flags, with **cost tracking + a quality-eval gate** before enabling the next. Rollout order (cheapest/most-grounded → most expensive/risky):

   | Phase | Technique | Why this order | Cost / risk |
   |---|---|---|---|
   | P1 | **(a) template scaffolding** | deterministic-ish, cheapest, immediate coverage of gaps | low |
   | P1 | **(b) external cultural retrieval** | grounded (Shan Hai Jing, Shang–Zhou history), low hallucination | low-med |
   | P2 | **(c) canon-grounded fabrication** | fills gaps retrieval can't; needs canon-verify + confidence gating | med-high |
   | P3 | **(d) real history/news re-cook** | most external sourcing + tone-matching; defer until P1/P2 proven | high |

   Architecture supports all four from day one; **only the rollout/enablement is phased** to control LLM cost. A per-job cost cap + the quality gate decide when to promote a technique.

### Remaining open (defaults applied unless overridden)

3. **External cultural corpora licensing** — default: public-domain classical Chinese texts (Shan Hai Jing, Fengshen Yanyi source, dynastic histories) for the demo. Modern translations / news sources need a licensing review — gate that to when technique (d) is enabled (P3).
4. **Cultural-fidelity eval harness** — *needed before (c)/(d) promotion* (the quality gate). How to measure canon-fidelity + cultural-faithfulness (not just JSON validity) is an open research item (Pass 1 OQ#3); design the harness in PLAN.
5. **Confidence auto-admit thresholds** — default: **always human-gate initially**; calibrate auto-admit tiers later from eval data.

## 8. Next steps

- [x] Fold Pass 3 competitive findings into RESEARCH_LANDSCAPE.md.
- [x] REVIEW round 1 — resolved: separate service; all 4 techniques, phased by effectiveness-per-cost (§7).
- [ ] PLAN: resolve knowledge-service dependency split (stub vs own minimal KG slice); design the `EnrichmentStrategy` interface + cost/quality gate; design the cultural-fidelity eval harness.
- [ ] Freeze API contract (`contracts/api/lore-enrichment.yaml`).
- [ ] RAID-decompose into cycles → write `.raid/active-task.yaml` + `docs/plans/<slug>/` (decomposition, locked questions, pre-flight).
- [ ] Confirm task size (likely **XL** — new service, schema, multi-service contracts → spec + plan + subagent recommended).
