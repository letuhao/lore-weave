# Spec — Structural perf-shape gate (catch higher-layer perf regressions the statistical gate can't see)

- **Date:** 2026-06-15
- **Phase:** CLARIFY → DESIGN (this doc is the CLARIFY artifact; **not** yet planned/built)
- **Size (provisional):** L (6+ files: new gate harness + conformance cases + CI wiring + bites). Reclassify at PLAN if it grows.
- **Branch:** `mmo-rpg/foundation-mega-task`
- **Origin question (user, 2026-06-15):** *"Should we add a gate to avoid higher layer break performance?"*

---

## 1. Problem statement

In a layered event-sourcing spine — kernel append → outbox → relay → projection rebuild,
with Go meta / Python AI / TS gateway as the layers *above* the Rust kernel — a change in a
**higher layer** can silently regress the performance of the **lower** hot path. The classic
shape is **not** a constant-factor slowdown; it is an **algorithmic / structural** regression:

- a service or gateway caller turning an O(1) append into O(N) (a per-subscriber `INSERT`
  loop instead of one outbox row),
- a synchronous fan-out added on the append path,
- a per-event network round-trip,
- a projection `apply` that does work proportional to history length.

These surface only at scale, and only as *shape* changes (slope), not as a fixed Δµs.

## 2. What already exists (do NOT rebuild)

The foundation already has a **statistical micro-benchmark regression gate** — this spec must
*complement*, not duplicate, it:

| Asset | What it does | Where |
|---|---|---|
| **S7/F2 benchstat gate** | Mann-Whitney U @ α=0.05 over Go micro-benchmarks; **same-runner A/B** (`--ci-ab <base>`) so it is machine-independent; ships a `--bite` non-vacuity proof. | `scripts/perf/bench-gate.sh` |
| **CI wiring** | Runs **per-PR** (`perf-micro-bench` job): `--bite` must fire, then `--ci-ab` fails on a significant `sec/op` regression vs the PR base. | `.github/workflows/conformance-ci.yml:140-172` |
| **Bencher path (F5)** | Cross-language perf time-series + threshold alert (self-hosted). Validation-only today. | `scripts/perf/bencher-gate.sh` |
| **W4.2 T0/T1 micro-bench** | **Relative** gate `T1p50 < T0p50` (outbox tick cheaper than event tick), reuses production SQL verbatim, has a 200k-row bite. | `tests/workload-gen/internal/emit/microbench.go` |
| **W4.1 USL fitter** | Fits the Universal Scalability Law (contention γ, coherency, Nmax) to a concurrency sweep; recovery unit-tested without an N=1 anchor. | `tests/perf/usl/usl.go` |
| **W4.3 recall gate** | pgvector HNSW recall@10 ≥ 0.90 (a *floor*, not a speed threshold) with an ef_search bite. | `scripts/perf/w4-pgvector-recall.sh` |

### The gap (this spec's thesis)

The S7/F2 gate benchmarks exactly **three contract-layer leaf functions** —
`BenchmarkEventMarshal`, `BenchmarkEventUnmarshal`, `BenchmarkEnvelopeValidate`
(`tests/perf/bench/event_bench_test.go`). Therefore:

1. **No benchmark exercises the spine hot path** (append → outbox → projection apply) or any
   higher-layer caller of it. A higher layer can regress the spine without moving any of the
   three benchmarked numbers → the gate is *non-vacuous but narrow*.
2. **benchstat catches constant-factor regressions, not structural ones.** Even if we added a
   wall-clock benchmark over the layered path, a Mann-Whitney over CI wall-clock only fires
   when the regression is large enough to clear the runner noise floor — an N+1 that is cheap
   at the benchmark's small N slips through, then explodes at production scale.

> **Conclusion:** the missing gate is **structural** — machine-independent invariants on the
> *shape* of the hot path (statement count, scaling exponent), not another wall-clock threshold.
> This is the same discipline W4.2/W4.3 already chose (relative/floor gates, never absolute µs).

## 3. Proposed gates (all bite-testable, none wall-clock-absolute)

### G1 — Statement-shape invariant on the spine write path  *(per-PR, deterministic)*

Appending **one** event emits **exactly** 1 `events` INSERT + 1 `events_outbox` INSERT,
**independent of** the subscriber/fan-out count N and the payload size. Assert the *count and
identity* of statements issued, not their latency.

- **Mechanism:** extend the W4.2 microbench seam (it already reuses `insertEventsSQL` +
  `events.OutboxInsertSQL`) to count statements per append over a workload swept across
  fan-out N ∈ {0,1,8,64}. Pass ⟺ count is constant in N.
