# Cycle 16 — Work-setup resilience (BE composition) — LIVE SMOKE

**Token:** `live smoke: knowledge down → POST /work 2xx → Generate returns prose`

**Date:** 2026-06-14 · **Stack:** infra docker-compose (composition-service rebuilt 3×; gateway :3123; knowledge-service :8216).
Test account `claude-test@loreweave.dev`. Chat model: Qwen2.5-7B Instruct (`019eb620-...`, LM Studio BYOK via provider-registry).

## Fault injection (scoped)
`docker compose -f infra/docker-compose.yml stop knowledge-service` → `curl :8216/health` = connection refused (000). Demo DB untouched (no `-v`).

## Part A — POST /work survives a knowledge OUTAGE (WG-3)
Greenfield book `019ec5f8-1ba9-785e-8087-68ebb9afbb6a` ("C16 Smoke Greenfield"), knowledge DOWN:

```
POST /v1/composition/books/019ec5f8-.../work  → HTTP 201
{"project_id":null,"id":"019ec5f8-9a1a-7aa2-b15a-9b5edea425b2","pending_project_backfill":true,...}
```
Was a 502 KNOWLEDGE_UNAVAILABLE before C16. The writer is NOT wall-blocked — a lazy null-project Work is persisted with the backfill marker.

## Part B(i) — deployed packer null-project path (no knowledge lens, no NPE)
In-container probe of the REAL deployed `app.packer.pack._pack_null_project` (a spy knowledge client that raises if any lens is called):
```
NULL-PROJECT PACK OK: grounding_available=False prompt_len=31 warnings=1 (NO lens called)
```
Proves the deployed image degrades to empty-but-valid grounding without widening cross-project (C23 guard preserved by never calling the lens).

## Part B(ii) — Generate returns prose with empty grounding (knowledge DOWN)
Cowrite generate on the demo Work `019eb683-...` (a REAL-project Work) scene `019ec5d0-...`, knowledge still DOWN.
NOTE: this proves grounding→empty→prose on a project-keyed Work. A STILL-PENDING null-project Work is not
addressable by the `{project_id}`-keyed generate route (project_id is the URL key); its prose-readiness is proven by
Part B(i) (the deployed packer null-path) + its backfill makes it project-keyed and fully draftable. See D-C16-NULL-WORK-ROUTE.
```
data: {"type":"job","grounding_available":false,"assembly_mode":"per_scene",...}
... 94 token deltas ... (紫怡偏殿内弥漫着淡淡的香雾，空气中似乎还残留着昨日的紧张气息。...)
data: {"type":"done","status":"completed","output_tokens":95,"finish_reason":"stop"}
```
`grounding_available:false` + real streamed prose → grounding degrades, prose still returns (cross-service round-trip, not a mock).

## Restore + backfill seam
`docker compose ... up -d knowledge-service` → `:8216/health` = **200** (later cycles unblocked).
Retry POST /work on the greenfield book (knowledge UP) → **backfill**, same row:
```
{"project_id":"019ec5fd-78a2-7b4b-b155-27718e26b84d","id":"019ec5f8-9a1a-7aa2-b15a-9b5edea425b2","pending_project_backfill":false,...}
```
Same `id` + created_at; project stamped on, marker cleared — no duplicate Work. Full lifecycle outage→null→recovery→backfill proven.

## Migration safety (real PG)
Upgrade path tested on a pre-C16 schema seed (project_id PK, 1 legacy row): after `run_migrations` ×2 → `pk=[id]`, `project_id nullable=YES`, rows=1, null_ids=0 (idempotent, no data loss). Live `loreweave_composition`: 163 rows preserved, PK re-pointed to `id`, project_id nullable.
