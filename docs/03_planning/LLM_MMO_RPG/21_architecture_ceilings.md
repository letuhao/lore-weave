# 21 — Architecture ceilings (measured)

> **Status:** MEASURED — 2026-07-27. First wall-clock budget for the game tier's commit + fan-out
> path. Facts `CEI-1..CEI-9`.
> **Prefix `CEI` is registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)
> (this commit). The `_boundaries/` ownership-matrix claim still rides the pending batch alongside
> `CWC` — stated per the record-correction discipline rather than left implicit.
>
> Harness: [`services/commit-service/src/bin/ceilings.rs`](../../../services/commit-service/src/bin/ceilings.rs)
> · gate: [`scripts/perf/game-commit-ceilings.sh`](../../../scripts/perf/game-commit-ceilings.sh)
> Supplies the missing inputs to **SL-Q9** (does cross-island IPC cost matter?) and **GDA-Q1**.

---

## 1. What this document is — and the trap it exists to avoid

The game tier is **real but incomplete**: 10 validator stages are `NotRun`, the POC `CombatDomain`
is a four-tool toy, control-plane lease issuance is stubbed (the *fence* is real), and there is no
island manager. The obvious benchmark to run — *"how many players can we host?"* — is exactly the
one that **must not** be run yet. Every missing piece only ADDS work, so that number would come out
flattering today and collapse later. Publishing it would be worse than having no number at all.

This document measures the opposite kind of quantity: the ceilings set by the **architecture**
rather than by the domain. Adding validators, a real ruleset, or an island manager can only push
the running system BELOW these figures. An upper bound measured today is still an upper bound after
the rest is built — which is the entire reason these three, and only these three, were measured.

**In scope:** the commit path (CAS fence → `events` → `channel_event_index` → outbox, one
transaction) and the Redis fan-out leg.
**Explicitly NOT measured** (§7): player capacity, validator cost, WS broadcast fan-out, Class A
movement, LLM decide() cost.

---

## 2. The rig — without which no number here means anything

| | |
|---|---|
| Host | 13th Gen Intel Core i9-13900K · 24 cores / 32 threads · 96 GB RAM · Windows 11 |
| Postgres | 16.14 (Debian) in Docker Desktop / WSL2 — `infra/foundation-dev` |
| Durability | **`fsync=on`, `synchronous_commit=on`**, `wal_level=replica` — full durability |
| `max_connections` | 100 |
| Redis | 7-alpine, same stack |
| `events` rows at measurement | ≈ 38 000 |
| Client | native Rust, `--profile release-commit`, same host as the containers |
| Loopback RTT (`SELECT 1`, p50, warmed, single held connection) | **0.32 – 0.42 ms** (0.361 in the paired run of §3.1) |

**CEI-1 — a throughput figure without its durability settings is not a result.** A commit rate
taken with `synchronous_commit=off` describes a database making no durability promise, and is
roughly 2× the honest number (§3). The harness prints `fsync` / `synchronous_commit` on every run
and warns loudly when either is relaxed; the gate **fails** rather than let a relaxed run be quoted
as a ceiling. This is not pedantry — it is the single easiest way for a benchmark to lie.

---

## 3. C1 — one channel, one writer: the per-channel commit ceiling

`ChannelWriter::append` under a live lease, serial, full durability. Serial is not a pessimistic
choice: one writer per channel is what DP-A16 mandates, so this **is** the per-channel ceiling
rather than a sample of it.

```
c1 n=1000  COMMITS_PER_SEC=174.0  p50=5.414 ms  p95=7.373 ms  p99=9.195 ms  max=23.018 ms
```

**CEI-2 — one channel sustains ≈ 170 durable commits/sec; a committed turn costs ≈ 5.4 ms (p50),
9–11 ms (p99).** Across the session the rate ranged 158–189 commits/sec on an otherwise-busy
workstation, with p50 stable at 5.3–5.4 ms; the run above (n=1000) is the reference.

### 3.1 Where the 5.4 ms goes — the decomposition that makes this portable

From a **paired back-to-back run** (n=800 each, same sitting, so the two halves are comparable —
mixing runs here would let noise masquerade as structure):

```
clean               p50 = 5.426 ms    rtt_p50 = 0.361 ms
--bite-sync-off     p50 = 2.529 ms
```

`append` issues six round trips (BEGIN, CAS, `events`, `channel_event_index`, outbox, COMMIT), so:

| Component | Derivation | p50 cost | Share |
|---|---|---:|---:|
| **WAL fsync** | clean − sync-off | **2.897 ms** | **53 %** |
| Transport | 6 × 0.361 ms RTT | 2.166 ms | **40 %** |
| Postgres work (parse/plan/insert/index) | remainder | 0.363 ms | 7 % |

**CEI-3 — the commit is half fsync, and most of the rest is the wire; actual database work is under
a tenth of it.** The decomposition is what makes CEI-2 portable to other hardware rather than a
fact about this workstation. Holding the fixed cost (fsync + PG work ≈ 3.26 ms) and varying only
the link:

