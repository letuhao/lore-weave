# Test-Coverage Audit — Findings

- **Date:** 2026-06-20 · **Status:** ✅ COMPLETE · **Type:** read-only structural audit (no code changed)
- **Source:** gap-analysis §11 Task 8.

## Headline
Coverage is **bimodal**: the data/knowledge/money paths and the foundation/MMO ops spine are **GOOD**; the **auth HTTP flow, cross-service contract drift, and 3 services' tenant deny-tests are the riskiest gaps.** The cross-service live-smoke gate the workflow relies on is **non-enforcing** (soft warning) for the application tier.

## Riskiest under-tested surfaces (prioritized)
1. **auth-service refresh-token rotation + revoked/expired-session branches — ZERO coverage.** Crypto primitives are tested (`authjwt/jwt_test.go`, `authpwd/password_test.go`) but there's **no `internal/api/handlers_test.go`** — the stateful login/refresh/logout/rotation flow (the most security-load-bearing code, and where the identity-lifecycle audit found Highs) is untested.
2. **3 services have owner-scoped handlers but NO cross-tenant deny-test** — **sharing-service, provider-registry-service, usage-billing-service**. Their only 403 tests are *admin-role* guards (a `user` hitting platform endpoints), which **look like** tenant coverage but aren't. Exactly the `e0-grant-mapping-test-pattern` lesson: a regression dropping the owner clause passes every existing test. (The IDOR sweep found real findings in provider-registry + an untested surface in sharing.)
3. **App-tier cross-service contract drift — structurally unenforced.** No contract tests (no schemathesis/dredd/pact); the full `infra/docker-compose.yml` app stack is **never booted in CI** (app-tier CI is unit/build only; Python skips pytest); `scripts/workflow-gate.py` live-smoke check is a **soft stderr warning** (bypassable with any string). The mock-only-hides-cross-service-bugs rationale is unmet for the app tier.
4. **travel-service — zero tests** (1 src file, kernel-derived Rust scaffold).
5. **ai-gateway federation dispatch error paths** — the MCP-first routing layer; 181 files but positive-path only (tool-not-found/timeout/provider-5xx/malformed-result untested).
6. **Migration full-chain apply** — per_reality (13) + meta (10) never applied as an ordered chain or rolled back in any test.

## Per-service tiers (summary)
- **GOOD:** book, glossary (best Go), knowledge (best overall), composition, campaign, lore-enrichment, translation, chat, admin-cli, meta-worker, tilemap, world (scaffold), usage-billing\* + provider-registry\* (\*money/pricing strong but missing tenant deny-test).
- **THIN:** auth (flow untested), sharing, api-gateway-bff, game-server, ai-gateway (error paths), notification/statistics/statuspage/slo-budget/postmortem.
- **NONE:** travel-service.

## What's solid
- **Money path is the best-tested critical surface** — `usage-billing/internal/api/guardrail_test.go` (1033 lines): reserve/reconcile/release, 402 budget gating, idempotency; pricing fails-closed on unknown models.
- **Foundation/MMO spine live-smoke is REAL** — `foundation-ci.yml` `db-smoke` boots PG/Redis/MinIO and runs `TestPublisherLiveSmoke`, `TestMetaWorkerLiveSmoke` fan-out per-PR.
- **5 services have proper cross-tenant deny-tests** (book, glossary, campaign, composition, knowledge) — port `book-service/grant_mapping_test.go`'s `denyServer(level)` stub to the 3 missing ones.
- `contracts/` stdlib mostly tested (meta, prompt, resilience, events); **thin:** tracing (1 test), observability (2), logging (2).

## Cross-cut
The two systemic gaps (missing tenant deny-tests; non-enforcing app-tier smoke + no contract tests) are the **same blind spots that let the IDOR-sweep findings exist** — closing them is test-infrastructure work, not per-bug work.
