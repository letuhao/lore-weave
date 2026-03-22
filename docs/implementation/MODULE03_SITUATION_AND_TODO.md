# Module 03 — implementation situation and todo backlog

## Document Metadata

- Document ID: LW-IMPL-M03-01
- Version: 1.0.0
- Status: Active
- Owner: Execution Authority + Tech Lead + QA Lead (consulted)
- Last Updated: 2026-03-22
- Approved By: Pending
- Approved Date: N/A
- Summary: Current implementation situation for Module 03 (provider registry + model billing) and a practical todo list for future execution waves.

## Change History

| Version | Date       | Change                          | Author    |
| ------- | ---------- | ------------------------------- | --------- |
| 1.0.0   | 2026-03-22 | Initial situation and todo backlog for M03 | Assistant |

## Current Situation (Module 03)

- Both backend services (`provider-registry-service`, `usage-billing-service`) are fully coded and smoke-tested.
- Core provider credential CRUD, health checks, model inventory sync, user model management (CRUD + activation/favorite/tags), and platform model admin endpoints are implemented.
- Usage metering pipeline (record invocation → quota/credits billing → encrypted payload storage → decrypt audit) is implemented and smoke-tested.
- Frontend pages are live: `UserModelsPage` (with embedded provider credential management), `PlatformModelsPage`, `UsageLogsPage`, `UsageDetailPage`.
- Unit tests exist for server handlers, crypto helpers, adapter layer, and key frontend pages.
- Current validation posture is **smoke-testing only**; formal acceptance matrix (`M03-AT-01` through `M03-AT-21`) has not been executed.
- Several backend behaviors and security invariants require integration-level evidence to close the acceptance gate.

## Testing Reality Check

- **What exists now:** smoke checks, unit tests for handler validation/auth guards, crypto round-trip, adapter factory, and selected frontend page renders.
- **What is not complete yet:** full acceptance matrix execution, integration traces proving provider-gateway routing invariant, DB-level ciphertext verification, formal evidence pack for QA sign-off.
- **Implication:** current state is suitable for iterative development progress, not formal acceptance closure or production release gate.

## Todo Backlog (Future Plan)

| Area | Todo item | Priority | Target phase |
| --- | --- | --- | --- |
| QA / acceptance | Execute full M03 acceptance matrix M03-AT-01 through M03-AT-21 with captured evidence (API + UI + DB where required) | P0 | Next execution wave |
| Security / encryption | Verify DB ciphertext columns are never plaintext — produce DB-level audit evidence for M03-AT-16 | P0 | Next execution wave |
| Security / routing | Add integration test proving all model invocations route through adapter layer and bypass attempts return `M03_PROVIDER_ROUTE_VIOLATION` (M03-AT-20, M03-AT-21) | P0 | Next execution wave |
| Security / access | Verify non-owner detail view returns `M03_LOG_DECRYPT_FORBIDDEN` with no payload leakage (M03-AT-18); verify ciphertext corruption path (M03-AT-19) | P0 | Next execution wave |
| Billing / correctness | Integration tests for quota-first path (M03-AT-09), credits-overage path (M03-AT-10), and exhausted-both rejection (M03-AT-11) with deterministic arithmetic | P0 | Next execution wave |
| Security / secrets | API-level redaction check: confirm no raw provider key is ever returned in list/detail/log responses (M03-AT-14) | P0 | Next execution wave |
| QA / acceptance | Produce reconciliation sample report covering at least one time window per evidence pack requirements (`47` §4) | P0 | Next execution wave |
| Frontend / coverage | Add unit/render tests for `PlatformModelsPage` (no test file exists yet) | P1 | Next execution wave |
| Frontend / UX | Add dedicated `ProvidersPage` for provider credential management; current route `/m03/providers` redirects to `/m03/models` — may be intentional but warrants explicit product decision | P1 | Next execution wave |
| Backend / admin | Verify or add admin endpoints for balance management (credit top-up, quota adjustment); currently no `POST /admin/account-balances` endpoint exists in billing service | P1 | Next execution wave |
| Backend / observability | Implement structured metrics per design doc `51` §8: provider health counts, quota/credit exhaustion counters, decrypt success/failure, route violation counts, inventory sync counters | P1 | Future wave |
| Backend / billing | Implement monthly quota reset job (currently quota is set at account creation but no scheduled reset mechanism exists) | P1 | Future wave |
| Operational readiness | Build formal release checklist and rollback playbook aligned with readiness gate `55` requirements | P1 | Pre-release wave |
| Key management | Upgrade credential and payload encryption from derived-JWT-key to proper KMS/vault abstraction per design doc `51` §7 (current AES-256-GCM with padded JWT secret is MVP; production requires proper key wrapping) | P2 | Pre-production wave |

## Deferred / Not Fully Implemented Yet

- Full acceptance evidence pack is not produced.
- Formal GO/NO-GO decision record in gate `55` has not been filled (outcome is still `Pending`).
- Production-grade KMS/vault integration for credential vaulting is deferred to pre-production hardening.
- Monthly quota reset scheduling is not implemented.

## Explicitly Not Implemented In This Wave (Inventory)

| Item | Current status | Planned direction |
| ---- | -------------- | ----------------- |
| Formal acceptance evidence pack (DB audit, API traces, UI recordings, reconciliation sample) | **Not produced** (smoke only) | Execute AT matrix and produce artifact bundle per `47` §4 |
| Integration tests for anti-bypass route invariant | **Not implemented** (unit guards only) | Add integration trace that proves adapter-only invocation and route-violation guard failure |
| Monthly quota reset background job | **Not implemented** (quota is set once at account creation) | Add scheduler or cron-style reset at billing period rollover |
| Admin credit top-up / quota override endpoints | **Not implemented** | Add admin balance management endpoints aligned with `45` contract |
| Proper KMS / vault key wrapping | **Not implemented** (MVP uses AES-256-GCM with JWT-secret-derived key) | Replace with envelope encryption + external KMS/vault per `51` §7 before production |
| Physical GC for old usage log rows and orphaned ciphertext | **Not implemented** (out of scope per `44` §3) | Future operational wave |
| Enterprise invoicing and tax pipeline | **Not implemented** (out of scope per `44` §3) | Future billing wave |
| Multi-currency billing rendering | **Not implemented** (out of scope per `47` §6) | Future billing wave |
| Provider auto-provisioning with cloud marketplaces | **Not implemented** (out of scope per `44` §3) | Future platform wave |
| Dedicated `ProvidersPage` frontend | **Redirects to models page** (intentional MVP compromise) | Explicit product decision needed before next UX wave |
| Observability metrics (Prometheus/OTEL counters) | **Not implemented** | Add alongside pre-release hardening |
| Full invoice export formatting | **Not implemented** (out of scope per `47` §6) | Future billing wave |

## References

- `docs/03_planning/44_PHASE1_MODULE03_PROVIDER_REGISTRY_EXECUTION_PACK.md`
- `docs/03_planning/45_MODULE03_API_CONTRACT_DRAFT.md`
- `docs/03_planning/47_MODULE03_ACCEPTANCE_TEST_PLAN.md`
- `docs/03_planning/48_MODULE03_RISK_DEPENDENCY_ROLLOUT.md`
- `docs/03_planning/51_MODULE03_BACKEND_DETAILED_DESIGN.md`
- `docs/03_planning/52_MODULE03_FRONTEND_DETAILED_DESIGN.md`
- `docs/03_planning/55_MODULE03_IMPLEMENTATION_READINESS_GATE.md`
