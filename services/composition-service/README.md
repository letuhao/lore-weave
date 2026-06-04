# composition-service (LOOM — Composition V0)

The lore-grounded **co-writer**: RAG-packs canon (knowledge graph + glossary +
prose) into spoiler-safe context, co-writes prose via the LLM gateway, and runs
an advisory critic (`judge_prose`). Built on the **Canon Model** primitives
(editorial lifecycle · canon=published · dual-order · provenance).

- **Design SSOT:** `docs/specs/2026-06-02-composition-design.md`
- **Plan:** `docs/plans/2026-06-02-composition-service-v0.md` (milestones M0–M9)
- **DB:** `loreweave_composition` (single, asyncpg, single-DDL idempotent migrate)
- **Port:** host `8217` → container `8093`

## Status
- **M0 (skeleton)** ✅ — boots, `GET /health`, `/v1/composition/ping`, `/metrics`.
- M1 schema · M2 repos · M3 clients/prose-source · M4 packer · M5 isolation ·
  M6 engine+critic · M7 contract+gateway · M8 FE tab · M9 OI-1 publish wiring.

## Boundary
Touches composition + additive infra only. **Never touches `lore-enrichment-service`.**
No edits to glossary/book/knowledge service code — consume via HTTP + the Canon
Model primitives.

## Dev
```bash
docker compose up -d composition-service      # from infra/
curl localhost:8217/health                    # {"status":"ok",...}
# host pytest:
PYTHONPATH=. python -m pytest tests/unit -q
```
