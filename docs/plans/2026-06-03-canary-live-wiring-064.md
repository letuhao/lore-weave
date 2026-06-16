# Plan — 064 D-CANARY-LIVE-WIRING: canary-controller live adapters (full 089-style set)

**Date:** 2026-06-03 · **Size:** XL · **Branch:** mmo-rpg/foundation-mega-task
**Workflow:** v2.2 human-in-loop + cold-start `/review-impl` before commit (new service boundary + credential surface + DB writes). No `/amaw`. No push without explicit approval.

## Context

`services/canary-controller/` ships (RAID cycle 38) as a **pure, fully unit-tested state machine** (`internal/canary` `Decide()` + `internal/cohort_router` + `internal/controller`) with every external dependency behind an interface (`DeployStore`, `SLISource`, `RolloutExecutor`, `Pager`). `cmd/canary-controller/main.go` is a **V1 skeleton**: validates env creds, exposes `/healthz`+`/readyz`+`/metrics` stub, runs a **no-op tick loop**. Tracked as `D-CANARY-LIVE-WIRING` (064, HIGH).

**Scoping finding (investigation-first, 2026-06-03):** the *adapters* are buildable now — `migrations/meta/023_deploy_audit.up.sql` exists, `service_acl/matrix.yaml` already registers `canary-controller` (`deploy_audit` SELECT+UPDATE, `meta_write_audit` INSERT, SVID assigned, "sole writer via MetaWrite"), and `deploy_audit` is in the meta `events_allowlist.yaml`. But the **upstream is entirely stubbed**: nothing writes major-deploy canary rows (`deploy.yml` push/traffic-shift is a stub — `D-DEPLOY-LIVE-WIRING`/063), nothing emits `lw_canary_sli_cohort`, and `canary.yml` only *signals* (it does not shift traffic). So the wired controller is **production-shaped but inert until the deploy pipeline lands** — the live round-trip is deferred, exactly as the user chose ("Full 089-style adapter set").

This mirrors 089: build real adapters against real contracts/schemas, contract-test the request shapes, defer only the live e2e.

## Scope — REAL vs DEFERRED

| Piece | Status |
|---|---|
| pgx `DeployStore`: SELECT active major canary; UPDATE stage/history/rollback/complete **via `contracts/meta` MetaWrite()** (same-TX `meta_write_audit`, CAS on `canary_stage`) | **REAL** |
| Prometheus `SLISource`: HTTP `GET {PROM_URL}/api/v1/query` for cohort burn + stage-0 error rate | **REAL** (request shape + parse) |
| GitHub-Actions `RolloutExecutor`: HTTP POST `repository_dispatch` (`canary-promote`/`canary-rollback`) | **REAL** (request shape) |
| PagerDuty `Pager`: HTTP POST Events API v2 `trigger` | **REAL** (request shape) |
| Prometheus metrics: `lw_canary_stage`, `lw_canary_abort_total`, `lw_canary_sli_cohort`, `lw_deploy_freeze_active` (client_golang + promhttp) | **REAL** |
| `main.go`: construct adapters from env → `controller.New` → real tick loop calling `Tick` → update metrics; `--require-providers` fail-closed; idle when unwired | **REAL** |
| Live round-trip (real GitHub/PD/Prom + real deploy pipeline writing rows) | **DEFERRED** `D-CANARY-LIVE-SMOKE` |
| Pre-deploy **baseline burn** capture (no `baseline_burn` column; deploy pipeline must snapshot it) | **DEFERRED** `D-CANARY-BASELINE-CAPTURE` |
| `deploy_audit` UPDATE **outbox event** emission (nil-Outbox in V1; no consumer yet) | **DEFERRED** `D-CANARY-OUTBOX-EMIT` |
| `app_canary_role` GRANT migration applied to a live DB (L+ DB-migration; test-DB only) | **DEFERRED** (flag at POST-REVIEW) |

## Key design decisions