* PG over a unix socket or same-VPC link (RTT ≈ 0.05 ms) → p50 ≈ 3.6 ms → **≈ 280 commits/sec**.
* PG across a cloud AZ hop (RTT ≈ 1 ms) → p50 ≈ 9.3 ms → **≈ 110 commits/sec**.

**CEI-4 — `append` costs six round trips, and that is the largest optimisation still on the table.**
Folding the four statements into a single CTE would delete five of the six round trips — ~1.8 ms
(33 %) on this link, and proportionally more on a slower one. **It is deliberately not being done** — §6 shows the commit path has ~200× headroom
over what turn-based play demands, so spending complexity here would buy nothing. Recorded so the
lever is *known* rather than rediscovered under pressure.

### 3.2 Table growth

`events` grew 0 → 38 000 rows across this session with no measurable change in C1 (169 → 174
commits/sec, inside run-to-run noise). At this scale index maintenance is not a driver. This says
nothing about behaviour at 10⁸ rows — partition pruning and index depth are a separate question,
untested here.

---

## 4. C2 — K channels against one Postgres: the contention curve

Each channel gets its own `channel_writer_state` row, so writers never contend on the CAS itself.
What this finds is where the **shared database** stops scaling. Pool sized to K+2 throughout, so
the curve reflects the database and not pool starvation.

| K | aggregate commits/s | per-channel commits/s | median channel p95 | scaling vs K=1 |
|---:|---:|---:|---:|---:|
| 1 | 181 | 181 | 7.3 ms | 1.0× |
| 2 | 364 | 182 | 7.9 ms | 2.0× |
| 4 | 620 | 155 | 8.4 ms | 3.4× |
| 8 | 1 120 | 140 | 8.1 ms | 6.2× |
| 16 | 2 173 | 136 | 8.0 ms | **12.0× (75 % eff.)** |
| 32 | 3 070 | 96 | 12.9 ms | 17.0× (53 % eff.) |
| 64 | 4 892 | 76 | 16.9 ms | 27.1× (42 % eff.) |

**CEI-5 — one Postgres sustains ≈ 4 900 durable commits/sec across 64 concurrent island writers,
with per-channel p95 degrading from 7.3 ms to 16.9 ms.**

**CEI-6 — the knee sits between K=16 and K=32.** Up to 16 channels, per-channel latency is flat
(8.0 ms) and scaling is 75 % efficient — islands are essentially free of one another. Past 32,
per-channel throughput falls 136 → 76/s and p95 more than doubles. **K ≈ 16–24 per Postgres is the
band where an island neither notices nor is noticed by its neighbours.**

**CEI-7 — `max_connections=100` is a harder wall than throughput.** The commit path holds a
connection for the duration of its transaction, so ~98 concurrent island writers exhaust the
default Postgres before the throughput curve flattens. This is a **provisioning** constraint, not a
code one: `infra/docker-compose.pgbouncer.yml` already exists, and transaction-mode pooling is the
standard answer. Flagged here because it is the limit that will be hit first, and it is invisible
to every unit test.

---

## 5. C3 — the fan-out leg (Redis)

Publisher-side `XADD` and room-side `XREADGROUP`. Deliberately excludes the Go publisher's **poll
interval**: that is a tuned latency, not a throughput ceiling, and folding it in here would
understate what the transport can carry.

```
XADD serial      =   2 611 /s   (p50 0.352 ms)
XADD pipelined   = 101 591 /s   (batch 64)
XREADGROUP       =  55 799 /s   (batch 64)
```

**CEI-8 — the serial 2 611/s figure is NOT a Redis limit; it is the loopback.** Its p50 (0.352 ms)
is the RTT measured in §2 — one round trip per event. The real publisher drains the outbox in
batches, so the meaningful number is the pipelined one, 39× higher. Quoting the serial figure as a
fan-out ceiling would be a measurement artefact masquerading as an architectural fact.

**CEI-9 — fan-out has ≈ 11× the headroom of the commit path, so Redis is not the constraint at any
scale this architecture can commit at.** The binding consume rate (55 799/s) exceeds the K=64
aggregate commit ceiling (4 892/s) by 11.4×. Every event that can be committed can be fanned out
with an order of magnitude to spare.

---

## 6. What the three numbers say together

The interesting result is a **negative** one, and it is worth stating plainly:

> **The commit path is not the risk.** For Class B turn-based play it has roughly two orders of
> magnitude more headroom than the design needs.

The arithmetic: a Class B turn is gated by `LlmDriver.decide()` at 1–5 s ([13](13_simulation_loop.md) §3),
so an encounter commits at most ~0.33 turns/sec. Sixty-four concurrent encounters therefore demand
≈ **21 commits/sec** — **0.4 %** of the measured 4 892/s aggregate ceiling. Per-channel, 174
commits/sec against a need of 0.33 is a ~500× margin, and the 5.4 ms commit is invisible beside a
1–5 s LLM call.

