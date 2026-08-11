# RUN-STATE — durable subscribe: let something READ what the writer commits

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3** · Data Plane channels **DP-Ch1–Ch37** · `contracts/events/_registry.yaml` — the audit is §1, and it found that **the backing store DP-Ch16 subscribes to does not exist**: `dp:events:{reality}:{channel}` appears in four documents and in **zero source files** of any language. The turn loop committed its first `channel.turn_boundary` yesterday and nothing can observe it.

---

## 0 · HOW TO WORK

**The binding execution contract is [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)** — adopted verbatim, not copied: the execution invariant, the source-of-truth rule, the six-step bite sequence, the hazards, the blocker rule, the continuation check, the stop-condition list, and the list of things that are NOT stop conditions.

Hazards that have each cost time in the last two tracks:

* **Run `--run-all` DETACHED and read its REAL exit code** (`BDR-89`, `BDR-90`). The task notification reports the *outer shell's* status; it said `0` for a sweep that exited `1`, twice. A foreground call that takes SIGTERM leaves a bite harness's mutation — typically a deleted assertion — in the tree.
* **Byte-level I/O for anything a shell executes, and for documents** (`BDR-86`). `Path.write_text` on Windows rewrote a shell gate to CRLF and separately rewrote every line of `SESSION_HANDOFF.md`, which handed the staged citation gate ten thousand lines of archive.
* **Never restore a bite with `git checkout`** (`TLD-10`) — it restores from the index and deletes unstaged work. Save the bytes.
* **A bite harness is itself an unverified check** (`TLD-11`). It failed three times in one session, always by calling a working arm dead. The red must NAME the thing.

---

## 1 · PHASE 0 — AUDIT-EXISTING

The goal named three questions. Each is answered with a command.

### 1.1 · Q1 — What already streams events here? **Four things, none of them this.**

| what | where | what it actually is |
|---|---|---|
| control channel | `crates/contracts-ws/src/control_channel.rs` | Redis **pub/sub** on `lw:dependency:control`, for forced-disconnect messages. A control plane, not an event log. |
| ws wire mirror | `crates/dp-kernel/src/ws.rs` | Rust mirror of `contracts/ws/` (Go). Its own header: Rust services surfacing WS endpoints are *"none today — gateway is TypeScript NestJS"*. |
| fan-out | `crates/foundation-model/src/fanout.rs` | An **S9 formal model** of cross-reality `xreality.*` dispatch, for model checking. Not a runtime. |
| XADD / XREADGROUP | `services/commit-service/src/bin/ceilings.rs` | The `c3` leg of an append-throughput **benchmark**. |

**None of them is a per-channel durable event stream**, and the resemblance is close enough that "we already have fan-out" would have been a plausible thing to believe without looking.

### 1.2 · Q2 — **DP-Ch17's backing store does not exist.** This is the finding.

`dp:events:{reality_id}:{channel_id}` is DP-Ch16's *"Default subscribe path"*. Measured across `*.rs`, `*.go`, `*.ts`, `*.py`, `*.yaml`:

```
grep -rn "dp:events" --include=*.rs --include=*.go --include=*.ts --include=*.py --include=*.yaml .
  → 0 hits outside docs/
```

Four documents describe it; nothing implements it. **The half that DOES exist is the other one.** DP-Ch17 specifies two tiers and calls Postgres *canonical* and the Redis tail *best-effort live* — and the Postgres tier is shipped: `events` carries `channel_id`, `channel_event_id`, `writer_epoch`, `causal_refs`, `turn_number`, with `channel_event_index` enforcing the per-channel order.

DP-Ch21 step 8 tells `advance_turn` to *"append to Redis Stream … (DP-Ch17)"*. `ChannelWriter::append` does **not**. It writes an **I13 outbox row in the same transaction** and lets the platform publisher fan out — and that is not a deviation, because DP-Ch17's own algorithm says *"Same tx **(or outbox per 02_storage R6)** appends to Redis Stream"*. The outbox branch was taken; the relay leg that turns an outbox row into a `dp:events:*` entry was never written.

**So the missing piece is smaller and better-defined than "build durable subscribe":** a reader over the canonical store, and — separately, later — a relay for the live tail.

### 1.3 · Q3 — The consumer is in another language

DP-Ch16 names *"human players via gateway/WebSocket fan-out"* first among consumers, and the gateway is TypeScript NestJS (`Q-L6-1`). Its other two named consumers are the **bubble-up aggregator** (`16_bubble_up_aggregator`, still in `NO_PRODUCER`) and **turn-boundary watchers** (`15_turn_boundary` — which as of 2026-08-11 has a producer, and is the only consumer this track can actually satisfy today).

### 1.4 · Q2b — Marker symbols, measured

`subscribe_channel_events_durable` **0** · `DurableStreamItem` **0** · `ChannelEvent` **0** ·
`DurableEventStream` and `durable_subscribe` — one hit each, both the *same doc-comment line* in `spec_oracle_rules.rs` recording them as unbuilt. Comment-stripped: **0**. Genuinely greenfield.

### 1.5 · DP-R2 tier table

