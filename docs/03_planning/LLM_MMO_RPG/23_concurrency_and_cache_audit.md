# 23 — Concurrency & cache audit (single-thread → multi-node)

> **Status:** AUDIT — 2026-07-27. Findings `CNC-F1..F16`, decisions `CNC-D1..D5`, open `CNC-Q2..Q3`.
> **§8 items 1–3 were BUILT the same day**; §9 records the three things building them found that the
> audit could not have known without executing. Remaining: **CNC-Q3** (the island manager) and
> **CNC-Q2** (rides the Class A movement lane).
> **Prefix `CNC` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> **Every finding cites `file:line` and was read from code, not from design docs.** Where a design
> doc and the code disagree, the code wins and the disagreement is the finding.
>
> Priced against [21 ceilings](21_architecture_ceilings.md); ingress rules from
> [22](22_ingress_and_admission.md).

---

## 1. Why this audit exists

The concern, stated by the PO: *"single thread, multiple thread, multiple cpu, multiple node — if
the architecture does not handle this well it will break, and foundation bugs are harder to patch
later."* That is correct on both counts, and the second half is the reason this was done **before**
the island manager rather than after: three of the findings below are cheap now and expensive once
there is data (F6 needs an index on a range-partitioned table; F7 changes a shipped defence).

**Summary verdict: rungs 1–3 are unusually strong; rung 4 has strong SAFETY and no LIVENESS.**

| Rung | Mechanism | Verdict |
|---|---|---|
| Single thread | Island is single-threaded inside; `&mut self`, no locks | ✅ |
| Multi thread | N islands, **shared-nothing** — nothing to contend on | ✅ structural |
| Multi CPU | Same; **measured 27× at K=64** (CEI-5) | ✅ measured |
| Multi node — *safety* | DP-A16 epoch fence: one CAS at the DB is allocator **and** fence | ✅ built + tested |
| Multi node — *liveness* | Who assigns an island? Who detects a dead node? Who reassigns? | 🔴 **absent** |
| Multi node — *idempotency* | Survives a node death? | ✅ **fixed** — recovery replay (CNC-D2) |

---

## 2. Per-module matrix

| Module | Concurrency unit | Shared mutable state | Multi-node correct? |
|---|---|---|---|
| `crates/sim-core` | one island, single-threaded | **none** (F1) | n/a — no I/O |
| `commit-service` spine | one island per channel | `DedupCache` (process-local, F6) | ✅ safety + dedup (recovery replay) |
| `dp-kernel::channel` | per-`(reality, channel)` writer | none | ✅ CAS fence (F4) |
| `dp-kernel::canon_cache` | per-process | `Mutex<HashMap>` (F3) | in-proc cache, TTL-bounded |
| `publisher` (Go) | N replicas | none | ✅ `FOR UPDATE … SKIP LOCKED` (F5) |
| `game-server` WS edge | per-connection + per-user | `ConnectionCap`, `MessageRateLimiter` (F7) | ✅ **fixed** — Redis token bucket (CNC-Q1) |
| `game-server` rooms | per-room, per-process | room view (projection) | ⚠️ no presence driver (F8) |
| `frontend-game` store | per-browser-tab | zustand store | ✅ session projection, rebuilt on connect |

---

## 3. Findings — rungs 1–3 (thread / CPU)

**CNC-F1 ✅ — the Rust game tier contains ZERO shared mutable state.** A repo-wide grep for
`static mut` · `lazy_static` · `OnceCell/OnceLock` · `Mutex<` · `RwLock<` · `Atomic*` ·
`thread::spawn` · `rayon` · `Arc<Mutex` across `crates/sim-core`, `dp-kernel::{channel,outbox}` and
all of `commit-service` returns **nothing**. Parallelism is shared-nothing by **construction**, not
by discipline — there is no lock to acquire in the wrong order because there is no lock. This is the
single most valuable property in the audit and it should be defended, not eroded (→ CNC-D1).

**CNC-F2 ✅ — measured, not assumed.** [21](21_architecture_ceilings.md): aggregate throughput scales
**27× at K=64** concurrent island writers, with the efficiency knee at **K≈16–24**. Above ~32 the
shared Postgres — not the islands — is the limiter.