Consequences for the build order:

1. **Do not optimise the commit path.** CEI-4's six-round-trip lever stays unspent. There is no
   measurement here that justifies the complexity.
2. **The first real limit is connections (CEI-7), not throughput** — a provisioning fix, available
   off the shelf, needed before ~98 concurrent islands.
3. **The load question that actually matters is elsewhere.** Class A movement at 20 Hz is a
   different lane entirely and never touches this path — SL-D11 makes it non-event-sourced
   precisely so it cannot. It is unbuilt, unmeasured, and is where the real capacity question
   lives.
4. **SL-Q9 input:** in-process island step is ~200 ns ([14](14_sim_core_spec.md) S1a) against a
   5.4 ms commit — a factor of ~27 000. Co-location (SL-D20b) is not merely justified; the step
   cost is not visible in this budget at all.

---

## 7. What is NOT measured here (and must not be inferred)

| Not measured | Why it would mislead |
|---|---|
| **Player capacity** | Dominated by the 10 `NotRun` validator stages, the real ruleset domain, and the absent island manager. Any figure today is optimistic by an unknown factor. |
| **Validator pipeline cost** | Unbuilt. If stages turn out to need their own database reads, they add round trips to the pre-commit path — the one place these numbers could move materially. |
| **WS broadcast fan-out** | One commit → M subscribed clients is a `game-server` + WebSocket property. Needs M real clients; `scripts/perf/k6-game-server.sh` is the vehicle. **This is the next measurement.** |
| **Class A movement (20 Hz)** | Not built. Different lane, different persistence model (SL-D11), different profile. |
| **LLM decide() cost** | Measured separately in POC-2; not part of the commit budget. |
| **Behaviour at 10⁸ events** | Measured at 3.8×10⁴ rows. Partition pruning and index depth at scale are untested. |

---

## 8. Non-vacuity — the bites, and what each one rules out

Every ceiling ships a bite that must MOVE its number, per the repo's bite discipline. A benchmark
that cannot fail is decoration.

| Bite | Clean | Bitten | Rules out |
|---|---:|---:|---|
| `c1 --bite-sync-off` — relax `synchronous_commit` | 168.7/s | **345.3/s** (2.05×) | that C1 is fsync-bound is *asserted* rather than shown. If throughput did not move, C1 would not be a durability ceiling. |
| `c2 --bite-pool1` — cap the pool at ONE connection | 2 073/s @ K=16 | **162/s** (13× worse) | that the C2 curve reflects real database concurrency rather than an artefact of the harness. |
| `c3 --bite-fat` — 100× payload | 101 547/s | **12 504/s** (8.1× worse) | that C3 measures Redis work rather than client loop overhead. |

A fourth guard is bite-proven the same way: pointing `LOREWEAVE_TEST_PG_URL` at a real service
database (`loreweave_book`) is **refused with exit 3** before a single row is written. The harness
is append-only, so the repo's `EnsureThrowawayDB` rule does not strictly bite — but in an
event-sourced store, injecting tens of thousands of synthetic `turn.resolved` events into a real
reality is permanent, and unrecoverable in a quieter way than a `DELETE` would be.

The gate's assertions are **ratios, not absolute values** — ratios are machine-independent, so the
gate stays honest on a slower box instead of going red on hardware and green through a real
regression. Absolute floors appear only as absurdity checks.

---

## 9. Reproducing

```bash
cd infra/foundation-dev && docker compose up -d postgres-foundation redis-foundation
# apply contracts/migrations/per_reality/*.up.sql once
bash scripts/perf/game-commit-ceilings.sh          # measure + assert scaling/durability
bash scripts/perf/game-commit-ceilings.sh --bite   # the non-vacuity gate
bash scripts/perf/game-commit-ceilings.sh --sweep  # the full C2 curve
```

The harness is **append-only** — no `DELETE`, `TRUNCATE` or `DROP`, and every run mints a fresh
random `reality_id`, so it cannot touch another run's rows. Point it at the throwaway
`foundation-dev` stack.

---

## 10. Open

| Id | Question | Resolved by |
|---|---|---|
| **CEI-Q1** | What does the validator pipeline add to the pre-commit path? | Re-run C1 once the 10 stages exist; the delta is the answer. |
| **CEI-Q2** | Where is the WS broadcast ceiling (one commit → M clients)? | `scripts/perf/k6-game-server.sh` against real clients — the next measurement. |
| **CEI-Q3** | Does the K≈16–24 band (CEI-6) hold under pgbouncer transaction pooling? | Re-run the C2 sweep through `infra/docker-compose.pgbouncer.yml`. |
| **CEI-Q4** | Does C1 hold at 10⁸ events with partition pruning in play? | A seeded large-table run; not urgent given the headroom in §6. |
