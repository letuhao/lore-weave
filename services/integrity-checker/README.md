# services/integrity-checker

L3.E (daily sampling) + L3.F (monthly full check) projection integrity checker.

**LOCKED Q-L3E-1**: SEPARATE service (different ops cadence — daily +
monthly cron — can scale independently from world-service / DPS pool).

## What this service does

For each per-reality DB, on a configurable cadence:
1. **Daily mode** (`pkg/daily_loop`) — sample N random aggregates per L3.A
   projection table, re-derive expected state via `pkg/comparator` (calls
   `load_aggregate` abstraction wired to cycle-12 dp-kernel in live wiring),
   diff against the projection row, write drift result to
   `projection_drift_state` via `pkg/state_writer`.
2. **Monthly mode** (`pkg/full_check`) — walks ALL aggregates of each
   projection table via cursor batching (no lock-table). Same comparator,
   different cadence + budget. Different alert SLO (page only on >5 drifts
   in monthly run; daily drift = WARN-only).

## V1 ships as a SKELETON

Following the cycle-11 archive-worker / retention-worker / cycle-14
freeze-rebuild pattern: `cmd/integrity-checker/main.go` validates config +
prints banner + exits 0. Real wiring (pgx, real cycle-12 `load_aggregate`
via FFI or sibling service, ticker loop with per-reality scheduling, graceful
shutdown, /healthz + /readyz + /metrics) lands alongside cycle-16+ live
publisher wiring (D-PUBLISHER-LIVE-WIRING).

Why ship the entry point + library packages now?
1. The binary is referenced by `infra/k8s/integrity-checker-cronjob.yaml`
   (cycle-15 L3.F.3) and the Prometheus alerts (L3.J.2) — without the
   library packages, those manifests dangle.
2. CI smoke (`go build ./...` + `go test ./...` per `verify-cycle-15.sh`)
   catches API/wiring drift early.
3. The sampler/comparator/state_writer packages have full unit-test
   coverage with in-memory fakes; they don't need main to be a long-running
   daemon to validate correctness.

## Cross-cycle contracts

- **cycle 13** `projection_drift_state` table — STATE TARGET. The
  `state_writer` package emits UPDATEs here. Allowlist of 10 L3.A
  projection tables enforced by the `CHECK` constraint.
- **cycle 13** `VerificationMeta` cols on every L3.A row
  (`event_id`, `aggregate_version`, `applied_at`,
  `last_verified_event_version`, `last_verified_at`) — the comparator reads
  `event_id` + `aggregate_version` to determine which events to replay for
  the sample.
- **cycle 12** `dp-kernel::load_aggregate` — comparator's
  `AggregateLoader` interface is the Go-side projection of the Rust
  function (same 3-path algorithm: snapshot exists / cold replay /
  snapshot + delta). Live wiring deferred.
- **cycle 11** worker skeleton — `cmd/integrity-checker/main.go` mirrors
  `services/archive-worker/cmd/archive-worker/main.go` shape.
- **cycle 13** `scripts/projection-drift-check.sh` — REPLACED by this
  service. Skeleton script remains for reference/dev-debugging only; the
  cycle-13 cron skeleton is now obsolete (this service is the
  authoritative L3.E/F implementation per the layer plan).

## Packages

| Package | Responsibility |
|---|---|
| `pkg/types` | shared types: `SampleResult`, `DriftReport`, `TableConfig` |
| `pkg/config` | YAML config loader (`contracts/integrity/config.yaml`) |
| `pkg/sampler` | picks N random aggregates per projection table |
| `pkg/comparator` | re-derives expected state via `AggregateLoader`, diffs against projection row |
| `pkg/state_writer` | UPDATEs `projection_drift_state` rows |
| `pkg/daily_loop` | orchestrator for daily sampling mode |
| `pkg/full_check` | orchestrator for monthly full-scan mode (cursor batching) |
| `pkg/metrics` | emits `lw_projection_lag_seconds`, `lw_projection_drift_count`, `lw_projection_check_*` metrics |
