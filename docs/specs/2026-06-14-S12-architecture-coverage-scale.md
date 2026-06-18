# S12 — Architecture scale-validation (shared-path centric)

**Slice:** S12 — a NEW post-test-plan slice. Goal: turn "kiến trúc có scale được tầng L4–L7 không?"
from *assumption* into *data* — focused on the ONE place it can actually break.
**Date:** 2026-06-14 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** L–XL (re-scoped down from XL).
**Anchors:** scale/SLOs `docs/03_planning/LLM_MMO_RPG/06_data_plane/08_scale_and_slos.md` (DP-S1..S8);
per-session rates `…/07_failure_and_recovery.md`; tier model `03_tier_taxonomy.md`; I6 invariant `00_foundation/02_invariants.md`.
**CLARIFY:** scale-validation · roleplay load-skeleton now · target **V3 scaled to one box**
(i9-13900K / 96 GB / RTX 4090 / 980 PRO) → measure what the box sustains, fit USL, extrapolate.
**L1/core coverage (the old Track B) is split out to S13** (review round-3 MED-3) — unrelated to scale,
separable, and combining bloated this slice.

---

## 1. The cardinality that reshapes everything (review round-3 MED-1)

A **session ≈ 10 participants** (`session_max_total=10`) at **~10 T2/T3 writes/s, ~100 T1/s, ~200 reads/s**
(`07_failure_and_recovery.md`). A **heavy reality = 200–500 players = ~20–50 SMALL sessions**, not one
mega-session. So:
- The **single-command-processor-per-session (I6)** is bounded SMALL (~10/s) → it is **NOT a scaling
  wall**; it is a **correctness** mechanism (serial FIFO per session). Testing a "500-player session" is
  testing a scenario that cannot exist.
- A heavy reality's shard does ~500 T2/s + ~50 T3/s — **trivial for one Postgres** → the **per-reality
  shard is NOT a wall** either.
- The **sharded path is embarrassingly parallel at these modest rates.** Therefore the scale question
  reduces almost entirely to: **(a) the AGGREGATE SHARED paths every reality contends on, and (b) how many
  realities one node/shard can pack.**

## 2. Where scale actually breaks — the centerpiece

| Path | Type | Scales by | This slice |
|---|---|---|---|
| event log / outbox / projection (per reality, ~500 T2/s) | **SHARDED, modest** | add shards/nodes | A1 = *packing* (how many realities/shard), not a throughput hunt |
| **Redis T1 pub/sub fan-out** (DP-S5 ~200k/s realistic peak, sharded by reality DP-A7) | **SHARED** | sharded pub/sub | **A3 — centerpiece** |
| **meta-worker = sole cross-reality writer (I7)** | **SHARED single-writer** | bigger writer node OR re-shard the writer | **A3 — centerpiece (highest risk)** |
| **reality_registry (meta DB)** — every provision/route touches it | **SHARED read/write** | replicas/cache | **A3** |
| event-handler = sole cross-session writer (I6) | SHARED single-writer | — | **OUT (NOT built)** — round-1 MED-3 |

**Two ceiling shapes — do not conflate (round-1 LOW-1):** a single-writer that hard-serializes → a
**serial-capacity ceiling (Amdahl, fixed)** — relieved by a bigger writer node / re-sharding; USL **β
(coherency, retrograde)** → adding load makes it *worse* — needs an architecture change. The report says
which shape each shared path has, because the fix differs.

**The single-box trap — the methodological linchpin (round-1 HIGH-1).** A shared single-writer
(meta-worker) is ONE process on the SAME box as the shard fleet, so its apparent ceiling can be the
process being **CPU-starved by the fleet**, not a real limit. Host-level CPU headroom does NOT
disambiguate. So every shared path is measured with:
1. a **dedicated vCPU set** (Docker `--cpuset-cpus`, a non-shared core subset — note: on Docker
   Desktop/WSL2 this isolates *logical vCPUs*, NOT guaranteed physical P-cores; the goal is guaranteed
   headroom, which vCPU isolation gives — round-3 MED-4);
2. its **OWN CPU at the plateau** + the **bottleneck type** (blocked on lock/serialization → real
   architecture ceiling, a bigger node does NOT help; vs saturating its own cores → per-process ceiling,
   a bigger node DOES help).
Without (1)+(2) the refactor-risk verdict could be measuring a starved process, not the architecture.

## 3. Method: V3 measured on one box

- **Per-node packing & ceiling (A1):** measure a single ISOLATED shard's reality-capacity at the DP-S5
  per-reality rate (≈500 T2/s + 50 T3/s) — "how many realities before this shard knees" — NOT a raw
  throughput hunt (rates are modest). Keep `synchronous_commit`/`fsync` at **production semantics** (off =
  inflated fiction); record the exact PG config.
