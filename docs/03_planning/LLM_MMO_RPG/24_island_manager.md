# 24 — Island manager (writer liveness + island lifecycle)

> **Status:** BUILT — 2026-07-27 (design + all four §10 items, same day). Closes **CNC-Q3 / CNC-F9**, the last of the audit's multi-node
> gaps. Axioms `IMG-A1..A7`, decisions `IMG-D1..D8`, open `IMG-Q1..Q3`.
> **Prefix `IMG` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Builds on: [23 audit](23_concurrency_and_cache_audit.md) (the gap) ·
> [22 ingress](22_ingress_and_admission.md) (the enforced front door) ·
> [21 ceilings](21_architecture_ceilings.md) (the budget) ·
> [15 commit-service](15_commit_service.md) (CS-A1: the writer is a ROLE, not a service) ·
> [`06_data_plane/05_control_plane_spec.md`](06_data_plane/05_control_plane_spec.md) (the CP this
> deliberately does **not** build yet — see IMG-D1).

---

## 1. The gap, precisely

`crates/dp-kernel/src/channel.rs` says it in its own header: *"Lease issuance is CP-less for now;
the FENCE is real."* The audit split that into the two halves that matter:

| | Today | |
|---|---|---|
| **Safety** — never two writers on a channel | ✅ unconditional, at the DB | one CAS is allocator **and** fence; a losing node finds out at the write |
| **Liveness** — someone assigns islands, notices a dead node, reassigns | 🔴 **does not exist** | `acquire_writer_lease` bumps `current_epoch` on demand, with no expiry and no holder |

Concretely, three things are absent:

1. **A lease cannot expire.** `channel_writer_state` has `current_epoch`, `last_event_id`,
   `updated_at` — and no TTL and no holder identity. A node that dies holds its epoch forever, in
   the sense that nothing *else* knows it may take over.
2. **Takeover is unconditional.** Anyone may call `acquire_writer_lease` at any time and win. That
   is safe (the previous holder is fenced out) but it is not a *policy* — a healthy writer can be
   evicted mid-encounter by a misconfigured process, and nothing distinguishes that from a
   legitimate failover.
3. **Nothing owns more than one island.** `spine.rs` hosts exactly one island, launched by hand
   with `--channel N`. There is no spawn, no routing, no dissolve, no supervision.

## 2. IMG-A1 — put liveness where safety already is

> **The lease gets an expiry and a holder, in the same row the fence already uses. Liveness is
> enforced by the database, not by a coordination service.**

The full control plane ([`05_control_plane_spec.md`](06_data_plane/05_control_plane_spec.md)) is
designed — a 25-method gRPC surface with a node registry, session registry, and writer-binding RPCs.
It is also unbuilt, and building it is a platform track, not a game-tier one.

**IMG-D1 — do not build the CP to close this gap.** The reasoning is the same one that made the
epoch fence good: the safety property was pushed into a single atomic statement rather than into a
service that had to be correct, available, and agreed-with. Liveness can go to the same place. A
lease row with `holder_id` + `lease_expires_at`, renewed by its holder and claimable by anyone once
expired, gives failover with:

* **no new service** to deploy, monitor, or make highly-available;
* **no split-brain risk** beyond what the fence already handles — two nodes racing to claim an
  expired lease still resolve to exactly one, by the same CAS;
* **no new failure mode** when the coordinator is down, because there is no coordinator.

When the platform CP does land, it takes over *issuance policy* (which node should host which
island) over **the same table with the same fence** — exactly as `channel.rs` already anticipates.
This design is therefore a subset of the CP contract, not a competitor to it.

## 3. IMG-A2..A4 — the lease protocol

**IMG-A2 — a lease is `(channel, epoch, holder, expires_at)`.** `channel_writer_state` gains:

```sql
ALTER TABLE channel_writer_state
    ADD COLUMN holder_id         UUID,          -- which process holds it
    ADD COLUMN lease_expires_at  TIMESTAMPTZ;   -- NULL = legacy/unheld
```

Nullable, because rows written before this migration exist and must remain claimable rather than
becoming permanently unownable.

**IMG-A3 — three operations, each one atomic statement.**

