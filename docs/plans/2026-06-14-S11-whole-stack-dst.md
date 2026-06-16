# S11 — Whole-stack DST — implementation plan

Spec: `docs/specs/2026-06-14-S11-whole-stack-dst.md`. Size **XL**. 3 increments, batch cadence
(autonomous → one POST-REVIEW → push-ask). `/review-impl` on this plan first.

## Guiding constraints
- **Two halves, honestly separated:** the local chaos harness is the verifiable, bite-backed deliverable;
  the Antithesis scaffolding is submit-ready but locally provable only as compiles + no-op + runs.
- **Reuse, don't reinvent:** the local harness reuses `scripts/chaos/{toxic.sh, fault-*.sh}` primitives,
  the `foundation-dev` compose, `wg`, the publisher, rebuilder, and integrity-checker (same convergence
  oracle as S5/S8).
- **Zero production-service edits:** Antithesis integration lives entirely in `tests/antithesis/`.

## Increment 1 — local whole-stack chaos-convergence harness  `[FS]`
- `scripts/chaos/whole-stack-chaos.sh`: boot foundation-dev (pg+redis+minio+toxiproxy) → PG + Redis
  proxies → start the **publisher as a PERSISTENT process** draining outbox→Redis through the Redis proxy
  (review MED-1: it must survive/retry the partition, or be restarted after it; the harness confirms it is
  actively draining before asserting) → **sustained workload loop** (N rounds of `wg -emit` through the PG
  proxy; **count successful rounds as the delivery baseline**, tolerate fault-induced rollbacks — review
  LOW-1) → **inject concurrent faults** (pg-slow ∥ redis-partition, staggered, via `toxic.sh`) → clear.
- **PRIMARY oracle — delivery-convergence (review HIGH-1), asserted BEFORE any rebuild:** after the
  partition clears + the publisher drains, assert **no-loss + dedup-able**: `distinct(event_id)` in the
  Redis stream `== events appended` by successful rounds, `XLEN >= events`, outbox pending `== 0`.
- **SECONDARY sanity (acknowledged rebuild-laundered):** C3 (`wg -verify`) + a post-rebuild B
  (ic `drift==0`, all populated tables sampled) + C2 (counts>0). Documented as not fault-sensitive.
- **Bite (review HIGH-2) — targets DELIVERY:** `--bite` `XDEL`s a delivered event from its Redis stream
  after a clean run → the no-loss check (`distinct == events`) MUST fail. (NOT a projection-corruption
  bite — that only re-proves the integrity-checker, already bitten in S5/S8.)
- Verdict: notrun(2: fault-couldn't-inject / publisher-not-draining) / fail(1: delivery or C3 violated) /
  pass(0), matching the S6/S8 scripts.
- Conformance case `tests/conformance/catalog/generic/whole-stack-chaos.yaml` (kind: live-probe,
  requires:[foundation-stack], embeds `--bite`).
- CI: a `whole-stack-dst-nightly` job (schedule/dispatch) — boots the stack, builds the spine binaries,
  runs the drill `--bite`; exit 1 → fail, 2 → notrun.
- **Risk R1 — quiesce flakiness under faults:** bounded `wait_until` on outbox-drained + a fixed
  post-fault settle; on timeout → `notrun` (environmental), never a flaky fail.

## Increment 2 — Antithesis-readiness scaffolding  `[BE]`
- `tests/antithesis/driver/` (Go module, pinned `antithesis-sdk-go`): **shells the spine binaries**
  (`wg`/`pub`/`rebuilder`/`ic`) for an emit→publish→rebuild→integrity cycle — NO reimplemented convergence
  logic (review LOW-2) — and wraps the results in `assert.Always(drift==0, …)`,
  `assert.Sometimes(recovered, …)`, `assert.Reachable(quiesce, …)`, `lifecycle.SetupComplete`. Exits 0/1
  so it is locally runnable; the assertions are inert outside Antithesis.
- `tests/antithesis/docker-compose.antithesis.yml` — test-composer: foundation-dev services + the driver
  as the singleton workload container.
- `tests/antithesis/config/` — singleton-driver layout + metadata.
- `tests/antithesis/README.md` — submission steps, cost note, H2-vs-S1–S10 targeting, and the explicit
  `D-S11-ANTITHESIS-RUN` deferral.
- **Verify locally:** `go build ./...` + `go vet` in the driver module; optionally run it against a booted
  stack (assertions no-op; or `notrun` if no stack at dev time).
- **CI (review LOW-3):** a cheap per-PR `go build` of `tests/antithesis/driver` so the scaffolding can't
  bit-rot while the paid run is deferred.
- **Honesty guard:** the README states plainly that local verification = compiles + inert + cycle-runs,
  NOT "Antithesis found bugs".

## Increment 3 — SESSION + commit  `[FS]`
- SESSION_PATCH.md handoff + deferred rows (`D-S11-ANTITHESIS-RUN`, `D-S11-FULL-APP-STACK`); memory +
  `.remember`. **Declare the S1–S11 battery COMPLETE** (the test-plan arc closes).
- Single commit; `/review-impl` on the impl before commit; push only on explicit approval.

## Risks
- **R1** quiesce flakiness → bounded waits + notrun-on-timeout (above).
- **R2** Antithesis SDK availability/API drift → pin the `antithesis-sdk-go` version; keep the driver tiny
  so an API change is a one-file fix.
- **R3** readiness half is not bug-finding-verifiable locally → mitigated by scoping it as scaffolding +
  the README honesty guard + the `D-S11-ANTITHESIS-RUN` deferral (no overclaim).
- **R4** full-stack compose heaviness in CI → the nightly job boots only the foundation-dev infra + spine
  binaries (not the app fleet), same as the S8 recovery-nightly.