- **Industry cross-check (round-2 #2):** `pgbench -f` with a custom event-append INSERT script vs one
  shard → a comparable raw-PG ceiling; contrast vs the rig's end-to-end → **spine overhead over raw
  Postgres** (a number reviewable against the wider world). YCSB = heavier alt, deferred.
- **Shared-path β (A3, the centerpiece):** drive many shards' cross-reality / fan-out load at the
  cpuset-isolated shared writers; find each ceiling + its shape (serial vs β) while watching its OWN CPU.
- **USL:** the **uniform** sweep over shard/node count → an X(N) curve → α + Nmax. The **skew** run is a
  **single-reality / hot-shard saturation POINT** (~50 sessions on one shard), NOT a USL-N curve
  (round-3 LOW-A) — report it as a point vs the DP-S5 per-reality target.
- **Extrapolate to V3 as a LOWER-BOUND, not a proof (round-1 MED-4):** verdict = "no wall found up to
  N=X (the box's reach), extrapolated headroom Y"; list large-N-only bottlenecks one box CANNOT surface
  (Redis cluster reshard, meta-DB connection ceilings, real network fan-out) as residual unknowns.
- **Two-phase framing (round-2 #3):** S12 = **Phase 1 (pre-prod, single-box, cheap)** — finds the
  architecture/coherency walls + a USL lower-bound. **Phase 2 (`D-S12-MULTI-HOST`, real cluster + prod
  observability, cloud/$)** *certifies* absolute V3. Phase-1 must never be read as a V3 certification.
- **LLM is mocked** in roleplay — measure the data-plane ceiling, not provider latency.

## 4. Scope (Track A scale + Track C report)

- **A1 — per-node packing + cross-check.** Multi-shard rig (N PG instances; real cross-shard — closes
  `D-WORKLOAD-GEN-REAL-SHARD`). One ISOLATED shard: realities-per-shard at DP-S5 per-reality rate → the
  packing ceiling. + the pgbench cross-check. Bite: throttle the shard (latency toxic) → measured capacity
  drops → proves it measures the real path.
- **A2 — roleplay skeleton: I6 CORRECTNESS + latency (NOT a scaling test).** Minimal roleplay-service
  (one command-processor/session, LLM mocked) emitting `turn.*`/`npc.*`/`pc.*` through the kernel at the
  REAL per-session rate (~10 T2/T3/s, session ≤10). Assert: per-session **serial FIFO** holds + p99
  **data-plane** ack vs DP-T3 <50 ms (LLM mocked, NOT user-perceived — round-1 LOW-3). Bite (round-1
  MED-2): mis-route so two processors touch ONE session → out-of-order/version drift → proves the I6
  serialization is what holds correctness (NOT a re-test of kernel CAS). Validates the I6 *assumption*,
  not routing infra (event-handler unbuilt — round-3 LOW-C).
- **A3 — SHARED-path β (THE CENTERPIECE — where scale actually breaks).** cpuset-isolated, OWN-CPU
  measured: **meta-worker (I7 sole cross-reality writer)** under fan-out from many shards (vs aggregate
  DP-S5 T3 ≤50k/s); **Redis pub/sub fan-out** sharded by reality (DP-A7) at the T1 broadcast rate;
  **reality_registry** under provision/route load. Output per path: ceiling + shape (serial-capacity vs
  coherency-β) + the refactor-risk verdict. Bite: un-shard the fan-out key → the ceiling worsens
  measurably → proves sensitivity to the coherency design, not noise.
- **A4 — soak + lag (closes `D-S7-SOAK-LAG-METRIC`).** Emit `lw_projection_lag_seconds` (+ outbox depth,
  stream length, RSS). Soak **cannot be time-compressed** (round-3 LOW-B): a short **leak-smoke** (CI) +
  a longer **manual soak** (real wall-clock hours) → assert lag/depth/RSS stay flat. Bite: throttle the
  publisher below emit rate → lag MUST trend up.
- **C1 — scale-readiness report** (`docs/specs/2026-06-14-S12-scale-readiness-report.md`): per-node packing
  + pgbench overhead; per shared path the isolated ceiling + OWN CPU + shape; uniform-USL vs skew-point;
  V3 extrapolation as a **lower-bound + residual-unknowns**; **Phase-1 vs Phase-2** framing; a ranked
  **refactor-risk list**. + closes `D-S8-MULTI-SHARD-DR` (N-shard restore-together drill).

## 5. Out of scope (tracked)
- **L1/core coverage → S13** (lifecycle R9 / capacity / migration 6-phase into the conformance+fault
  battery) — the old Track B, separated (round-3 MED-3).
- `D-S12-MULTI-HOST` = **Phase 2** (real multi-node cluster + prod observability; certifies absolute V3).
- Real LLM/provider latency at scale — `D-S12-LLM-LATENCY-AT-SCALE`. T0/T1 micro-latency — `D-S12-T0T1-MICRO`.
- The full roleplay-service (S12 ships only a Cycle-0 load-skeleton).

## 6. Acceptance criteria
- [ ] A1: real cross-shard (N PG instances, `D-WORKLOAD-GEN-REAL-SHARD` closed); per-node **packing**
      ceiling from an ISOLATED shard + pgbench cross-check (spine overhead-over-raw-PG); fsync production.
- [ ] A2: roleplay skeleton asserts **I6 serial-FIFO correctness** + p99 data-plane ack vs DP-T3 at the
      REAL per-session rate (~10/s); the bite tests routing-serialization, not kernel CAS.
- [ ] A3 (centerpiece): shared paths **cpuset-isolated + OWN-CPU measured**; each ceiling + shape
      (serial-capacity vs coherency-β) + refactor-risk verdict; bite fires. event-handler out (unbuilt).
- [ ] A4: lag metric emitted; leak-smoke + manual soak show flat lag; bite fires.
- [ ] C1 report committed — uniform-USL + skew-point + V3 **lower-bound** + residual unknowns +
      **Phase-1/Phase-2** framing + ranked refactor-risk list; `D-S8-MULTI-SHARD-DR` closed.
- [ ] `/review-impl` on the plan AND the impl; findings folded.