| Op | Statement shape | Fails when |
|---|---|---|
| `claim` | `UPDATE … SET epoch = epoch+1, holder = $me, expires = now()+$ttl WHERE lease_expires_at IS NULL OR lease_expires_at < now()` | someone healthy holds it |
| `renew` | `UPDATE … SET expires = now()+$ttl WHERE holder = $me AND current_epoch = $mine` | you were fenced or evicted |
| `release` | `UPDATE … SET expires = now() WHERE holder = $me AND current_epoch = $mine` | you no longer hold it |

**A failed `renew` is the signal that matters** and it must be loud: it means this process is no
longer the writer, so it must stop stepping its islands *immediately* rather than discover it at the
next append. Discovering it at the append is safe (the fence rejects the write) but wasteful — an
island can burn a whole LLM decision on a turn it will not be allowed to commit.

**IMG-A4 — `claim` keeps the epoch bump.** Every successful claim increments `current_epoch`, so the
previous holder is fenced even if it is alive and merely partitioned. The expiry decides *who may
try*; the CAS decides *who wins*. Neither alone is sufficient: expiry without the fence allows two
writers during a clock skew, and the fence without expiry is what we have today.

### 3.1 IMG-D2 — the TTL is a wall-clock bet, and it is bounded by measurement

Lease TTL trades failover latency against the risk of evicting a live-but-slow writer. From
[21](21_architecture_ceilings.md), a commit is p50 5.4 ms / p99 ~10 ms, and a Class B turn is
LLM-gated at 1–5 s. So:

* **TTL = 30 s, renew every 10 s** — three renewal attempts inside one TTL, and a TTL comfortably
  longer than the slowest thing a writer legitimately does between renewals (one LLM turn).
* Failover is therefore bounded by ~30 s of channel unavailability, not by a human noticing.

**Clock skew is the assumption this rests on**, and it is stated rather than hidden: all comparisons
use **`now()` evaluated by Postgres**, never a node's clock, so the only skew that matters is
between Postgres and itself. This is the same reason the rate limiter takes server time and the
anti-cheat rule refuses client timestamps.

## 4. IMG-A5..A6 — the manager itself

**IMG-A5 — the manager owns N islands in one process; the island stays single-threaded.** It is a
supervisor, not a scheduler-of-schedulers: it holds a map `channel → (Island, WriterLease)`, renews
leases, and steps islands. CNC-D1 (shared-nothing) is preserved — islands never share state, and the
manager touches one at a time.

**IMG-A6 — the manager is a ROLE inside `commit-service`, not a new service.** CS-A1 already forces
this: the epoch token must sit on the writer node *with* the island, so anything that assigns
islands to nodes and anything that hosts them must be co-located. Splitting them would ship the
token off-node and dissolve DP-A16's guard.

**IMG-D3 — lifecycle operations are the kernel's, not new ones.** `sim-core` already has
`dissolve(self, reason)` (consuming — "Gone" is unrepresentable), `depart`/`arrive` for SL-A12
handoff, and `checkpoint`/`restore`. The manager calls them; it does not reimplement them.

**IMG-D4 — spawn is idempotent per channel.** Asking for an island that already exists returns the
existing one. Anything else races the moment two proposals for a new encounter arrive together.

**IMG-D5 — a dissolved island releases its lease in the same operation.** Otherwise the channel is
unclaimable for a full TTL after a clean shutdown, which turns every deploy into a 30 s outage per
channel.

## 5. IMG-A7 — recovery composes with CNC-D2

When the manager claims a channel, it runs the CNC-D2 recovery replay **before** stepping anything:
seed the I2 set from `metadata.input_id`, restore the DP-A17 turn counter and version high-water.

> This is the whole reason CNC-D2 was built first. Writer reassignment is the event that triggers
> the double-apply, so shipping the manager before the recovery would have *created* the bug it
> then had to survive.

**IMG-D6 — claim → recover → step, in that order, always.** A manager that stepped before recovering
would apply redelivered intents in the window between.

## 6. Failure behaviour

| Failure | Result |
|---|---|
| Manager process dies | Leases expire after TTL; another manager claims, recovers, resumes |
| Postgres unreachable | Renew fails ⇒ manager stops stepping (IMG-A3). It cannot commit anyway |
| Network partition (manager alive, DB reachable from a peer) | Peer claims after expiry + bumps epoch ⇒ old holder is fenced at its next append and its renew fails |
| Two managers race an expired lease | Exactly one wins the CAS; the loser sees 0 rows and does not claim |
| Clock skew | Only Postgres's clock is consulted (IMG-D2) |

