# S7 — Perf harness + USL saturation rig + statistical regression gate (Technique F)

**Spec date:** 2026-06-13 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** XL
**Parent plan:** `docs/specs/2026-06-04-foundation-runtime-test-plan.md` §8 (Technique F), §11 (open decisions)
**Depends on:** S3 (generator) ✅, S2b/C3 (ledger + replay-aggregate) ✅, S6 (publisher drain, toxiproxy compose) ✅
**CLARIFY decisions (user, 2026-06-13):**
1. Perf surface = spine binaries **+ wrk2/k6 vs game-server** (pull the L4 WS edge into this slice).
2. USL depth = **full curve-fit** (γ/α/β + Nmax, β-coherency *measured*).
3. Bencher = **validate self-host now** (resolve the §11 open decision in this slice).

---

## 0. The governing discipline — "ship a method, baselines are the first output"

Spec §8 is explicit: **"No pass/fail numbers asserted until baselined — F ships a *method*, baselines
are S7's first output."** This is the perf analog of the non-vacuity / bite-test discipline that has
run through S4–S6:

- A perf conformance case must **never** assert an absolute threshold (`p99 < 5ms`) before a baseline
  time-series exists — a fixed-% / fixed-number gate is a *documented anti-pattern* (§8).
- What a perf case asserts instead: **the method ran and produced a baseline artifact**, and — where a
  committed baseline exists — **a statistical regression gate (benchstat / Bencher) is ABLE to fail**
  on a real regression. Each gate ships with a **bite-test** (inject a synthetic regression → the gate
  flags it) exactly as S5/S6 did.
- The USL fitter's bite is **coefficient recovery**: fit synthetic data generated from known
  (γ, α, β) + noise and assert recovery within tolerance — a degenerate fitter that returns constants
  fails the bite.

## 1. Honest scope corrections (from the code survey)

- **The foundation spine has no live HTTP/WS service to wrk2/k6 EXCEPT game-server.** The publisher
  exposes only `/healthz`/`/readyz`/`/metrics` (not a load target). The realistic open-loop HTTP/WS
  target is **`services/game-server`** (Colyseus/TS, PRR-20 second public entry). Per §6.5 it is L4
  "edge (now-ish)", which the user has consciously pulled into S7.