**CNC-F3 🟡 MED — the one lock in the tree.** `crates/dp-kernel/src/canon_cache.rs:42` imports
`std::sync::Mutex`, and the type is documented *"Thread-safe … One instance per process."* It is not
on the game hot path today (canon reads, not turn commits), so it does not appear in the CEI-2/CEI-5
numbers. It is recorded because it is the **first** place a multi-core scaling problem would appear
if canon reads ever entered the turn path, and because the audit's headline (F1) would otherwise be
overstated.

---

## 4. Findings — rung 4 (multi-node)

### 4.1 What is genuinely solid

**CNC-F4 ✅ — single-writer is enforced at the DATABASE, not by a lock service.**
`crates/dp-kernel/src/channel.rs` — one atomic
`UPDATE channel_writer_state SET last_event_id = last_event_id + 1 … WHERE current_epoch = $presented`
is simultaneously the id allocator and the fence; 0 rows ⇒ `WrongChannelWriter`. A second node that
believes it owns a channel cannot write, and does not need to be *told* it lost — it finds out at the
write. This is the hard part of multi-node, and it is done.

**CNC-F5 ✅ — the publisher is multi-replica safe.** `services/publisher/pkg/pgsource` drains with
`FOR UPDATE OF o SKIP LOCKED` (line 71), so N publisher replicas partition the outbox without
coordination and without double-emitting.

### 4.2 CNC-F6 🔴 HIGH — durable idempotency is WRITTEN but never READ

This is the finding the audit exists for, and it is the cheapest one to fix today.

The chain, each link verified:

| # | Fact | Evidence |
|---|---|---|
| 1 | The dedup key **is persisted** on every committed event | `spine.rs:278` — `metadata.input_id` |
| 2 | **Nothing ever reads it back** | grep for a read/replay/`metadata->` of `input_id`: **zero hits** |
| 3 | There is **no unique index** on it | `0002_events_table` / `0014_channel_ordering`: no index on `metadata` |
| 4 | EVT-L3 dedup is a **process-local `BTreeMap`**, 60 s TTL | `admission.rs:54-57`; owned by the spine loop at `spine.rs:148` |
| 5 | The island's I2 `seen` set is **RAM only** | `island.rs` — in-memory `SeenSet` |
| 6 | `IslandCheckpoint` **carries** `seen` … | `checkpoint.rs:37` |
| 7 | …but is **never persisted anywhere** | grep for `IslandCheckpoint` outside the kernel + its tests: **zero hits** |