1. **DeployStore reads via raw `*pgxpool.Pool`, writes via `MetaWrite`.** Reads (`ActiveCanary`) need no audit → plain `SELECT`. Writes (`AdvanceStage`/`MarkRolledBack`/`MarkComplete`) MUST go through `contracts/meta` MetaWrite() (the ACL matrix + meta-write-discipline lint require the same-TX `meta_write_audit` row). The store holds both a `*pgxpool.Pool` and a `*meta.Config`.
2. **`ActiveCanary` query:** `SELECT deploy_id, class, canary_stage, canary_history, rolled_back, started_at FROM deploy_audit WHERE class='major' AND completed_at IS NULL AND rolled_back=FALSE ORDER BY started_at DESC LIMIT 1`. `ok=false` on no rows. (canary.yml's `concurrency` group enforces one major canary; LIMIT 1 + a logged warning if a COUNT>1 ever appears.)
3. **Derive `StageEntered`** from the last `canary_history` entry whose `stage == canary_stage` (else `started_at` for stage 0). History entries are `{stage:int, at:RFC3339, reason:string}`.
4. **`BaselineBurn` has no column** → read from `canary_history[0].baseline_burn` if the deploy pipeline captured it; else `0.0` (documented `D-CANARY-BASELINE-CAPTURE`). A `0.0` baseline means the 2× threshold is `0` → any positive cohort burn aborts; that is *fail-safe* (conservative) and harmless while inert, but the deferral must be cleared before real rollouts or every canary will abort.
5. **`AdvanceStage` = read-modify-write the history array, CAS on stage+liveness.** Read current `(canary_stage, canary_history)`; append `{stage:to, at, reason}`; `MetaWrite` UPDATE `NewValues{canary_stage:to, canary_history:<full new JSON []byte>}` with `ExpectedBefore{canary_stage:<old>, rolled_back:false, completed_at:nil}` → `ErrConcurrentStateTransition` on a lost race OR a concurrent abort/complete (the latter change `rolled_back`/`completed_at`, NOT `canary_stage`, so stage-only CAS would let an advance resurrect a rolled-back deploy — review HIGH #1). `canary_history` passed as `[]byte` → jsonb: pgx encodes `[]byte` to a jsonb column correctly (the same path `meta_write_audit`'s `before/after/row_pk` jsonb columns use on every MetaWrite; the `metapg` pg test only covers a TEXT column, so this is verified by the audit-insert path, not that test).
6. **Adapters are pure-seam testable.** Each HTTP adapter has a pure parse/build function (`parsePromQuery`, `buildDispatchBody`, `parsePagerResp`) unit-tested directly, plus an `httptest.Server` test pinning method+path+headers+body (the 089 wiremock equivalent in Go-stdlib).
7. **No vendor SDKs.** GitHub + PagerDuty are plain `net/http` POSTs (provider-gateway invariant is about *AI* providers; these are ops integrations — still, stdlib keeps deps minimal). Prometheus query is `net/http` GET; metrics use the standard `client_golang` already used by 3 other services.
8. **Credentials:** `GITHUB_TOKEN`+`GITHUB_REPO` (owner/repo), `PAGERDUTY_INTEGRATION_KEY`, `PROM_URL`, `LW_META_DSN`. Env-only, never logged. `--require-providers` keeps the existing fail-closed behavior; absent creds → idle loop (controller not constructed).

## Files

**New** (`services/canary-controller/internal/`):
- `store/deploy_store_pg.go` + `deploy_store_pg_test.go` (+ test-DB-tagged integration)
- `sli/prometheus_source.go` + `prometheus_source_test.go`
- `executor/github_executor.go` + `github_executor_test.go`
- `pager/pagerduty_pager.go` + `pagerduty_pager_test.go`
- `metrics/metrics.go` (+ test)

**Modified:**
- `cmd/canary-controller/main.go` (construct + wire + real loop + promhttp)
- `go.mod` / `go.sum` (pgx/v5, pgxpool, client_golang, contracts/meta, sdks/go/metapg, google/uuid; mirror breach-notifier's module refs)

**Docs:**
- `docs/plans/2026-06-03-canary-live-wiring-064.md` (this)
- `docs/deferred/DEFERRED.md` (064→ADDRESSED; open D-CANARY-LIVE-SMOKE, D-CANARY-BASELINE-CAPTURE, D-CANARY-OUTBOX-EMIT)
- `docs/sessions/SESSION_PATCH.md`

## Verification

- `go build ./... && go vet ./... && go test ./...` (canary-controller) green; `gofmt`.
- **Unit/contract:** DeployStore derivation (StageEntered from history; baseline fallback; ok=false on no row) with a fake `meta.Tx`/pool seam; each HTTP adapter's pure build/parse fn + an `httptest` request-shape test (method/path/auth header/body). Metrics register + render.
- **Full 15-lint matrix** (111 lesson) incl. `meta-write-discipline-lint.sh`, `service-acl` matrix, `language-rule-lint.sh` (canary-controller = Go), `lint-foundation`.
- **Live smoke:** DEFERRED `D-CANARY-LIVE-SMOKE` (no real GitHub/PD/Prom + no deploy pipeline at dev time) — `live infra unavailable` token in VERIFY evidence.
- DB migration (`app_canary_role` grant): NOT applied to any non-test DB; flagged at POST-REVIEW.

## Workflow / guardrails

- v2.2 + cold-start `/review-impl` before commit. Honest-status: the inert-until-launch reality + baseline-fallback + deferred outbox are surfaced in the deferrals + `main.go`/`mod.rs`-equivalent doc comments + the POST-REVIEW summary, never hidden.
- Stage only changed files (no `git add -A`). Co-author trailer. No push without approval.
