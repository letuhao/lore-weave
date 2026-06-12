# Cycle 4: PLATFORM K14 event pipeline

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Wire automatic glossary→KG propagation (resolves **H1**). glossary-service emits a `glossary.entity_updated` event on **every** entity write — including the bulk `extract-entities` path — onto Redis Streams. knowledge-service adds a consumer that, on each event, triggers its existing `glossary_sync` so the entity lands in Neo4j with no manual call. Touches **glossary-service + knowledge-service** only; changes are strictly **ADDITIVE / backward-compatible** (new emit + new consumer, no behavior removed, no contract broken).
- **Acceptance gate:** `scripts/raid/verify-cycle-4.sh` exits 0 (created by this cycle's runner).
- **Top 3 LOCKED decisions consumed:** Q2 (glossary SSOT → glossary_sync → Neo4j; never write Neo4j directly), H1 (automatic platform-wide propagation), Isolation (platform edits additive only; never touch world-service/game-server).
- **DPS count:** 3
- **Estimated wall time:** 3–5 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C1
- Files expected to exist (grep-able paths): `services/glossary-service/` (entity write + `extract-entities` bulk handler), `services/knowledge-service/` (existing `glossary_sync` function + Redis Streams plumbing), `services/lore-enrichment-service/app/clients/` (C1 KG-read port; the H1 sync-trigger verify lives here).

## Scope (IN)
- glossary-service: emit `glossary.entity_updated` on every canonical entity write — single create/update **and** the bulk `POST /books/{id}/extract-entities` path. Event payload carries at minimum `book_id`, `glossary_entity_id`, `name`, `op` (created|updated), `source_type` (preserve `glossary` for authored canon vs `enriched` if present), emitted-at timestamp.
- Publish to Redis Streams using the stream/consumer-group conventions already in the repo (reuse existing producer helper; do not introduce a new broker).
- knowledge-service: new consumer on `glossary.entity_updated` that calls the **existing** `glossary_sync` to upsert the entity into Neo4j. Idempotent on re-delivery (same `glossary_entity_id` + `op` must not duplicate nodes/edges); ACK/retry/dead-letter behavior matches existing consumers.
- Tests: glossary emit unit test (single + bulk fan-out, one event per entity); knowledge-service consumer unit test (event → `glossary_sync` invoked, idempotent on replay); live cross-service smoke (see Acceptance).
- `scripts/raid/verify-cycle-4.sh` running the above as the exit-0 gate.

## Scope (OUT — explicitly)
- NO enrichment write-back, proposal store, or `source_type='enriched'` write path (that is C11/C13).
- NO direct Neo4j writes from any service — propagation goes only through `glossary_sync` (Q2). Do not bypass glossary SSOT.
- NO changes to glossary entity schema, API contract shape, or `extract-entities` request/response (additive emit only — backward-compatible).
- NO edits to world-service, game-server, tilemap, or `infra/existing-prod/` (Isolation lock).
- NO new RAG/broker/framework; NO hardcoded model names (this cycle has no LLM call, but the consumer must not introduce any).
- NO wiki content generation (that is C5/D4-03).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: glossary emit unit test (single + bulk extract-entities → one event per entity); knowledge-service consumer unit test (event → `glossary_sync` called; replay is idempotent).
- Lints pass: glossary-service + knowledge-service language linters clean; no new direct Neo4j-write call sites; no hardcoded model names introduced.
- Integration smoke (REQUIRED — cross-service): **`live smoke:`** on a running stack, write a glossary entity (single + via extract-entities) → observe `glossary.entity_updated` on the stream → confirm the entity appears in Neo4j **automatically** (no manual sync call). The VERIFY evidence string MUST carry the `live smoke: <one-liner>` token (or an explicit `live infra unavailable: <reason>` / `LIVE-SMOKE deferred to ...` per CLAUDE.md VERIFY rule). Mock-only green is INSUFFICIENT — this is a ≥2-service cycle.

## DPS parallelism plan
- DPS 1: glossary-service emit. Add `glossary.entity_updated` publish to the single-entity write path **and** the `extract-entities` bulk path; reuse existing Redis Streams producer. Worktree files: `services/glossary-service/` entity write + extract-entities handler + emit helper + unit test. (return budget: 1500 tokens summary)
- DPS 2: knowledge-service consumer. New consumer subscribing to `glossary.entity_updated`; invoke existing `glossary_sync`; idempotent upsert + ACK/retry/dead-letter matching existing consumers. Worktree files: `services/knowledge-service/` consumer + registration + unit test. (return budget: 1500 tokens)
- DPS 3: verify script + live smoke. Author `scripts/raid/verify-cycle-4.sh` (runs both unit suites + the cross-service smoke), capture the `live smoke:` evidence. Worktree files: `scripts/raid/verify-cycle-4.sh`. (return budget: 1500 tokens)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Mock-only false-green:** confirm a REAL cross-service run happened (glossary write → stream → Neo4j node), not just stubbed `glossary_sync`. This is the single most common failure for this cycle.
- **Bulk-path coverage:** verify `extract-entities` fans out one event PER entity (not a single batch event silently dropping entities). The bulk path is the easy miss — the goal explicitly calls it out.
- **Idempotency / at-least-once delivery:** Redis Streams redelivers on crash/no-ACK. Re-processing the same event must not duplicate Neo4j nodes/edges. Check the consumer is keyed on `glossary_entity_id` and uses upsert semantics.
- **Q2 violation:** any code that writes Neo4j canonical content directly (bypassing `glossary_sync`) is a hard fail.
- **Backward-compat:** emit must not change entity API contract, response shape, or break existing extract-entities callers; a publish failure must not lose/break the primary write (decide and document fire-and-forget vs transactional-outbox; at minimum the write must not silently roll back on broker hiccup).
- **Isolation:** zero edits to world-service/game-server/tilemap/`infra/existing-prod/`.
- **No hardcoded model names** sneaking into the consumer path.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All Scope (IN) items present: emit on single + bulk path, knowledge-service consumer → `glossary_sync`, both unit tests, `verify-cycle-4.sh`.
- No Scope (OUT) items touched: no enriched write-back, no schema/contract change, no direct Neo4j writes, no world-service/game-server/infra/existing-prod edits, no new broker/framework.
- All acceptance criteria met, INCLUDING the `live smoke:` cross-service token in VERIFY evidence.
- Cross-cycle invariants intact: Q2 SSOT path honored; H0 not pre-empted (no enriched canonization here); changes additive/backward-compatible.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C4 row + platform-deferral notes): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- LOCKED decisions (K14 scope decision §, Q2, H1, Isolation): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md)
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md), [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): Q2, H1, Isolation, Q4 (feed extractive machinery, no fork), no-hardcoded-model-names.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1 — Q2:** propagation goes glossary SSOT → `glossary_sync` → Neo4j ONLY. NEVER write Neo4j canonical content directly.
- 🔴 **Top LOCKED 2 — H1:** propagation must be AUTOMATIC and platform-wide — every entity write (single AND bulk extract-entities) emits; no manual sync call.
- 🔴 **Top LOCKED 3 — Isolation / additive-only:** platform edits to glossary + knowledge-service are ADDITIVE / backward-compatible; do NOT touch world-service, game-server, tilemap, or `infra/existing-prod/`.
- 🔴 **Acceptance MUST include:** the `live smoke:` cross-service token — write glossary entity → event → entity appears in Neo4j automatically. Mock-only green does NOT pass (≥2-service cycle).
- 🔴 **Do NOT touch:** no enriched write-back / `source_type='enriched'` path (C11/C13), no entity schema or API-contract change, no new broker/framework, no hardcoded model names.
- 🔴 **Fresh session reminder:** this is a new `/raid 4` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