**Consequence.** The bus is at-least-once by design (EVT-L2: ACK only after success, `XAUTOCLAIM`
reclaims a dead consumer's PEL). So: writer node A takes a proposal, commits it, dies before ACK.
Node B reclaims the PEL entry and acquires the lease. B's `DedupCache` is empty, B's island is fresh
(no checkpoint was ever written), and no query consults the log. **B admits and applies the same
intent a second time.** The epoch fence does not help — B legitimately holds the lease.

The player-visible form: *one attack, applied twice, on a server restart.*

**Why it is cheap now and expensive later.** `events` is `PARTITION BY RANGE (recorded_at)`. Adding
an index over `metadata->>'input_id'` on an empty table is instant; adding it across months of
partitions later is a migration with a maintenance window. And the *shape* of the fix is already
decided — the key is being written; only the read side is missing.

**Fix shape (CNC-D2).** On lease acquisition, replay the channel's recent tail and rebuild the
seen-set from `metadata.input_id` — the same replay the room already does (GDA-D7 makes fresh join
and reconnect one code path; this makes writer recovery a third caller of it). Optionally add a
partial index for a hard DB-level backstop. Note the key must also ride **rejection** commits, or
dedup covers only successes.

### 4.3 CNC-F7 🔴 HIGH — rate limiting is per-replica (in code shipped today)

`services/game-server/src/ws/rate-limit.ts:6-9` states it plainly: *"Per-replica (in-process) … A
cross-replica/global cap (Redis token bucket) is future hardening, not V1."* Both `ConnectionCap`
and `MessageRateLimiter` are in-process maps, and `ChannelRoom.submitLimiters` (added under IAS-D5
this session) inherits that.

⇒ With N game-server replicas, a client that opens a connection to each gets **N× the budget**. The
IAS-D5 defence is correct on one node and proportionally weaker on a fleet.

**The instructive contrast — and the design rule it yields (CNC-D3).** The turn economy shipped in
the same session (IAS-D6) is **multi-node-correct for free**, because it lives in island state,
which is single-writer behind the epoch fence. No Redis, no coordination, no staleness.

> **A defence that lives inside the island is correct at every scale. A defence that lives at the
> edge is per-replica and must buy distributed state explicitly.** Layer 3 scales for free; layer 1
> does not. Place a control accordingly, and when it must live at the edge, say so out loud.

### 4.4 CNC-F8 🟡 MED — no Colyseus presence driver; rooms are per-process

A grep for `RedisPresence` / `RedisDriver` / `matchMaker` in `services/game-server/src` returns
nothing, so Colyseus runs on the default in-process presence. Two replicas can each hold a `channel`
room for the same channel id.

For the **turn lane** this is tolerable: the room is a read-only projection (GDA-A7, CWC-A1), so two
copies of the same fold are harmless, and authority sits in commit-service behind the fence. It is
recorded because (a) it is why F7 bites, and (b) the **Class A movement lane** (RTM, ~20 Hz,
authority-adjacent at the edge) will not tolerate it — that lane needs a room singleton, and
discovering it then would be a re-architecture rather than a config change.

### 4.5 CNC-F9 🟡 MED — the control plane is stubbed: safety without liveness

`crates/dp-kernel/src/channel.rs` says so in its own header: *"Lease issuance is CP-less for now; the
FENCE is real."* `acquire_writer_lease` bumps `current_epoch` directly. So:

* **Safety** (never two writers) — ✅ holds unconditionally, at the DB.
* **Liveness** (someone assigns islands, detects a dead node, reassigns) — 🔴 does not exist.

Today a human runs one spine by hand. This is precisely the island manager's job and it is correctly
sequenced *after* this audit — but F6 must land first, because writer reassignment is exactly the
event that triggers the double-apply.

---

## 5. Findings — caching

**CNC-F10 ✅ — the game tier is REPLAY-DERIVED, not cache-invalidated.** This is the strongest
property in the section and it deserves naming, because it dissolves most of the problem class
rather than managing it. The room does not hold a cache awaiting an invalidation message; it **folds
the committed event stream** (`replayView` / `foldEvent`, GDA-A7/D7). The browser store is a session
projection rebuilt on every connect (CWC-A1/A7). There is no invalidation protocol to get wrong,
because there is no invalidation.

**CNC-F11 ✅ — the platform layer already has a designed cache-coherency model.** Not a blank spot:
[`06_data_plane/06_cache_coherency.md`](06_data_plane/06_cache_coherency.md) specifies
stale-while-revalidate with a 20 s grace (DP-X4), TTL bounds (DP-X7), deliberately fire-and-forget
invalidation pub/sub, jittered re-population to avoid an N-node thundering herd, and an alarm when
in-process staleness exceeds the Redis layer's.

**CNC-F12 ℹ️ — correction: there is no MongoDB in this stack.** The data layer is Postgres
(per-service DBs) · Redis · MinIO · RabbitMQ. A "mongodb cache" tier should not be designed for a
store that does not exist; the real tiers are: in-process → Redis → Postgres.

**CNC-F13 🟡 — the island's memory is AUTHORITATIVE, not a cache, and that distinction must be
written down.** While an island lives, its `State` *is* the truth for that channel; the event log is
the durable record of how it got there. The failure waiting to happen is someone adding a read-through
cache over island state for a "fast read" — inheriting every staleness problem the replay design
avoids, on the one piece of state where being wrong is a rules violation rather than a stale render.

> **CNC-D4 — never cache what an island owns; project it from the log.**

---

## 6. Decisions

| Id | Decision | Rationale |
|---|---|---|
| **CNC-D1** | The game tier stays **shared-nothing**; introducing a lock or shared mutable state into the island path needs an explicit decision | F1 is structural, and structural properties erode one convenience at a time |
| **CNC-D2** | Idempotency gets a **durable backstop**: rebuild the seen-set by replaying `metadata.input_id` on lease acquisition; the key must also ride rejection commits | F6 — at-least-once delivery plus RAM-only dedup double-applies across a node death |
| **CNC-D3** | A control is placed by **where its state must live**: island-state controls are multi-node-correct for free; edge controls are per-replica and must declare it | F7 vs IAS-D6 |
| **CNC-D4** | **Never cache what an island owns** — project it from the log | F13 |
| **CNC-D5** | Multi-node correctness is proven **mechanically**, not by review: a conformance test asserts identical committed output for the same inputs at 1 vs N threads | The kernel is deterministic (DetRng, BTreeMap, injected time), so this test is possible — most systems cannot write it |

## 7. Open

| Id | Question | Blocks |
|---|---|---|
| **CNC-Q1** | Cross-replica rate limit — Redis token bucket at layer 1 | F7; needed before a second game-server replica |
| **CNC-Q2** | Room singleton / presence driver | F8; **blocks the Class A movement lane**, not the turn lane |
| **CNC-Q3** | CP lease issuance + death detection + reassignment policy | F9; **is** the island manager |

---

## 8. Fix order

1. ~~**CNC-D2 (F6)** — durable idempotency~~ ✅ **BUILT.** `commit-service::recovery` replays the
   channel tail on lease acquisition and seeds the island's I2 set from `metadata.input_id`; the
   DP-A17 turn counter and version high-water are recovered in the same query (both were also
   RAM-only, and `turn_number` silently rewound to 0 on every restart). 5 PG-gated tests.
2. ~~**CNC-D5** — the 1-vs-N-thread conformance test~~ ✅ **BUILT.** `crates/sim/tests/concurrency.rs`.
3. ~~**CNC-Q1 (F7)** — cross-replica rate limit~~ ✅ **BUILT.** Redis token bucket, Lua-atomic,
   keyed by authenticated user; degrades to the per-replica cap on a Redis outage rather than
   failing open or closed.
4. **CNC-Q3 (F9)** — the island manager. Now standing on an enforced front door (doc 22), an
   idempotency guarantee that survives writer handover (1), and a mechanical concurrency check (2).

`CNC-Q2` rides with the Class A movement lane, which is where it starts to matter.

---

## 9. What building the fixes found

Three things the audit could not have known without executing, recorded because a finding list that
only keeps its correct predictions is not a record.

**CNC-F14 — the turn counter had the same disease as the dedup set, one line away.**
`spine.rs` seeded `turn_number = 0` on every start with the comment *"Seeded 0 = never advanced"*.
So a restart rewound the DP-A17 counter and every client's `turn_number` went **backwards** — the
one thing [20](20_client_wire_contract.md) tells the browser it may rely on. Same root cause as
CNC-F6 (recovery state living only in RAM), same query to fix, so it was fixed with it rather than
left as a known-broken sibling. Finding one instance of a class and not looking for the others is
how the second one ships.

**CNC-F15 — the conformance test was bite-proven, and it needed to be.** A test asserting "these
two runs agree" passes trivially if both runs are empty or if nothing shared exists to break. A
process-global counter was planted in `Island::submit_inner` and **all three** conformance
assertions went red independently (sequential-vs-concurrent, run-to-run, and neighbour-independence)
before it was reverted. The fourth test asserts the fleet produces a non-trivial outcome mix, so the
comparison cannot succeed by comparing nothing to nothing.

**CNC-F16 — the new rate limiter silently disabled itself on a valid config.** `refillPerSec = 0`
(a legitimate "hard budget, no refill", reachable from env) made the TTL divide to `Infinity`;
`String(Infinity)` reached Redis as a non-integer `EXPIRE`, the script errored, and the
degrade-on-error path returned **allowed** — the global cap turned itself off with nothing but a
log line. Caught by the shared-budget test, which allowed 10 of a budget of 5. The general lesson
is about the *degrade path*, not the arithmetic: **a fail-degraded branch will absorb any bug
upstream of it and report success.** It needs a test that asserts the cap actually caps, not only
that the outage path returns something sensible.