| Access | Aggregate / store | Tier | Why |
|---|---|---|---|
| Read a channel's events from `channel_event_id` forward | `events` (per-reality Postgres) | **T3** | Durable, canonical, ordered by `DP-A15`. DP-Ch17 calls this tier canonical. |
| Read the channel's current head | `channel_writer_state.last_event_id` | **T3** | Same row the writer CASes; authoritative, no cache. |
| Live tail | Redis Stream `dp:events:*` | **T1** | Best-effort, lossy-tolerant by DP-Ch17's own words. **Not built — `DF-1`.** |
| Resume-token storage | *none* | — | The token is `channel_event_id`, held by the caller. DP-Ch16 stores no cursor server-side, so there is no new table and no new scope key. |

---

## 2 · SEALED FORKS

**`DF-1` · Build the Postgres tier. The Redis live tail is DEFERRED.**
DP-Ch17 calls Postgres *canonical* and the Redis tail *"best-effort live"* — the tail is a latency optimisation, not the contract. A subscriber that resumes from a `channel_event_id` and reads forward out of `events` satisfies everything DP-Ch16 promises about correctness, ordering and resumption; what it does not give is ≤50 ms live delivery. Building the Redis half first would mean building a relay for a stream with no reader. **Reversal trigger:** a measured latency requirement from a real consumer, or the gateway fan-out landing.

**`DF-2` · The reader lives in `dp-kernel`, beside `ChannelWriter`, not in `crates/dp`.**
Same reasoning `SF-1` had to be AMENDED into on the turn-loop track: `crates/dp` has no database, its `WriteBackend` has one implementation and nothing uses it, so an SDK-level function would be a facade over nothing. `dp-kernel::channel` is where the events are written and where the pool already lives. **Reversal trigger:** DP-Ch14 cross-node routing shipping, which is also what `TL-SDK-FACADE` waits on.

**`DF-3` · The TypeScript gateway consumer is OUT of scope.**
DP-Ch16 names it first, and it is a second language plus a transport plus an auth surface. The consumer this track satisfies is the one that exists: turn-boundary watchers, over the reader built here. **Reversal trigger:** the gateway growing a channel-subscribe endpoint.

**`DF-4` · No `impl DpClient`.**
There is no such type; the turn-loop audit established this and nothing has changed. Free functions / inherent methods on the type that owns the pool.

---

## 3 · THE BOARD

| # | row | done = |
|---|---|---|
| `D0` | this file + the audit | `phase0-reconcile-gate.py` passes on it, pasted |
| `D1` | **`ChannelEvent` trait + `DurableStreamItem`** — the typed shapes DP-Ch16 specifies | the types exist in non-comment source; a feature type implementing `ChannelEvent` round-trips through the decoder; unit tests pasted |
| `D2` | **the reader** — resume from a `channel_event_id`, read forward in `DP-A15` order | reads back events the writer committed, in order, with `writer_epoch`/`turn_number`/`causal_refs` intact; `from_event_id = 0` means "from the beginning of retention"; live PG test, pasted |
| `D3` | **end to end against `T3`'s output** | a subscriber resumes a channel and receives the `channel.turn_boundary` events `advance_turn` commits — **state explicitly whether it is a live test or a drill**; a drill does not satisfy the goal |
| `D4` | **oracle for `14_durable_subscribe`** | the `NO_PRODUCER` shrink arm FIRES and is PAID; the doc enters the coverable denominator with a live asserting oracle; bitten per the six steps; baseline 17/17 → 18/18 |
| `D5` | **full verification** | `cargo test --workspace` and a **detached** `--run-all`, both green, REAL exit codes pasted |

---

## 4 · OPEN, each with a trigger

| id | what | trigger |
|---|---|---|
| `DS-REDIS-TAIL` | DP-Ch17's live tail is unbuilt (`DF-1`); `dp:events:*` exists in four documents and no source file | a measured latency requirement, or the gateway fan-out |
| `DS-OUTBOX-RELAY` | the I13 outbox row is written by `ChannelWriter::append` and no relay turns it into a channel stream entry. `services/meta-outbox-relay` exists but prunes; it does not publish `dp:events:*` | `DS-REDIS-TAIL` |
| `DS-GATEWAY` | DP-Ch16's first-named consumer is the TS gateway and nothing there subscribes to a channel (`DF-3`) | the gateway growing the endpoint |
| `DS-CH21-STEP8` | DP-Ch21 step 8 instructs the writer to XADD, which the shipped writer does not do. Not a defect — DP-Ch17 sanctions the outbox branch — but the two documents read as contradictory to anyone who opens only one | `DS-REDIS-TAIL` closing, at which point step 8 becomes true and should say so |

---

## 5 · REGISTERS — decisions · parked · debt · drift

**An empty drift log is not evidence of a clean run** (§0.6d).

**`DSD-1` (2026-08-12) — Phase 0 found the subject missing, not the implementation.**
The plan going in was *"build DP-Ch16's subscribe"*. The audit's second question showed that the store it subscribes to has never existed in any language, while the tier DP-Ch17 calls **canonical** is fully shipped and already carries every column the reader needs. The work is therefore a reader over Postgres plus a deferred relay — smaller, better defined, and pointed at the half that exists. **Three tracks in a row, Phase 0 has changed the shape of the work before a line was written.**
