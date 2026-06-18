# S12 — Architecture scale-validation — implementation plan

Spec: `docs/specs/2026-06-14-S12-architecture-coverage-scale.md`. Size **L–XL**. 5 increments, batch
cadence (autonomous → one POST-REVIEW → push-ask). `/review-impl` on this plan first.

## Guiding constraints (carried from 3 review rounds)
- **The wall is the SHARED aggregate paths, not per-node throughput (round-3 MED-1/2).** Session ≈10
  participants @ ~10/s; a heavy reality ≈ 50 small sessions @ ~500 T2/s on one shard = trivial for PG. So
  per-node/per-session are modest; **A3 (shared-path β) is the centerpiece**, A1/A2 are supporting.
- **Single-box trap (round-1 HIGH-1 / round-3 MED-4):** every shared path runs on a **dedicated vCPU set**
  (`--cpuset-cpus`; on WSL2 this isolates logical vCPUs, not physical P-cores — still gives guaranteed
  headroom) and its **OWN CPU + bottleneck type** (lock/serial vs CPU-bound) is recorded — else the
  refactor verdict is a CPU-starvation artifact.
- **Honest numbers:** `fsync`/`synchronous_commit` at production semantics; per-node α from an ISOLATED
  shard (not N-shards-sharing-one-NVMe); V3 is **extrapolated lower-bound**, never certified (Phase-2).
- **Reuse:** S7 `tests/perf/usl`, `tests/workload-gen`, publisher, `tests/conformance`, S6/S8 harness.
  New = the multi-shard rig + the roleplay load-skeleton.
- **L1 coverage is NOT here** — it's S13 (round-3 MED-3).

## Increment 1 — Multi-shard rig + per-node packing + pgbench cross-check (A1) `[FS]`
- `infra/scale/docker-compose.scale.yml`: N Postgres instances (real shard hosts) + Redis + toxiproxy,
  sized to the box (start N=8, RAM-bounded), with `--cpuset-cpus` reserving a vCPU subset for the shared
  writers (used in Inc-2) vs the shard fleet. PG at production `fsync`/`synchronous_commit`.
- `scripts/perf/scale-rig.sh`: spread realities across N shards via wg (real cross-shard → closes
  `D-WORKLOAD-GEN-REAL-SHARD`); a publisher-per-shard fleet drains.
- **Per-node PACKING ceiling (not a throughput hunt):** one ISOLATED shard → how many realities at the
  DP-S5 per-reality rate (~500 T2/s + 50 T3/s) before it knees; record host + shard CPU/IO.
- **pgbench cross-check:** `pgbench -f` custom event-INSERT script vs one shard → raw-PG ceiling; contrast
  vs the rig end-to-end → spine overhead-over-raw-PG.
- **Bite:** throttle a shard (latency toxic) → measured packing capacity drops → proves it measures the
  real path.

## Increment 2 — SHARED-path β (THE CENTERPIECE) (A3) `[FS]`
- Each shared path **cpuset-isolated (dedicated vCPU set) with its OWN CPU recorded** (HIGH-1):
  - **meta-worker (sole cross-reality writer, I7):** drive xreality fan-out from many shards → ceiling vs
    aggregate DP-S5 T3 ≤50k/s; classify **serial-capacity (Amdahl — bigger node helps)** vs **coherency-β
    (retrograde — needs re-design)** by whether its own cores are idle (lock-bound) or saturated.
  - **Redis pub/sub fan-out** sharded by reality (DP-A7): T1 broadcast load → fan-out ceiling.
  - **reality_registry (meta DB):** provision/route read+write load.
  - (event-handler / I6 cross-session = OUT, not built.)
- Output per path: isolated ceiling + OWN CPU + shape → "scales horizontally" vs "coherency wall
  (refactor risk)".
- **Bite:** remove the sharding key (un-shard the fan-out) → ceiling worsens measurably → proves
  sensitivity to the coherency design, not noise.

## Increment 3 — roleplay skeleton: I6 correctness + latency (A2 — NOT a scaling test) `[FS]`
- `services/roleplay-service/` **Cycle-0 LOAD-SKELETON** (loud header banner like `travel-service`, so it
  isn't mistaken for the real service — round-1 LOW-2): one command-processor/session, mocked LLM, emits
  `turn.*`/`npc.*`/`pc.*` through the kernel at the REAL per-session rate (~10 T2/T3/s, session ≤10).
- `scripts/perf/roleplay-load.sh`: many small sessions + a hot reality (~50 sessions on one shard) →
  assert **per-session serial-FIFO holds** + p99 **data-plane** ack vs DP-T3 <50 ms (LLM mocked, NOT
  user-perceived — LOW-3). This validates the I6 *concurrency assumption*, not a throughput wall.
- **Bite (MED-2):** mis-route so two processors handle ONE session concurrently → the session's event
  stream shows out-of-order / version drift → proves the I6 routing/serialization holds correctness (NOT
  a re-test of `append_events` CAS — that's S10).

## Increment 4 — soak + lag metric (A4, closes `D-S7-SOAK-LAG-METRIC`) `[BE]`
- Emit `lw_projection_lag_seconds` (+ outbox depth, Redis stream length, RSS) from the rig.
- **Soak can't be time-compressed (LOW-B):** a short **leak-smoke** (minutes, CI-able) + a longer
  **manual soak** (real wall-clock hours, dispatch) → assert lag/depth/RSS stay flat (no leak/backlog).
- **Bite:** throttle the publisher below the emit rate → lag MUST trend up → proves the detector bites.

## Increment 5 — multi-shard DR + scale-readiness report + CI + SESSION (C1) `[FS]`
- Close `D-S8-MULTI-SHARD-DR`: N-shard restore-together drill (whole-system DR).
- **`docs/specs/2026-06-14-S12-scale-readiness-report.md`:** per-node packing + pgbench overhead; per
  shared path the isolated ceiling + OWN CPU + **shape (serial vs β)**; **uniform-USL curve vs skew
  saturation-point** (LOW-A); **V3 extrapolation as a lower-bound + residual-unknowns list**; **Phase-1
  (this) vs Phase-2 (`D-S12-MULTI-HOST`)** framing; ranked **refactor-risk list** with evidence.
- Conformance cases (CPU/stack-gated) + a `scale-nightly` CI job (small sweep; full sweep manual/dispatch
  given weight). SESSION_PATCH + memory + remember; close the deferred rows; note **S13 = L1 coverage**.

## Risks
- **R1 box ≠ V3 absolute** → expected; the verdict is the α/β split + extrapolation lower-bound; Phase-2
  certifies. Stated in the report.
- **R2 box-saturation masquerading as a β-wall** → the single most important guard: dedicated vCPU set +
  OWN-CPU + bottleneck-type for every shared path (Guiding constraints).
- **R3 roleplay skeleton fidelity** → validates the I6 *concurrency assumption* + event path, not game
  logic or routing infra (event-handler unbuilt); stated.
- **R4 N PG on one NVMe / RAM** → per-node α from ONE isolated shard; size N to 96 GB (start 8, tune).
- **R5 WSL2 cpuset** → isolates vCPUs not physical P-cores; sufficient for the headroom guarantee HIGH-1
  needs; documented as a caveat. If isolation proves leaky at dev time, fall back to running the shared
  writer natively on Windows with affinity (record it).
