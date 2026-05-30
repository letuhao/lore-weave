# Cycle 1: KG-read port + verifies

## 🎯 TL;DR (30 seconds — TOP critical info)
Build the **read-only** client layer that lets lore-enrichment-service consume platform data WITHOUT writing it, plus a degradation seam, plus three platform-assumption verifies that everything downstream depends on.
- **Deliverables:** `app/clients/` (knowledge-service: graph, graph-stats, context, embedding-model; glossary read; book-service read) + a `KnowledgeReadPort` Protocol with a real impl, a Null impl, and a cached impl (Q6 graceful degradation).
- **Verifies (record findings, do NOT fix platform here):** H2 glossary entity scoping (user/project/book), H1 glossary→KG sync trigger, M4 injection-defense + CJK importability of the read path.
- **Acceptance gate:** `scripts/raid/verify-cycle-1.sh` exits 0 (this cycle's runner creates that script). It asserts read-only clients exist, port + Null/cached impls present, no provider model names hardcoded, and the **live-smoke** + verify-findings artifacts are recorded.
- **Cross-service: YES** — acceptance MUST carry a live-smoke token (read real graph-stats from a running knowledge-service).
- **LOCKED rails:** Q2 write-through-glossary-only (this cycle is READ-only — no writes at all); Q6 thin read port; no hardcoded model names (Execution decision); never touch world-service/game-server/infra/existing-prod.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- C0 ships the FastAPI skeleton (`config.py` fail-fast, `/health`, DB pool, `deps.py`, gateway route). This cycle's clients hang off `deps.py` and read C0's config for service base URLs + `INTERNAL_SERVICE_TOKEN`.

## Scope (IN)
- `app/clients/knowledge.py` — typed read clients: graph neighborhood, **graph-stats**, context, embedding-model resolution. Embedding/model identity resolved via **provider-registry** (never hardcoded).
- `app/clients/glossary.py` — read entities/wiki for a `(user_id, project_id, book_id)` scope.
- `app/clients/book.py` — read source via `GET /internal/books/{book_id}/chapters/{chapter_id}/hierarchy`.
- `app/clients/port.py` — `KnowledgeReadPort` Protocol; `KnowledgeReadHttp` (real), `NullKnowledgeRead` (returns empty/typed-default when KG is down → graceful degradation, Q6), `CachedKnowledgeRead` (TTL wrapper for hot graph-stats reads).
- All clients carry `INTERNAL_SERVICE_TOKEN` for `/internal/*`; JWT passthrough for user-scoped reads. Timeouts + typed errors; UTF-8/CJK-safe request+response handling.
- **Verify H2:** probe whether glossary entity reads are scoped by user/project/book; record exact scoping keys + whether cross-project bleed is possible.
- **Verify H1:** probe the glossary→KG sync path (manual `glossary_sync` today vs C4's planned `glossary.entity_updated` event); record current trigger + whether reads see synced state.
- **Verify M4:** confirm the read path neutralizes prompt-injection-bearing entity text on the way IN, and that CJK (封神演义 names: 玉虛宮/碧遊宮/金鰲島/蓬萊/陳塘關) round-trips through clients without mojibake.
- `scripts/raid/verify-cycle-1.sh` (the acceptance gate) + a `docs/raid/findings/C1-verifies.md` recording H1/H2/M4 results.

## Scope (OUT — explicitly)
- **NO writes anywhere.** No `extract-entities`, no wiki generate, no Neo4j writes — that is Q2/C11/C13 territory.
- **NOT fixing** H1 (that is C4's K14 pipeline) or H3 wiki (C5). This cycle only VERIFIES + records H1/H2/M4 findings.
- No gap model/engine (C6/C7), no strategies (C8–C10), no proposal schema (C2), no eval (C15).
- No new RAG framework, no langchain/llamaindex. Retrieval reuse (`/internal/embed`) belongs to C10, not here.
- No edits to knowledge-service, glossary-service, or book-service code — read clients only consume their existing endpoints.

## Acceptance criteria (CI gates — exit code 0 = pass)
- `scripts/raid/verify-cycle-1.sh` exits 0. It checks:
  1. `app/clients/{knowledge,glossary,book,port}.py` exist; `KnowledgeReadPort` Protocol + `NullKnowledgeRead` + `CachedKnowledgeRead` present.
  2. **No hardcoded provider/model names** (grep guard for literal model strings; embedding/model identity comes from provider-registry resolution).
  3. Null impl returns typed empties when the KG client raises (degradation unit test green).
  4. **CJK round-trip** unit test passes for the 4 locked Fengshen place names.
- **Live-smoke token (REQUIRED — cross-service, CLAUDE.md VERIFY rule):** evidence string contains `live smoke: read graph-stats from running knowledge-service` (real call on a stack-up, not mocked). If full stack un-bootable: `live infra unavailable: <reason>` is the only allowed substitute, and verify findings then note degraded confidence.
- `docs/raid/findings/C1-verifies.md` records H2 scoping keys, H1 sync-trigger state, and M4 injection+CJK results — file non-empty.
- `pytest` for `app/clients/` green; no network in unit tests (real call lives only in the live-smoke step).

## DPS parallelism plan
Three independent client modules → fan out as parallel DPS sub-agents, then converge:
- **DPS-A:** `clients/knowledge.py` + graph-stats + embedding-model-via-registry.
- **DPS-B:** `clients/glossary.py` + book.py read clients.
- **DPS-C:** `clients/port.py` (Protocol + Null + cached) — depends on A/B type shapes, so seam-stub first, integrate last.
- **Serial tail (Raid Leader):** the three verifies (H1/H2/M4) + live-smoke + `verify-cycle-1.sh` — these need the assembled clients and a running stack, so run after A/B/C land.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Mock-only false-green:** unit suite passes but no real cross-service call ran → confirm the live-smoke token is present and reflects a genuine graph-stats read, not a mocked one.
- **Hardcoded model names:** any literal embedding/model string (e.g. `text-embedding-bge-m3`, `qwen`) baked into client code instead of resolved via provider-registry → LOCKED violation.
- **Accidental write surface:** any client method that POSTs/PUTs/PATCHes — this cycle is read-only; a write here breaks Q2 (glossary-SSOT-only).
- **Degradation gap:** Null impl that raises or returns `None` instead of typed empties → defeats Q6 graceful degradation.
- **CJK corruption / injection passthrough:** non-UTF-8 handling, or entity text with embedded instructions passed downstream un-neutralized (M4).
- **Scoping bleed:** glossary read that ignores `project_id`/`book_id` and can leak cross-project entities (H2).

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only `app/clients/`, `scripts/raid/verify-cycle-1.sh`, `docs/raid/findings/C1-verifies.md`, and client tests changed; ZERO writes to any platform service; no edits to knowledge-service/glossary-service/book-service/world-service/game-server/infra/existing-prod; `verify-cycle-1.sh` exits 0 with live-smoke token recorded. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- `docs/plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md` — C1 row + cross-service live-smoke note.
- `docs/plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md` — Q2, Q6, H0, H1, K14 entries.
- `docs/03_planning/lore-enrichment/PLAN.md` — read endpoints table (knowledge/glossary/book), `INTERNAL_SERVICE_TOKEN` auth, per-project scoping.
- `docs/03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md` — service boundaries + platform-assumption ground truth.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **READ-ONLY (Q2 LOCKED):** this cycle writes NOTHING to any platform service. Write-back goes through glossary SSOT later (C11/C13). A POST/PUT/PATCH in any client is a hard violation.
- 🔴 **NO hardcoded model names (Execution LOCKED):** embedding (`text-embedding-bge-m3`) and app LLM (Qwen 3.6 via LM Studio) are resolved via provider-registry. Never bake a literal into client code.
- 🔴 **Q6 graceful degradation LOCKED:** `NullKnowledgeRead` MUST return typed empties (never raise / never `None`) so enrichment survives a down KG.
- 🔴 **Acceptance gate:** `scripts/raid/verify-cycle-1.sh` must exit 0 AND the evidence string must carry `live smoke: read graph-stats from running knowledge-service` (cross-service rule) — mock-only is a false-green and fails review.
- 🔴 **DO NOT TOUCH:** world-service, game-server, tilemap, `infra/existing-prod/`, knowledge/glossary/book service code, or other agents' files. Verifies RECORD findings only; they do not fix H1/H3.
