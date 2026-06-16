# S7 — Perf harness: implementation plan

**Plan date:** 2026-06-13 · **Size:** XL · **Spec:** `docs/specs/2026-06-13-S7-perf-harness.md`
**Build order:** Inc 1 (USL, in-toolchain, the load-bearing core) → Inc 2 (micro-bench + benchstat
gate) → Inc 3 (hyperfine wall-clock) → Inc 4 (k6 vs game-server) → Inc 5 (Bencher self-host) →
Inc 6 (conformance cases + runner predicates + CI). Each increment is independently committable;
checkpoints between increments per the human-in-loop cadence.

---

## Inc 1 — USL curve-fitter (F1) · in-toolchain, fully local

**New module** `tests/perf/` (`go.mod` → `github.com/loreweave/foundation/tests/perf`, gonum require).

- `usl/usl.go`:
  - `type Sample struct { N int; Throughput float64 }` — **N = concurrency (parallel workers), not
    event-count** (review HIGH-1). Doc comment states this explicitly so a future rig author can't
    feed a load-size series.
  - `type Fit struct { Gamma, Alpha, Beta, Nmax, Xmax, R2 float64; Degenerate bool }`
  - `func FitUSL([]Sample) (Fit, error)` — (1) Gunther linearization seed (γ re-fit free in step 2,
    so X(1)-sample sensitivity is absorbed — review LOW-5), (2) `gonum/optimize` nonlinear refine,
    (3) project α,β≥0, compute Nmax/Xmax/R². **Degeneracy guard (review MED-4):** `α≥1 || β≤0` →
    `Nmax=+Inf`, `Degenerate=true` (never a silent NaN). Errors on <4 distinct N or non-finite input.
  - `func (Fit) Predict(N float64) float64`.
- `usl/usl_test.go` — **bite tests:**
  - recover known (γ=1000, α=0.03, β=1e-4) from seeded-jitter synthetic samples within tol; Nmax ±N.
  - β=0 linear series → Beta≈0, Nmax=+Inf, Degenerate=true (no hallucinated knee).
  - α>1 super-contention series → Degenerate=true, Nmax=+Inf, **no NaN** (MED-4).
  - degenerate input (<4 N) → error.
- `usl/cmd/usl-fit/main.go` — reads `(N,throughput)` CSV or JSON on stdin / `-in`, writes `Fit` JSON.

**VERIFY:** `go test ./usl/...` green; `echo synthetic | usl-fit` prints recovered coeffs.

## Inc 2 — Per-layer micro-benchmarks + benchstat gate (F2) · in-toolchain

- `tests/perf/bench/`:
  - `eventwrite_bench_test.go` — `BenchmarkEventEncode` over the workload-gen payload marshal path
    (reuse `tests/workload-gen/internal/schema` shapes; no DB — pure CPU encode throughput, L2).
  - `projection_bench_test.go` — projection-apply inner loop (reuse the comparator/replayloader
    apply over a fixed event batch; no DB).
  - `replay_bench_test.go` — replay-aggregate fold over an in-memory event slice (L3.G inner loop).
  - `gate_bite_test.go` — `BenchmarkPerfGateBite` with `LW_PERF_BITE=1` → injects extra work
    (alloc + tiny spin) the benchstat gate must flag vs a clean baseline.