- **Bite (must fail):** an implementation that loops a per-subscriber outbox INSERT → count
  grows with N → gate fires. *(A gate that can't tell 1 from N is vacuous.)*
- **Open:** statement-count can be measured via a counting `sql.Driver` wrapper, or via PG
  `pg_stat_statements` / a session `log_statement` capture. Decide at DESIGN (the driver
  wrapper is hermetic and CI-friendly; pg_stat needs the live rig).

### G2 — Scaling-exponent band from the USL fitter  *(nightly, live rig)*

Over the existing concurrency sweep, assert the **fitted shape** stays sub-linear within a
band — e.g. the USL contention coefficient γ and/or an empirical complexity exponent
`p = d log(time) / d log(N)` stays ≤ `1 + ε`. Ratios across N on the **same run** → immune to
absolute machine speed.

- **Mechanism:** reuse `tests/perf/usl/usl.go`; add a band assertion over the fitted/observed
  exponent.
- **Bite (must fail):** feed a deliberately super-linear series (the USL test already
  synthesizes known-coefficient series) → exponent exits the band → gate fires.
- **Open:** band width ε and which coefficient to gate on (USL γ vs raw log-log slope). Needs
  a short empirical calibration on the scale rig so the band is tight enough to bite a real
  N+1 yet loose enough not to flag rig noise.

### G3 — Extend the benchmarked surface so the *existing* S7 gate covers the hot path  *(per-PR)*

Add micro-benchmarks over the genuinely hot, higher-layer-reachable functions so the already-
wired `--ci-ab` gate protects them: projection `apply_one` per arm, the rebuild
`build_stmt` SQL construction, envelope/event hashing (W3.4 `content_sha256`). This is the
cheapest, highest-leverage slice — it makes the *existing* mechanism guard the layer that
matters, with zero new gate code.

- **Bite:** already provided by the existing `BenchmarkPerfGateBite` + `--bite` mode; new
  benchmarks inherit the same non-vacuity harness.

## 4. Non-vacuity contract (per project discipline)

Every gate above ships with a bite that makes it **fail on demand**:
G1 → per-subscriber loop; G2 → super-linear series; G3 → `LW_PERF_BITE=1`. No gate is
committed without a demonstrated red. A gate that cannot be made to fail is deferred with a
rationale row, not shipped green.

## 5. Explicit non-goals

- **No absolute wall-clock thresholds** in CI (runner variance → flaky/vacuous; this is the
  S7 review HIGH-2 lesson, already encoded in `bench-baseline.txt` being informational-only).
- **No replacement** of the S7/F2 or Bencher paths — purely additive.
- **Not** a full distributed load test (that is the nightly hyperfine/k6 battery's job).

## 5a. CLARIFY decision (2026-06-15, human)

- **Scope:** ALL THREE gates — G1 (statement-shape) + G2 (USL exponent band) + G3 (extend
  benchmark surface). Maximal slice, consistent with the "build everything possible" cadence.
- **Workflow mode:** default v2.2 (no AMAW); `/review-impl` on plan + impl as usual.
- Open questions Q1 (scope) resolved above; Q2/Q3/Q4 resolved at DESIGN (see plan doc).

## 6. Open questions for the human (CLARIFY checkpoint)

1. **Scope for the first slice** — all three (G1+G2+G3), or start with **G3 + G1** (both
   deterministic/per-PR, cheapest, highest leverage) and defer G2 (needs live-rig
   calibration)? *Recommendation: G3 + G1 first; G2 as a fast-follow once the band is
   calibrated.*
2. **G1 measurement mechanism** — hermetic counting-driver wrapper (per-PR, no live PG) vs
   `pg_stat_statements` on the scale rig (live, truer but heavier)? *Recommendation: counting
   driver for the per-PR gate; optional live cross-check in nightly.*
3. **Which higher-layer caller(s) to instrument for G1** — kernel append only, or also a
   representative real caller (`world-service` rebuild writer, `game-server` event path)?
4. **AMAW?** This touches a CI gate (load-bearing-ish) but no schema/security boundary —
   default v2.2 is fine unless you want the cold-start sub-agent reviews.

---

## 7. Acceptance criteria (draft — finalize at PLAN)

- [ ] At least G3 + G1 implemented, each with a demonstrated bite (red → green).
- [ ] G1 gate is machine-independent (counts/shape, not µs) and runs per-PR.
- [ ] New conformance catalog case(s) for each gate; catalog count rises.
- [ ] CI wired (per-PR for deterministic gates; nightly for G2 if included).
- [ ] SESSION_HANDOFF + DEFERRED updated; any deferred gate (e.g. G2) has a tracked row.
