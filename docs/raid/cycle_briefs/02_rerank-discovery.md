# Cycle 2: Rerank discovery (BE+FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
Make rerank models **auto-discoverable**: the `provider-registry-service` inventory sync parses a **Cohere-shape `/v1/models`** response, recognizes rerank-capable models, and tags `capability_flags.rerank` on the inventoried `user_models` row — so a user adds a local-rerank credential, hits **Refresh**, and the model appears under "Reranker" without hand-registering. Plus FE setup guidance pointing the user at the credential + refresh flow.
- **Scope:** Cross-service (provider-registry BE inventory parse + FE setup guidance). The discovery counterpart to C1's manual registration.
- **Acceptance gate:** `scripts/raid/verify-cycle-2.sh` exits 0 (this cycle's runner creates that script).
- **Top 3 LOCKED decisions consumed:** provider-registry rail (local rerank backend = BYOK credential, never per-service URL/token), Scope-LOCKED (rerank optional grounding-quality), G4 (Playwright screenshot + a real cross-service live-smoke call).
- **DPS count:** 2
- **Estimated wall time:** ~3 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0, C1
- Files expected to exist: provider-registry inventory-sync module; `CapabilityFlags`/`RerankModelPicker` (C1) so a discovered rerank model lands in the picker.

## Scope (IN)
- provider-registry inventory sync: parse a **Cohere-shape `/v1/models`** payload, detect rerank-capable entries, and set `capability_flags.rerank` on the resolved `user_models` row (BYOK credential = kind + `endpoint_base_url` + secret resolved via `provider_credentials`). (BL-2)
- FE **setup guidance**: a panel/copy telling the user to add a local-rerank credential, then Refresh, to populate the Reranker picker.
- `scripts/raid/verify-cycle-2.sh` (acceptance gate) + a Playwright screenshot: add local-rerank credential → Refresh → model listed under "Reranker".

## Scope (OUT — explicitly)
- NO rerank connection-test / `/v1/rerank` round-trip — that is C3.
- NO per-service `RERANK_URL`/`RERANK_MODEL`/`*_SERVICE_TOKEN` env in any consuming service — the local backend is reached ONLY as a provider-registry BYOK credential (the D-RERANK-NOT-BYOK mistake).
- NO hardcoded model names — capability + identity resolve from provider-registry inventory, never a literal.
- NO new manual-register UI (C1) and NO knowledge/writer surfaces.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: provider-registry unit/integration tests for the Cohere-shape `/v1/models` rerank-detection parse + `capability_flags.rerank` tagging.
- Lints pass: provider-registry (Go) + `frontend` lints clean on touched files.
- **Live-smoke token (REQUIRED — cross-service, CLAUDE.md VERIFY rule):** evidence string contains `live smoke: add local-rerank credential → Refresh → rerank model appears under Reranker` (real provider-registry inventory sync against a running local-rerank backend on a stack-up, not mocked). If full stack un-bootable: `live infra unavailable: <reason>` is the only allowed substitute.
- Integration smoke (Playwright screenshot per G4): the discovered rerank model shows under "Reranker". Screenshot filed with this brief. Rebuild the provider-registry image before live-smoke (stale image = false-green).

## DPS parallelism plan
- DPS 1 (BE): provider-registry inventory sync — Cohere-shape `/v1/models` rerank detection + `capability_flags.rerank` tagging (return budget: 1500 tokens summary).
- DPS 2 (FE): setup-guidance panel + Refresh flow wiring to the picker.
- Serial tail: `verify-cycle-2.sh` + live-smoke + Playwright screenshot once BE+FE land (needs a running stack).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- A per-service rerank URL/token sneaking in instead of a provider-registry credential — the D-RERANK-NOT-BYOK regression; the local backend MUST be a BYOK credential resolved via an `/internal/*` provider-registry route.
- A hardcoded model name in the inventory parser (other than provider-registry's own preconfig/pricing or test fixtures).
- Cohere-shape parse that mis-tags non-rerank models, or misses rerank models with a slightly different `/v1/models` shape — check the detection predicate.
- Mock-only false-green: the live-smoke token must reflect a REAL inventory sync against a running local-rerank backend, not a mocked response. Stale image hides missing route/tag.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (Cohere-shape parse, `capability_flags.rerank` tagging, FE setup guidance).
- No OUT items touched (no connection-test, no per-service URL/token env, no hardcoded models).
- All acceptance criteria met; `verify-cycle-2.sh` exits 0 with the live-smoke token + a filed Playwright screenshot.
- Cross-cycle invariant: discovered rerank models flow into C1's picker; rerank stays a provider-registry credential.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) C2 (cross-service / live-smoke list).
- LOCKED: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) §Architecture-review (rerank via provider-registry BYOK, provider-gate green), §Scope, §G4.
- Source spec: [knowledge-service-standalone-ux-review](../../specs/2026-06-13-knowledge-service-standalone-ux-review.md). BL-2 origin per the decomposition Sources list (knowledge-fe-ux-qol-gaps).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Provider rail LOCKED (ENFORCED):** the local-rerank backend is a BYOK provider-registry credential (kind + `endpoint_base_url` + secret) — NO `RERANK_URL`/`RERANK_MODEL`/`*_SERVICE_TOKEN` per-service env (the D-RERANK-NOT-BYOK fix).
- 🔴 **No hardcoded model names (ENFORCED):** capability + identity come from provider-registry inventory; literals are a provider-gate defect.
- 🔴 **Cross-service live-smoke REQUIRED:** evidence MUST carry `live smoke: …` from a REAL inventory sync on a stack-up (rebuild the provider-registry image first); mock-only is a false-green and fails review.
- 🔴 **G4 LOCKED:** also file a Playwright screenshot of the rerank model under "Reranker".
- 🔴 **Do NOT touch:** the `/v1/rerank` connection-test (C3), manual-register UI (C1), or knowledge/writer surfaces.
- 🔴 **Fresh session reminder:** new `/raid 2` invocation; no carry-over. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
