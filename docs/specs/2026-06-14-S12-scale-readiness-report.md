# S12 — Scale-readiness report (Phase 1, single-box)

**What this answers:** "Will the foundation scale the L4–L7 layers, or will scaling
force a from-scratch refactor?" — turned from assumption into **measured data** on
one box (i9-13900K / 96 GB / RTX 4090 / 980 PRO; Docker Desktop on WSL2), per the
S12 spec (`2026-06-14-S12-architecture-coverage-scale.md`).

**Bottom line:** the per-shard / per-session paths are **not** walls; they scale
with concurrency and clear the DP-S5 per-reality rates with headroom. **One real
architectural ceiling was found** — the I7 single cross-reality consumer — and it
has a **cheap, non-structural fix**. No from-scratch refactor is indicated; one
targeted change (batch the meta-worker XACK) is.

---

## 0. Honesty rails (read first)

- **Phase 1, not a certification.** Every number here is measured on ONE box and
  is an **extrapolated lower bound**, never an absolute V3 throughput. Absolute V3
  is certified only by **Phase 2** (`D-S12-MULTI-HOST`: real multi-node cluster +
  prod observability, cloud/$).
- **Production durability.** Every Postgres shard ran `fsync=on`,
  `synchronous_commit=on` (asserted at runtime; the rig refuses an async run). An
  `fsync=off` ceiling would be inflated fiction.
- **Single-box trap guarded.** Each shared writer ran on a **dedicated vCPU set**
  (`--cpuset-cpus`) with its **OWN CPU recorded**, so a "ceiling" is attributed to
  the architecture, not to a CPU-starved process. On Docker Desktop/WSL2 cpuset
  isolates *logical vCPUs*, not guaranteed physical P-cores — sufficient for the
  headroom guarantee, noted as a caveat.
- **Non-vacuity.** Every measurement ships a bite (a real degradation that MUST
  move the number); a measurement whose bite did not bite is reported as such, not
  dressed as a pass. Two measurements self-caught their own vacuity during BUILD
  (the Redis read-amp timing was exec-overhead-bound; the meta-worker host run was
  WSL2-loopback-bound) and were corrected before any verdict rode on them.

---

## 1. Per-node packing — the per-shard path is NOT the wall (Inc-1)

A single ISOLATED shard (cpuset 0–3, fsync on), pgbench raw event+outbox INSERT
(the spine T2 write shape), concurrency sweep:

| N (clients) | throughput (ev/s) | shard OWN CPU |
|---|---|---|
| 1 | ~410 | ~11% |
| 2 | ~440 | ~15% |
| 4 | ~900 | ~22% |
| 8 | ~1770 | (rising) |

- **Throughput rises with concurrency; no coherency knee** up to the box's reach at
  these rungs (own CPU still climbing, no retrograde). The shard is contention-
  light at the DP-S5 per-reality write rate (~500 T2/s + ~50 T3/s).
- **Raw-PG packing upper bound** ≈ ceiling / 550 ev/s per reality. At ~1770 ev/s on
  4 vCPUs that is only ~3 realities — but that is a **lower-bound artifact of a tiny
  4-vCPU cpuset + a short window + fsync**, not a coherency wall: the curve had not
  kneed. Scaled to a real shard node and higher concurrency this climbs; the point
  proven is **the per-shard write path scales with added concurrency** (Amdahl-
  linear region), so packing is solved by **adding shards/cores**, the cheap axis.
- Real cross-shard verified across **3 distinct Postgres instances** (closes
  `D-WORKLOAD-GEN-REAL-SHARD`).
- **Bite:** a latency toxic on the shard dropped measured throughput 901 → 26 ev/s
  — the sweep rides the real shard path.
- **Spine-vs-raw:** the wg CLI emit floor is spawn-bound and NOT a per-event
  overhead figure; the clean spine ceiling is the Inc-3 long-lived skeleton.

## 2. The shared aggregate paths — where scale actually breaks (Inc-2, centerpiece)

Each shared path cpuset-isolated, OWN-CPU recorded, classified serial-capacity
(Amdahl — bigger/faster node or pipelining helps) vs coherency-β (retrograde —
needs re-design):