- **game-server has a dev auth path** (`EchoRoom.onAuth`): when `LW_WS_REDIS_URL` is unset it falls
  back to static-token auth — a client joins `echo` with `options.jwt = LOREWEAVE_INTERNAL_TOKEN
  ?? 'dev_token'`. So the load rig needs **no gateway/Redis ticket dance** in dev. (The ticket path
  is exercised by game-server's own edge tests; perf load measures throughput, not the auth crypto.)
- **No perf generator is installed on the dev box** (k6 / wrk2 / hyperfine / benchstat / fortio all
  MISSING; node / npm / cargo / go / docker present). Therefore — exactly like S6's `cargo` predicate
  for loom — every generator-dependent conformance case degrades to **`notrun`** locally via a
  `Provides` predicate and **runs on CI** where the tool installs. The in-toolchain pieces (the Go
  USL fitter, the Go micro-benchmarks, the benchstat gate, the game-server boot) are **fully
  buildable + verifiable locally**.
- **`gonum` v0.17.0 is already a workspace dependency** → the USL nonlinear least-squares fit uses
  `gonum/optimize` rather than a hand-rolled solver.
- **Soak/endurance primary signal `lw_projection_lag_seconds` does not exist yet** (⊕ = unbuilt in
  the plan). S7 ships the soak *method skeleton* (steady-rate driver + the secondary signals that DO
  exist: outbox depth, Redis `XLEN`, RSS) and **defers the lag-metric soak gate** (`D-S7-SOAK-LAG-METRIC`)
  until the metric is emitted. Asserting on a metric the spine doesn't emit would be vacuous.

## 2. Deliverables (what "method shipped" means here)

| # | Deliverable | Tool | Local verifiable? |
|---|---|---|---|
| F1 | **USL curve-fitter** `X(N)=γN/(1+α(N−1)+βN(N−1))` → γ/α/β + `Nmax=√((1−α)/β)` | Go + gonum/optimize | ✅ yes (bite = recover synthetic coeffs) |
| F2 | **Per-layer micro-benchmarks** (event-write, projection-apply, replay inner loop) + **benchstat** Mann-Whitney @α=0.05 regression gate | Go `testing.B` + benchstat | ✅ yes (benchstat go-installable) |
| F3 | **hyperfine binary wall-clock harness** — CLI binaries (`wg -emit`, `replay-aggregate`, `ic`) across a **concurrency** sweep (K parallel workers/shards) → throughput-at-concurrency series feeding F1 | hyperfine | ⛔ notrun locally / CI |
| F4 | **k6 open-loop generator vs game-server** — `constant-arrival-rate` (coordinated-omission-correct) over `/livez` + `/matchmake` (HTTP) + a WS echo round-trip; HdrHistogram p50/p99/p999/p99.9 | k6 | ⛔ notrun locally / CI |
| F5 | **Bencher self-host validation** — self-hosted compose, `bencher run --error-on-alert`; resolves §11 | Bencher (Docker) | partial (boot + ingest locally; decision recorded) |
| F6 | **Conformance cases + runner predicates + CI** — `k6`/`hyperfine`/`benchstat`/`bencher` `Provides`; `perf-nightly` CI job + per-PR micro-bench gate | Go runner + Actions | ✅ runner wiring; generators on CI |

## 3. USL fitting method (F1) — the technically-load-bearing part

**N is CONCURRENCY, not load-size (review HIGH-1).** USL's `X(N)` is throughput as a function of the
**number of concurrent workers/clients** at ~fixed work-per-worker; α (contention) and β (coherency)
are *concurrency-scaling* coefficients. Feeding the fitter a throughput-vs-event-count curve would be
a category error (its "knee" would be per-call overhead amortization, not contention). F3's sweep
variable is therefore **K = parallel workers** (`wg -emit`) / **parallel shard replays**
(`replay-aggregate`/`ic`), each doing a fixed batch; `X(K) = total_events / aggregate_wall_time` at
K = 1,2,4,8,…. Event-count is held fixed *per worker*, never swept as the axis.

The USL is **nonlinear** in (α, β); a naive linear regression cannot fit it directly. Method:

1. **Seed (Gunther linearization).** With γ = X(1), the relative capacity C(N)=X(N)/γ gives
   `N/C(N) − 1 = (N−1)(α + βN)`. For N>1, regress `y = (N/C(N) − 1)/(N−1)` on N (ordinary least
   squares) → intercept α₀, slope β₀. Cheap, closed-form, gives a good starting point. (The seed is
   sensitive to the single X(1) sample — review LOW-5 — so γ is re-fit as a FREE parameter in step 2,
   and the rig averages repeated K=1 samples; the seed quality only affects convergence, not the
   final estimate.)
2. **Refine (nonlinear least squares).** Levenberg-Marquardt / BFGS via `gonum/optimize` minimizing
   Σ(X(Nᵢ) − γNᵢ/(1+α(Nᵢ−1)+βNᵢ(Nᵢ−1)))² over (γ, α, β), seeded from (X(1), α₀, β₀). Constrain
   α,β ≥ 0 (project negatives to 0 — a slightly-negative α from noise is physically 0).
3. **Report.** γ, α (contention), β (coherency), `Nmax=√((1−α)/β)` (peak), `Xmax=X(Nmax)`, plus R²
   goodness-of-fit. **Degeneracy guard (review MED-4):** when `α ≥ 1` or `β ≤ 0`, `(1−α)/β` is
   negative/undefined → report `Nmax = +Inf` (no coherency knee) with `Degenerate: true` rather than
   emitting a silent `NaN`. **β is whatever the data yields** — the spec's hypothesis that β maps to
   projection/replay + Redis-backlog cost is **reported, not asserted**: F3 feeds real measured
   throughput across K, and the fitted β is an *output*, never a hard-coded input.

**Bite (non-vacuity):** `usl_test.go` generates points from known (γ=1000, α=0.03, β=0.0001) with
seeded jitter and asserts the fitter recovers each within tolerance AND Nmax within ±N. Three further
("bite") assertions: (a) a perfectly *linear* series (β=0) → `Beta≈0`, `Nmax=+Inf`, `Degenerate` true
(no hallucinated knee); (b) a super-contention series (α>1) → `Degenerate` true, no NaN; (c) <4
distinct K → error. A stub fitter returning constants fails (a) and the recovery test.

## 4. The statistical regression gate (F2/F5) — how it is ABLE to fail without absolute thresholds

- **benchstat (F2) — SAME-RUNNER A/B, not a committed cross-machine baseline (review HIGH-2).** A
  baseline captured on one machine compared against a different CI runner is a cross-machine diff:
  runner variance + hardware differences make benchstat flag noise as regressions (or force the noise
  band so wide the gate never fires). So the **per-PR gate benches BOTH the merge-base and the PR head
  on the SAME runner in one job**: checkout the baseline ref → `go test -bench` → `old.txt`; checkout
  head → `new.txt`; `benchstat old.txt new.txt`. Same hardware, same run → the p-value is meaningful.
  The committed `scripts/perf/baselines/*.txt` is **informational local-dev only** (a dev can eyeball
  drift on their own box) and is *explicitly not a CI gate input* — it carries a machine/date header
  saying so.
  - **Parse `benchstat -format csv`, pin the version (review MED-3).** benchstat's human table format
    and `-col` semantics changed across versions; grepping the table breaks silently. The gate parses
    the CSV output (explicit delta + `p` columns) and the script header pins the
    `golang.org/x/perf/cmd/benchstat` version it was validated against.
  - **Gate fires** when a CSV row shows a significant regression (`p<0.05`, positive delta beyond the
    band). **Bite:** a `BenchmarkPerfGateBite` with an env-gated (`LW_PERF_BITE=1`) artificial
    allocation+spin; the bite runs old=clean / new=bite on the SAME process → the gate MUST fire
    (same-machine, so the bite validates the *real* gate path, not a cross-machine proxy).
- **Bencher (F5):** self-hosted `bencher run … --err` ingests the same `go test -bench` output as a
  per-commit time-series; `--error-on-alert` fails on a Bencher threshold alert. Per §8 we start with
  `t_test`/`percentage` and **graduate to change-point once a per-commit series exists** (documented;
  not done this slice — there is no multi-commit series yet). **Validation outcome is recorded
  honestly:** if self-host boots + ingests cleanly, Bencher becomes the cross-lang gate and §11 closes
  PASS; if the self-host path proves impractical (license/infra), the slice records a NEGATIVE result
  + keeps benchstat as the working gate + a `D-S7-BENCHER-*` row. "Validate" includes "validated as
  not-worth-it" — that still resolves the open decision.

## 5. game-server load target (F4)

- **Boot (dev):** `npm ci && npm run build && PORT=2567 LW_WS_ALLOW_DEV_AUTH=1 node dist/index.js`
  (no `LW_WS_REDIS_URL` → static-token path; `NODE_ENV` unset so `assertWsAuthConfig` passes).
- **HTTP load:** k6 `constant-arrival-rate` over `GET /livez` (pure transport ceiling) and
  `POST /matchmake/joinOrCreate/echo` (seat-reservation path = the edge-control surface PRR-20
  governs). Percentiles via k6's native `p(99.9)` thresholds (HdrHistogram-equivalent).
- **WS echo round-trip:** k6 `experimental/websockets` script that completes the Colyseus seat
  reservation (POST matchmake → WS to the reserved seat) and times an `echo` round-trip. If speaking
  the Colyseus msgpack room protocol by hand in k6 proves too brittle, **fall back to a Node
  `@colyseus/loadtest` driver** for the WS round-trip and keep k6 for the HTTP surface — recorded as
  `D-S7-WS-K6-PROTOCOL` either way. The WS round-trip is **measured, not threshold-asserted** (no
  baseline yet).

## 6. Layout

```
tests/perf/
  go.mod                       # new module github.com/loreweave/foundation/tests/perf
  usl/usl.go  usl/usl_test.go  # F1 fitter + bite
  usl/cmd/usl-fit/main.go      # CLI: (N,throughput) CSV/JSON → fitted coeffs+Nmax JSON
  bench/*_test.go              # F2 micro-benchmarks (event-write/projection/replay)
  k6/http_livez.js  k6/http_matchmake.js  k6/ws_echo.js   # F4
scripts/perf/
  bench-gate.sh                # F2: go test -bench → benchstat vs baseline (+ --bite)
  hyperfine-binaries.sh        # F3: wall-clock CLI binaries across N → USL input
  k6-game-server.sh            # F4: boot game-server (dev) → run k6 → percentiles
  bencher-gate.sh              # F5: bencher run --error-on-alert (+ self-host boot)
  baselines/                   # committed baseline.txt series (baseline-first)
infra/bencher/docker-compose.yml   # F5 self-host (isolated, foundation-dev pattern)
tests/conformance/catalog/generic/
  perf-usl-fit.yaml            # go-test, in-toolchain, PASS locally
  perf-micro-bench-gate.yaml   # go-test + benchstat (requires:[benchstat])
  perf-hyperfine.yaml          # requires:[hyperfine,foundation-stack]
  perf-k6-game-server.yaml     # requires:[k6,node]
  perf-bencher-gate.yaml       # requires:[bencher]
.github/workflows/conformance-ci.yml  # +perf-nightly job, +per-PR micro-bench-gate step
```

## 7. Verdict conventions (consistent with S6)

- generator/tool absent (`requires:` unmet) → **notrun** (exit ≥2; never flaky-fail).
- baseline absent (first run) → **pass** + writes baseline (informational, gate disarmed).
- statistically-significant regression vs committed baseline → **fail** (exit 1).
- fit failed to converge / too few rate points / game-server didn't boot → **notrun** (setup), not fail.
- USL bite (coefficient recovery) is a **go-test** → always fail-closed on a real break.

## 8. Out of scope / deferred (tracked, not forgotten)

| ID | Item |
|---|---|
| `D-S7-SOAK-LAG-METRIC` | Soak gate on `lw_projection_lag_seconds` — metric not emitted yet; ship skeleton + secondary signals only. |
| `D-S7-WS-K6-PROTOCOL` | Colyseus msgpack WS round-trip in k6 vs `@colyseus/loadtest` fallback — decide at BUILD. |
| `D-S7-BENCHER-CHANGEPOINT` | Graduate Bencher `t_test`→change-point once a per-commit series exists. |
| `D-S7-FORTIO` / wrk2 | k6 chosen as the single open-loop generator; fortio/wrk2 parity deferred. |
| `D-S7-FUZZ-DIRECTION` | §11.1 fuzzing S-slice (syzkaller vs schemathesis) — still roadmap, not S7. |

## 9. Acceptance

- F1 USL fitter recovers synthetic (γ,α,β)+Nmax within tolerance (go-test, local) **and** the β=0
  bite proves it doesn't hallucinate a knee.
- F2 micro-benchmarks run + benchstat gate flags the injected regression bite; clean run passes.
- F3/F4 produce baseline artifacts on CI (notrun locally) — the *method* runs end-to-end.
- F5 self-host decision recorded (PASS→gate wired, or NEGATIVE→benchstat stays + deferred row).
- F6 all perf cases pass through the runner (notrun where tools absent); `perf-nightly` CI job green;
  per-PR micro-bench gate wired.
- No absolute perf threshold asserted anywhere. Baselines committed under `scripts/perf/baselines/`.