- `scripts/perf/bench-gate.sh` — **same-runner A/B (review HIGH-2)**, two modes:
  - **CI gate mode (`--ci-ab <baseline-ref>`):** in ONE job/runner — `git stash` any dirty state →
    checkout `<baseline-ref>` (merge-base) → `go test -bench=. -count=10 ./bench/... > old.txt` →
    checkout head → same → `new.txt` → `benchstat -format csv old.txt new.txt`. **fail (exit 1)** when
    a CSV row shows a significant regression (`p<0.05`, positive delta beyond the band). Both halves
    run on the same hardware → the p-value is meaningful. Parses **CSV, not the human table**
    (review MED-3); header pins the validated benchstat version.
  - **local-dev mode (default):** `go test -bench` → compare against the committed informational
    baseline, **print drift only, never exit 1** (it's cross-machine — not a gate).
  - **`--bite`:** runs old=clean / new=`LW_PERF_BITE=1` on the SAME process and asserts the gate DOES
    fire (else vacuous → exit 1). Same-machine, so the bite validates the real gate path.
- `scripts/perf/baselines/bench-baseline.txt` — committed **informational local-dev** baseline with a
  `# machine/date — NOT a CI gate input` header (review HIGH-2). The CI gate never reads it.

**VERIFY:** install benchstat (`go install golang.org/x/perf/cmd/benchstat@latest`); confirm
`-format csv` exists on the installed version (pin it); run local-dev mode (prints drift) + `--bite`
(fires); simulate `--ci-ab` against `HEAD` (degenerate same-ref A/B → no regression → pass).

## Inc 3 — hyperfine binary wall-clock harness (F3) · CI-run / notrun local

- `scripts/perf/hyperfine-binaries.sh` — **sweep variable is CONCURRENCY K, not event-count
  (review HIGH-1).** For K in {1,2,4,8,16} parallel workers: each worker emits a FIXED batch
  (events-per-worker held constant), and `X(K) = total_events / aggregate_wall_time`:
  - `wg -emit`: K parallel `wg -emit` processes against one shard DB (DB lock/WAL contention → α,
    cross-worker coherency → β). `hyperfine --export-json` times the whole K-fan-out per K.
  - `replay-aggregate` / `ic`: K parallel runs against K seeded shards (reuse S5's N-shard seeding) —
    these are batch one-shots with no internal concurrency, so K-parallelism IS their concurrency axis.
  Emit the `(K, X(K))` series → pipe into `usl-fit` → `results/perf-usl-<bin>.json`.
- Verdict: hyperfine absent → notrun; <4 K points or fit non-convergent/`Degenerate` → notrun(setup);
  runs + writes artifact → pass. **No threshold asserted** — the artifact IS the deliverable.

**VERIFY (local):** notrun (hyperfine MISSING) — confirm the case reports notrun cleanly. Logic
reviewed by inspection + the usl-fit unit already proven in Inc 1.

## Inc 4 — k6 open-loop generator vs game-server (F4) · CI-run / notrun local

- `tests/perf/k6/http_livez.js` — `constant-arrival-rate` executor, `GET /livez`, threshold
  `http_req_duration: p(99.9)<...` recorded (not gated pre-baseline); summary → JSON.
- `tests/perf/k6/http_matchmake.js` — `POST /matchmake/joinOrCreate/echo` (seat reservation).
- `tests/perf/k6/ws_echo.js` — `experimental/websockets`: matchmake → WS to reserved seat → time an
  `echo` round-trip. If the Colyseus msgpack handshake is too brittle in k6 → Node `@colyseus/loadtest`
  fallback driver (`scripts/perf/colyseus-loadtest.mjs`), recorded as `D-S7-WS-K6-PROTOCOL`.
- `scripts/perf/k6-game-server.sh` — `npm --prefix services/game-server ci && npm run build`;
  boot `LW_WS_ALLOW_DEV_AUTH=1 PORT=2567 node dist/index.js`; wait `/livez`; run the k6 scripts;
  tear down. Verdict: k6 or node absent → notrun; game-server didn't boot → notrun(setup); ran +
  artifact → pass.

**VERIFY (local):** notrun (k6 MISSING). Optionally boot game-server + curl `/livez` to prove the
target wiring (the boot half is node-local).

## Inc 5 — Bencher self-host validation (F5) · resolve §11

- `infra/bencher/docker-compose.yml` — self-hosted Bencher (API + console + its Postgres), isolated
  ports (foundation-dev pattern, `BENCHER_*` overridable). Pin a tag; document the boot.
- `scripts/perf/bencher-gate.sh` — wait for the API; create project/token; `bencher run --project …
  --adapter go_bench --err 'go test -bench=. ./bench/...'`. `--err` = `--error-on-alert`.
- **Decision artifact** `docs/specs/2026-06-13-S7-bencher-selfhost-decision.md` — boots? ingests? CLI
  install friction? Verdict PASS (wire as gate) or NEGATIVE (benchstat stays; `D-S7-BENCHER-DEFER`
  row + §11 marked "validated: self-host impractical because …"). Either way §11 is RESOLVED.

**VERIFY:** `docker compose -f infra/bencher/docker-compose.yml up` boots; record outcome honestly.

## Inc 6 — conformance cases + runner predicates + CI (F6)

- `tests/conformance/internal/runner/runner.go` — add `Provides` cases: `k6`, `hyperfine`,
  `benchstat`, `bencher`, `node` (LookPath each), mirroring the `cargo` predicate.
- Catalog cases (§6 of the spec): `perf-usl-fit` (go-test, no requires — runs everywhere),
  `perf-micro-bench-gate` (requires `[benchstat]`), `perf-hyperfine` (`[hyperfine,foundation-stack]`),
  `perf-k6-game-server` (`[k6,node]`), `perf-bencher-gate` (`[bencher]`).
- `.github/workflows/conformance-ci.yml`:
  - **per-PR:** a `perf-micro-bench` job (Go + `go install benchstat` → `bench-gate.sh`) — fast,
    in-toolchain, gates regressions per commit.
  - **nightly (`perf-nightly`):** install k6 + hyperfine, build binaries + game-server, boot stack,
    run the hyperfine + k6 cases (the heavy live perf battery). `schedule`/`workflow_dispatch` only,
    like the S5/S6 nightly. Bencher job left manual (`workflow_dispatch`) until the §11 decision lands.

**VERIFY (runner-green):** Git-Bash-first on PATH; `go run ./cmd/conformance -catalog ./catalog` →
`perf-usl-fit` PASS, the generator cases NOTRUN (tools absent), nothing FAIL.

## Cross-cutting

- **Provider/language/secrets rules:** perf tooling only; no provider SDK, no model names, no secrets.
  New Go module + Bencher compose creds are dev-only (`bencher/bencher`-style), env-overridable.
- **`language-rule.yaml`:** `tests/perf/` is a test harness (like `tests/workload-gen/`), Go — confirm
  the lint treats it as a non-service test dir (workload-gen precedent).
- **Wiring to CONFIRM at BUILD, not assume (review LOW-7):** (a) game-server has an `npm run build`
  script emitting `dist/index.js` (check `package.json`+`tsconfig` outDir) before relying on it;
  (b) the runner's `go-test` kind vs a generic `["bash","-c","cd tests/perf && go test ./usl/..."]`
  invocation (S6 loom used the generic `bash -c` form — follow that precedent if `go-test` assumes a
  fixed module root); (c) whether a root `go.work` exists that the new `tests/perf` module must join
  (`tests/workload-gen` is standalone — confirm and follow that precedent).
- **Soak (review LOW-6):** the soak skeleton ships secondary-signal collection only and is **NOT**
  registered as a conformance catalog case — it would be a vacuous pass while the `lw_projection_lag_
  seconds` gate is deferred (`D-S7-SOAK-LAG-METRIC`). It lands as a script + a deferred row, nothing more.
- **SESSION + deferred + memory** updated at COMMIT; `/review-impl` on this plan before BUILD and on
  the implementation before COMMIT (standing instruction).