| Shared path | Ceiling (this box) | OWN CPU | Shape | vs target |
|---|---|---|---|---|
| **meta-worker (I7 sole xreality consumer)** | **~22k msgs/s** | ~62% of 1 core | **serial-capacity** (flat across batch 50→1000 AND GOMAXPROCS 1→4; bound by per-message XACK RTT) | **BELOW** DP-S5 aggregate T3 ≤50k/s ⇒ **refactor-risk** |
| reality_registry (meta DB route+provision) | ~3,000 ops/s (write-mixed; route-reads far higher) | meta-pg ~383% (≈4 cores) mid-run | serial/IO under write mix | route-reads not a near-term wall |
| Redis fan-out per-reality sharding (DP-A7) | sharding gives **~18× read-amp benefit** (read one reality's history: 260 ms sharded vs 4745 ms over a 200-reality mega-stream) | — | the sharding **key** is load-bearing | sharded design validated |

**Bites:** meta-worker 8031 → 186 msgs/s under a Redis latency toxic; registry
2965 → 151 ops/s under a meta-DB latency toxic; un-sharding the fan-out inflated the
per-reality read >2× — all three ride their real paths.

### THE finding (ranked #1 refactor-risk)

A **single I7 meta-worker drains ~22k xreality msgs/s, below the aggregate DP-S5
T3 target (≤50k/s).** Because I7 mandates a *single* consumer (cross-tenant blast
radius), this is a genuine ceiling. Its shape is **serial-capacity, not coherency-
β**: throughput is flat across batch size and core count, with the consumer at only
~62% of one core — i.e. it is bound by the **per-message `XACK`** in
`services/meta-worker/pkg/consumer/consumer.go` (each message acked in its own
round-trip), not by a retrograde lock. **Mitigations, cheapest first:**

1. **Batch the `XACK`** across the `ProcessOne` batch (one `XACK` with N ids
   instead of N calls) — a small, local change, no architecture change; expected
   multi-× gain.
2. Faster core (serial-capacity ⇒ a bigger node helps).
3. If still short, run **one consumer per xreality topic** (the topics are few and
   fixed) — preserves I7 (single consumer *per stream*) while parallelizing.

None of these is a from-scratch refactor; #1 is a focused fix. **No structural
re-architecture is indicated by Phase 1.**

> **UPDATE — finding RESOLVED (mitigation #1 applied + re-measured).** Batched the
> XACK in `consumer.ProcessOne` (one `XACK` per stream per batch instead of one per
> message; `MessageSource.AckBatch`). Re-measured on the same rig: the single I7
> consumer went **~22k → ~230k msgs/s (~10×)** — now **4.5× ABOVE** the DP-S5
> aggregate T3 target (≤50k/s). The bite still fires (225k → 39k under a +5ms Redis
> latency toxic). The serial-capacity diagnosis is confirmed: removing the
> per-message round-trip lifted the ceiling without touching the I7 single-consumer
> design. Mitigations #2/#3 are no longer needed on this box.

## 3. I6 session concurrency — correctness holds (Inc-3)

The I6 command-processor-per-session is a **correctness** mechanism, not a scaling
wall (a session is ~10 participants @ ~10 T2/T3 writes/s). Load skeleton: 50 small
sessions on one shard (a hot reality), each one processor:

- **Serial FIFO held** for every session (contiguous version sequence 1..M).
- **p99 data-plane ack 37.7 ms < DP-T3 50 ms** (p50 7.5 ms; LLM mocked — this is
  the data-plane ack, NOT user-perceived latency). Headroom is modest under a hot
  reality's 50 concurrent fsync-bound sessions, but the target is met.
- **Bite:** giving one session TWO processors forked its version sequence — proving
  the I6 **routing serialization** is what holds correctness (there is no storage
  uniqueness on `(aggregate_id, aggregate_version)`; the PK includes `recorded_at`).

## 4. Soak + delivery lag (Inc-4) and whole-system DR (Inc-5)

- **Lag metric** `lw_projection_lag_seconds` (= age of the oldest un-published
  outbox row) emitted as a Prometheus textfile. Under steady 200/s emit the
  publisher kept up: depth bounded (2–32), lag < 0.2 s — **no BACKLOG growth**.
  Note this is a backlog signal (outbox depth + delivery lag), **NOT a memory-leak
  signal** — the publisher runs here as a host process so RSS is not sampled; the
  RSS/memory-leak watch is the manual containerized soak (`D-S12-RSS-MEMORY-SOAK`).
  Soak cannot be time-compressed: a CI leak-smoke + a manual wall-clock-hours run
  (`soak.sh manual`). **Bite:** throttling the publisher drove lag 0.07 s → 20.8 s
  monotonic. Closes `D-S7-SOAK-LAG-METRIC`.
- **Multi-shard DR:** 3 real Postgres shards dumped, dropped TOGETHER (disaster),
  restored together, every shard verified **content-identical** (ordered digest
  over `event_id || aggregate_version || payload` — not the id set alone, so a
  payload/version corruption is also caught). **Bite:** a tampered dump restored
  non-identical and the checksum caught it. Closes `D-S8-MULTI-SHARD-DR`.

## 5. Verdict, residual unknowns, and Phase 2

**Verdict:** the architecture scales the foundation paths the L4–L7 layers ride on,
**without a from-scratch refactor.** The per-shard write path and the I6 session
path scale on the cheap axes (shards, cores). The one architectural ceiling found
(I7 single consumer) is real but fixed by a **local, ranked, non-structural change**
(batch the XACK), not a redesign.

**Residual unknowns one box CANNOT surface (Phase 2 must certify):**
- Real network fan-out + a Redis **cluster reshard** at large N.
- meta-DB connection-pool ceilings with thousands of live realities (here capped to
  avoid exhausting one shard's 300 connections).
- Absolute V3 throughput (10k players / ~1000 realities) — this report extrapolates
  a **lower bound**; only a multi-node cluster certifies the absolute.
- True physical-core isolation (WSL2 cpuset is logical-vCPU isolation).
- The meta-worker ceiling AFTER the XACK-batching fix (re-measure post-fix).
- **Memory-leak (RSS) soak** — Phase-1 soak proves no *backlog* growth, not no
  *memory* leak (publisher ran as a host process). `D-S12-RSS-MEMORY-SOAK`:
  containerized publisher + RSS watch over a long manual soak.

**Ranked refactor-risk list:**
1. **✅ RESOLVED — I7 meta-worker single-consumer XACK** (was ~22k < 50k/s). Batched
   the XACK → **~230k msgs/s, 4.5× above target** (bite still fires). Was HIGH; now
   cleared on this box. Re-confirm at Phase-2 scale.
2. **MED — meta-DB connection ceiling** at thousands of realities (Phase-2 / pooling
   like pgbouncer in front of the meta DB).
3. **LOW — per-shard packing absolute** (re-measure on a real shard node at higher
   concurrency; Phase 2).

**Phase 1 (this) vs Phase 2:** Phase 1 = pre-prod, single-box, cheap → finds the
coherency/serial walls + a USL lower bound. **Phase 2 (`D-S12-MULTI-HOST`)** = real
cluster + prod observability → certifies the absolute V3 numbers. Phase 1 must
never be read as a V3 certification.
