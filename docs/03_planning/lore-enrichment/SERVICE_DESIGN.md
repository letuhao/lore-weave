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

## 7. Open design questions (for REVIEW)

1. **New service vs module of knowledge-service?** Current lean: separate `lore-enrichment-service` (distinct lifecycle, heavy LLM/RAG workload), but it depends tightly on knowledge-service's KG — confirm boundary.
2. **External cultural corpora** — licensing, sourcing, and storage of Shan Hai Jing / Shang–Zhou history texts (technique b/d). Public-domain classical Chinese texts likely OK; modern translations/news need care.
3. **Cultural-anachronism evaluation** — open research question (Pass 1 OQ#3): how to *measure* canon-fidelity + cultural-faithfulness, not just JSON validity. Needs an eval harness.
4. **"Re-cooking real news" technique (d)** — scope for the Fengshen mythological demo vs later realistic settings; may be deferred.
5. **Confidence thresholds & auto-admit** — which confidence tier may auto-write vs always require human gate.

## 8. Next steps

- [x] Fold Pass 3 competitive findings into RESEARCH_LANDSCAPE.md.
- [ ] REVIEW this design (Lead + PO perspectives) → resolve §7 open questions.
- [ ] Freeze API contract (`contracts/api/lore-enrichment.yaml`).
- [ ] RAID-decompose into cycles → write `.raid/active-task.yaml` + `docs/plans/<slug>/` (decomposition, locked questions, pre-flight).
- [ ] Confirm task size (likely **XL** — new service, schema, multi-service contracts → spec + plan + subagent recommended).