**IMG-D7 — a manager that cannot renew stops stepping but does NOT exit.** Exiting throws away
warm islands for what may be a transient blip; stopping is reversible and safe, because the fence
means nothing it produced can be committed anyway.

## 7. Scope

**In:** the lease protocol (claim/renew/release with expiry + holder), the multi-island supervisor,
spawn/dissolve, claim→recover→step ordering, and the failure behaviours above.

**Out, deliberately:**

* **Placement policy** (*which* node should host *which* island) — that is the CP's job (IMG-D1).
  V1 takes what it is given: a manager claims the channels it is configured for.
* **Cross-node island migration** — `depart`/`arrive` exist in the kernel; a *live* migration
  protocol between nodes is a separate design.
* **CNC-Q2 room singleton** — a game-server concern, rides the Class A movement lane.
* **Autoscaling** — needs the placement policy first.

## 8. Decisions

| Id | Decision | Rationale |
|---|---|---|
| **IMG-D1** | Liveness goes in the lease row, not a new coordination service | Same reasoning that made the fence good; the CP later takes over policy on the same table |
| **IMG-D2** | TTL 30 s, renew 10 s, all times from Postgres `now()` | Three renewals per TTL; TTL > one LLM turn; no node clock is trusted |
| **IMG-D3** | Lifecycle reuses the kernel's `dissolve`/`depart`/`arrive` | They already encode the invariants; a second implementation would drift |
| **IMG-D4** | Spawn is idempotent per channel | Two simultaneous proposals for one new encounter must not create two islands |
| **IMG-D5** | Dissolve releases the lease atomically | Otherwise every clean shutdown costs a TTL of unavailability |
| **IMG-D6** | Order is always claim → recover → step | Stepping before recovery re-opens CNC-F6 |
| **IMG-D7** | Renew failure stops stepping; it does not exit | Reversible, and the fence already makes it safe |
| **IMG-D8** | The manager is a role in `commit-service`, co-located with the token | CS-A1; splitting ships the epoch token off-node |

## 9. Open

| Id | Question | Notes |
|---|---|---|
| **IMG-Q1** | How does a manager learn which channels to claim? | V1: configured/discovered from `channel_writer_state`. Real answer is CP placement |
| **IMG-Q2** | Should a lease renewal piggyback on the commit CAS? | It touches the same row; folding it in would make an active writer self-renewing and cut idle renewals. Measure first (CEI-4 says the commit is already 6 round trips) |
| **IMG-Q3** | Encounter channels are children of a cell (CS-D8) — does the child inherit the parent's lease or hold its own? | Affects blast radius: one lease per cell fails over encounters together |

## 10. Build order — DONE

1. ~~Migration~~ ✅ `0015_writer_lease_liveness` — `holder_id` + `lease_expires_at`, nullable.
2. ~~Lease protocol~~ ✅ `claim`/`renew`/`release`, one statement each, **6 PG-gated tests all
   asserting negatives** (a healthy lease cannot be stolen · a fenced holder cannot renew · a stale
   holder cannot release another's lease · 8 racing claimants resolve to exactly one).
3. ~~Manager~~ ✅ `commit-service::manager` — `adopt` (claim → recover → step), `renew_all`,
   `drain`, `relinquish`.
4. ~~Failover test~~ ✅ `tests/failover.rs`, 5 tests.

### 10.1 What building it settled

**A dead writer cannot be modelled by re-claiming with a negative TTL.** The first version of the
failover test did that, and it failed — correctly. A healthy lease *refuses* the claim, so the lease
stayed healthy and the test proved nothing. Death is the **absence of renewal**, so the faithful
model is to push the deadline into the past (`expire_lease`) — which is also what makes the test
run in milliseconds instead of sleeping out a 30 s TTL. The distinction matters beyond the test:
"stop renewing" and "hand it over" are different operations, and only the second is `relinquish`.

**`adopt` takes a builder, not an island.** A channel already held by a healthy writer should cost
nothing; constructing an encounter's state for a channel this node will not be allowed to write is
work thrown away, and on a fleet it is work thrown away on *every* manager that does not win.

**`HeldByAnother` is a normal outcome, not an error.** It is how a manager discovers a channel is
already covered. Modelling it as an error would make the healthy path noisy and push callers toward
ignoring it.
