# Cycle 3: Rerank connection test (BE+FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
Make the model **verify/test** action rerank-aware: when the user clicks "Test" on a rerank model in `EditModelModal`, the backend performs a **real `/v1/rerank` round-trip** (through provider-registry to the user's BYOK rerank backend) and returns ranked scores / latency — instead of the generic chat/embedding probe that doesn't exercise a reranker. This closes the loop: register (C1) → discover (C2) → **prove it actually ranks** (C3).
- **Scope:** Cross-service (provider-registry rerank verify path BE + `EditModelModal` FE).
- **Acceptance gate:** `scripts/raid/verify-cycle-3.sh` exits 0 (this cycle's runner creates that script).
- **Top 3 LOCKED decisions consumed:** provider-registry rail (rerank call goes through provider-registry BYOK, no per-service URL/token, no hardcoded model), Scope-LOCKED (rerank optional grounding-quality), G4 (Playwright screenshot + real cross-service live-smoke).
- **DPS count:** 2
- **Estimated wall time:** ~3 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C2
- Files expected to exist: `EditModelModal` (FE); provider-registry verify/test endpoint + the C2 inventory-tagged rerank `user_models` row.

## Scope (IN)
- Rerank-aware **verify** path: provider-registry performs a real `/v1/rerank` round-trip against the user's resolved BYOK rerank credential and returns ranked scores + latency. (BL-10)
- `EditModelModal` FE: a "Test" affordance for rerank models that calls the rerank-aware verify and renders ranked scores / latency / pass-fail.
- `scripts/raid/verify-cycle-3.sh` (acceptance gate) + a Playwright screenshot: Test a rerank model → ranked scores / latency shown.

## Scope (OUT — explicitly)
- NO inventory discovery / Cohere-shape parse — that landed in C2.
- NO grounding/packer rerank integration (junk-rejection in retrieval) — out of this rerank trio's scope.
- NO per-service rerank URL/token env; NO hardcoded rerank model name — resolve via provider-registry BYOK.
- NO knowledge/writer/graph surfaces.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: provider-registry unit/integration tests for the rerank verify path (request shaping + score/latency parse); `frontend` test for the `EditModelModal` rerank Test rendering.
- Lints pass: provider-registry (Go) + `frontend` lints clean on touched files.
- **Live-smoke token (REQUIRED — cross-service, CLAUDE.md VERIFY rule):** evidence string contains `live smoke: Test a rerank model → real /v1/rerank round-trip returns ranked scores + latency` (real call against a running local-rerank backend on a stack-up, not mocked). If full stack un-bootable: `live infra unavailable: <reason>` is the only allowed substitute.
- Integration smoke (Playwright screenshot per G4): the rerank Test result renders ranked scores / latency. Screenshot filed. Rebuild the provider-registry image before live-smoke.

## DPS parallelism plan
- DPS 1 (BE): provider-registry rerank-aware verify — `/v1/rerank` round-trip via the BYOK credential + score/latency response shape (return budget: 1500 tokens summary).
- DPS 2 (FE): `EditModelModal` rerank Test affordance + result rendering.
- Serial tail: `verify-cycle-3.sh` + live-smoke + Playwright screenshot once BE+FE land (needs a running stack).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- The verify path calling a rerank endpoint directly from a consuming service instead of through provider-registry — every provider call goes through provider-registry (the only place provider SDKs/HTTP live).
- A hardcoded rerank model name or a per-service rerank URL/token env — provider-gate defect.
- Verify that "passes" without actually exercising `/v1/rerank` (e.g. falls back to a generic probe) — confirm the round-trip is rerank-shaped (documents + query → scores).
- Mock-only false-green: live-smoke token must reflect a REAL `/v1/rerank` call on a stack-up; stale provider-registry image hides a missing route.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (rerank-aware verify, real `/v1/rerank` round-trip, `EditModelModal` Test UI).
- No OUT items touched (no discovery, no packer integration, no per-service URL/token, no hardcoded models).
- All acceptance criteria met; `verify-cycle-3.sh` exits 0 with the live-smoke token + a filed Playwright screenshot.
- Cross-cycle invariant: rerank call routed through provider-registry; the rerank trio (C1–C3) is complete.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) C3 (cross-service / live-smoke list).
- LOCKED: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) §Architecture-review (rerank via provider-registry BYOK, provider-gate green), §Scope, §G4.
- Source spec: [knowledge-service-standalone-ux-review](../../specs/2026-06-13-knowledge-service-standalone-ux-review.md). BL-10 origin per the decomposition Sources list (knowledge-fe-ux-qol-gaps).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Provider gateway invariant (ENFORCED):** the `/v1/rerank` round-trip goes through provider-registry — NO direct provider call from a consuming service, NO per-service rerank URL/token env, NO hardcoded rerank model name.
- 🔴 **Cross-service live-smoke REQUIRED:** evidence MUST carry `live smoke: …` from a REAL `/v1/rerank` round-trip on a stack-up (rebuild provider-registry image first); mock-only fails review.
- 🔴 **Scope LOCKED:** rerank is optional grounding-quality — this cycle proves the model ranks; it does NOT wire rerank into the packer/grounding path.
- 🔴 **G4 LOCKED:** also file a Playwright screenshot of the rerank Test result (scores/latency).
- 🔴 **Do NOT touch:** C2 discovery, packer grounding, or knowledge/writer surfaces.
- 🔴 **Fresh session reminder:** new `/raid 3` invocation; no carry-over. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
