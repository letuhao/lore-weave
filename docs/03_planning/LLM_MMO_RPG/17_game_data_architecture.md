# 17 — Game Data Architecture (flows)

> **✅ CORRECTED 2026-07-26 — correction pass applied** (per the same-day banner +
> [`19_reconciliation_register.md`](19_reconciliation_register.md) §12b). What changed:
>
> - **§5 R1** — `ReadFreshness` (GDA-A5) **withdrawn**: reads use the DP-K4/K5 primitives at their
>   tier's locked coherency (DP-X1); read-your-writes is the existing `wait_for` `CausalityToken`
>   param; the `Cached`/`Eventual` split deleted (DP-X3 fallthrough is automatic). **GDA-A6
>   rewritten** around the LOCKED `t1_read` primitive; only the island-memory half survives.
> - **§4 B4** — the missing-budget claim was false: DP-Ch33 locks wakeup ≤2 s p99, DP-S2 locks
>   cold-start ≤10 s; GDA-Q1 rescoped to the W1/wakeup **composition** question.
> - **§4 B5** — GDA-D8 rewritten to **ack-early, not skip** (DP-Ch31 conformant); resume corrected
>   to the DP-Ch18 per-channel `from_tokens` map; W1 gains DTO names (`InventorySummary`,
>   `RosterEntry`); W0 gains `client_protocol` + upcast-before-fanout; transport = Colyseus
>   (REC-71/72/73/75).
> - **§5 R2** — step 5 durability re-stated over DP primitives + the `02_storage` outbox contract
>   (DP-A8), never raw SQL (DP-R3); GDA-D10 rescoped to **T3**; ack-by-tier partition (GDA-F11)
>   added at step 5b.
> - **§4 B1** — step 2.5 `DpClient::connect` tier-policy fetch added (DP-A2/DP-K10); GDA-A2 halved
>   (fencing survives; DP-Ch11 MAX-seed + DP-F2/F4 catchup added).
> - **§2** Redis miscitation fixed (three roles, five table rows). **§8** corrected to the four
>   affected LOCKED files; all remaining LOCKED-file changes ride the **REC-53/58/65/68 AMEND
>   bundle**, except those these corrections made unnecessary (ReadFreshness withdrawn → `04b`
>   needs no change; GDA-D13 hotset still needs `06_cache_coherency`).
>
> No LOCKED `06_data_plane/` file was touched; every fix that requires one is explicitly marked
> **pending AMEND**.

> **Status:** DRAFT — 2026-07-26. Opens **AUD-F15**, and closes its design half the same day.
> **Prefix:** `GDA-*` (registered 2026-07-26; axioms `GDA-A1..A9`, decisions `GDA-D1..D18`, findings
> `GDA-F1..F10` — **all resolved**, §7 — questions `GDA-Q1..Q3`; flows `B1..B5` / `R1..R8` / `L1..L5`).
>
> **Read §7 first if you only read one section.** The audit below is why this doc exists; §7 is what
> it decided.
>
> **The question this answers:** *"do we have a game data architecture, and what loads from where at
> boot?"*
>
> **Short answer: we have ~80 documents of data architecture and zero end-to-end flows.**
> `06_data_plane/` (25 files, LOCKED) · `02_storage/` (40+) · `07_event_model/` (15) specify tiers,
> kernel primitives, cache coherency, channel ordering, failure/recovery, event taxonomy, validators
> and replay in unusual depth. **Not one document traces a single request from trigger to storage and
> back.** `docs/DATA_ARCHITECTURE.md` has a "Major data flows" section with 7 flows — all of them
> novel-platform (chapter save, translation, search, RAG chat, wiki, enrichment, eval). Its Living
> Worlds section is a pointer to `06_data_plane/_index.md`. The game has **zero** documented flows.
>
> **This is the third instance of the same inversion** `12_module_coverage_audit.md` §4 named: depth
> is inversely correlated with proximity to the thing a player touches. First it was play-loop
> modules; then it was the manifest (§16, which had 64 fields and no loader); now it is the data
> layer — every layer specified, no path through them.
>
> **Composing the flows found nine gaps and conflicts** between layers that each read as correct in
> isolation. Two were load-bearing: `02_storage`'s write path **contradicts** the sim-core /
> commit-service model (GDA-F2), and there were **two incompatible reality-seeding designs** with two
> different owners (GDA-F6). **All nine are resolved in §7**; the four flows that had no design at all
> (process start · session join · read path · seeding) are designed in §4–§5.

---

## 1. What exists, and what this adds

| Layer | Where | Depth | What it does *not* say |
|---|---|---|---|
| Kernel access contract | [`06_data_plane/`](06_data_plane/_index.md) — DP-A/T/K/C/X/F/R/S/Ch, 25 files LOCKED | very deep | in what **order** primitives are called, by whom, for a given user action |
| Durable storage | [`02_storage/`](02_storage/_index.md) — aggregates, envelope, projections, snapshots, DB-per-instance, meta registry | very deep | the read path (§7 GDA-F3) |
| Event model | [`07_event_model/`](07_event_model/_index.md) — taxonomy, producers, validators, replay, versioning | very deep | which events a given flow emits, in sequence |
| Simulation runtime | [`13`](13_simulation_loop.md) · [`14`](14_sim_core_spec.md) | deep | where its state comes from on first load |
| Commit authority | [`15`](15_commit_service.md) | deep | — (it is the closest thing to a flow doc we have) |
| Rules loading | [`16`](16_ruleset_loader_and_registry.md) · [`16a`](16a_ruleset_field_classification.md) | deep | — (added 2026-07-26; had no data-architecture doc to slot into — GDA-F9) |
| **Flows** | **this document** | — | — |

This doc **composes**; it does not re-specify. Where a step is governed by a locked ID, the ID is
cited and the locked spec wins. Where a step has **no owner**, it is marked **⛔ GAP** inline — those
are the deliverable, not the prose around them.

---

## 2. The stores

What physically holds game data, and what is authoritative in each.

| Store | Holds | Authority | Lifetime |
|---|---|---|---|
| **Island memory** (`D::State` in `sim-core`) | live world state for one channel — entities, positions, encounter state | **authoritative while Hot** (SL/SC; DP-X1 T1: *"writer's in-memory is authoritative until next snapshot"*) | dies with the island |
| **`event_log`** (per-reality Postgres) | every committed event, ordered per channel by `UNIQUE(reality_id, channel_id, channel_event_id)` | **SSOT for history** | forever (archive at 90d) |
| **`aggregate_snapshots`** | periodic materialisations | *speed only* — never correctness (SC-A10) | prunable |
| **Projections** | denormalised read views | derived; rebuildable from `event_log` | rebuildable |
| **Redis** — three roles (DP-X2), five table rows *(miscitation "5 keyspaces" corrected 2026-07-26)* | cache · invalidation pub/sub · invalidation audit · **durable channel events** (`dp:events:*`, 7d/1M) · channel-tree + writer-audit deltas | cache is derived; `dp:events:*` is a **delivery** buffer with Postgres catchup (DP-Ch17) | 7 days |
| **Meta registry DB** | reality lifecycle, DB routing, writer/epoch assignment, capacity | **SSOT for topology** | forever |
| **MinIO** | archived realities, assets | archive | forever |
| **Ruleset store** (§16) | resolved, content-addressed rulesets | **SSOT for rules** | never pruned while referenced |

> **GDA-A1 — The event log is a sink, not the hot path.** Live state is in island memory; the log is
> written *behind* the simulation, not read *by* it per tick. This is stated as industry practice in
> [`12` §6](12_module_coverage_audit.md) and assumed throughout `13`/`14` — and it is exactly what
> `02_storage` §4.4/§4.6 contradict (GDA-F2).
>
> **Tier partition added 2026-07-26 (GDA-F11):** as first written this axiom was tier-blind. Island
> memory is authoritative **for state** at every tier — but the **ACK time is tier-determined**:
> T1 acks at R2 step 4 (island apply), T2 acks on cache+outbox (DP-T2), T3 acks only after
> invalidation fan-out (DP-T3). See §5 R2 step 5b.

---

## 3. Six load levels

"What loads at boot" is six different questions, because there are six independent cold-starts. Each
has a different trigger, owner, budget, and blast radius.

| # | Level | Trigger | Frequency | Blocking? |
|---|---|---|---|---|
| **B1** | **Process start** — a game node comes up | deploy / scale-out / crash | rare | blocks that node |
| **B2** | **Reality creation** — a reality first exists | author creates / forks | once per reality | async, progress-reported |
| **B3** | **Reality warm** — `frozen → active` | first player after dormancy | per dormancy cycle | non-blocking (DP-X3) |
| **B4** | **Channel Cold→Hot** — an island spawns | PC enters a Cold cell | constant | blocks that entry |
| **B5** | **Session join** — a player connects | login / reconnect | constant | blocks that player |

The user-visible latency of "log in and play" is **B3 + B4 + B5**, and only B3 has a stated budget.

---

## 4. Boot flows

### B1 — Process start (GDA-F4 — DESIGNED)

```
Joining ──(CP reachable + assignments received)──► Serving ──(drain)──► Leaving
   │
   └──(CP unreachable)──► Joining (retry, backoff) — NEVER Serving
```

| # | Step | Source | Mechanism |
|---|---|---|---|
| 1 | load platform config | env / deployment | `multiverse.*` + the 5 ops knobs RLS-D13 moved out of the manifest |
| 2 | open store handles | — | Postgres pools, Redis, MinIO. **No game data read.** |
| 2.5 | **`DpClient::connect` — fetch tier policy** *(added 2026-07-26)* | CP | DP-A2 / DP-K10 — **mandatory**; a node that has not fetched the tier policy cannot legally read or write |
| 3 | register with CP, receive channel assignments **+ epoch tokens** | **meta registry** | DP-Ch13 |
| 4 | subscribe to `dp:channel_changes:{reality_id}` | Redis Stream | DP-Ch3 |
| 5 | mark `Serving`; island manager begins accepting Cold→Hot requests | — | SC-A7 |

> **GDA-A2 (corrected 2026-07-26) — A node never assumes ownership; the CP grants it.** Start-up is
> idempotent against a crashed predecessor's *writes* by construction: the predecessor's epoch token
> is already stale, and DP-A16 fences its `event_log` inserts at the DB — the **fencing half of this
> axiom survives**. ~~No startup-time reconciliation is needed~~ — that half was wrong: takeover
> **does** run the locked reconciliation steps. The `channel_event_id` counter is **seeded from the
> `MAX` query at takeover** (DP-Ch11), and DP-F2/F4 mandate **T1 reload + invalidation-stream
> catchup** before serving. Fencing prevents the double-write; these steps are what preserve DP-A15
> gaplessness.

> **GDA-D1 — `Joining` is a distinct state from CP-outage degraded mode, and it refuses traffic.**
> `DP-F*` degraded mode lets a *running* node continue on assignments it already holds. A node that
> has never reached the CP holds **none**, so "continue on what you have" is not available to it.
> Conflating them would let a fresh node serve with an empty assignment set and silently answer
> nothing. It retries with backoff and stays out of the pool.

> **GDA-D2 — Rulesets resolve lazily, at first island (§16 B4 step 4), never at node start.** A node
> may host islands from dozens of realities and cannot know which at step 3. Eager resolution would
> pay for realities that never wake. The registry's digest interning (RLS-A11) already makes the
> lazy path cheap on the second island.

### B2 — Reality creation ⚠ **two incompatible designs (GDA-F6)**

The lifecycle is specified: `provisioning` → `seeding` → `active`, CAS-protected, resumable,
progress-reported ([`02_storage/HMP_followups.md` §12R.2](02_storage/HMP_followups.md)).

The **seeding step has two mutually exclusive designs**, neither aware of the other:

| | §12R.2 bootstrap worker | RealityBootstrapper (feature layer) |
|---|---|---|
| **Owner** | `migration-orchestrator` (*"folded into existing service… avoids service proliferation"*) | *"DP-Internal RealityBootstrapper (Synthetic actor)"* |
| **Source** | the **book**: *"FOR each book region → create region aggregate; FOR each glossary entity marked player-relevant → create `npc_proxy`"* | the **RealityManifest**: `places`, `map_layout`, `canonical_actors`, `continent_geometries` |
| **Emits** | aggregates, directly | events — `PlaceBorn`, `LayoutBorn`, `TilemapBorn`, `GeographyBorn`, `EntityBorn` |
| **Vocabulary** | `region`, `npc_proxy` | `place`, `map_layout`, `actor_core`, `channel` |
| **Named in** | `02_storage` | PF_001, MAP_001, TMP_001, GEO_001, EF_001, ACT_001 — six features |

These are not two views of one process. They read different inputs, write different shapes, and run
in different services. The feature-layer version is the one six features depend on and the one §16
§5.1 just assigned seed-time validation to (RLS-D23); §12R.2 is the one with the lifecycle state
machine, the checkpointing, the resumability and the locale-translation step. **Each has what the
other is missing.**

#### Resolution (GDA-F6)

> **GDA-A3 — `RealityBootstrapper` is a *role*, hosted by the §12R.2 seeding worker.** Exactly the
> CS-A1 pattern: `commit-service` is *"a ROLE co-located on the channel's writer node, not a standalone
> microservice."* Same move here. The worker keeps its lifecycle state machine, CAS protection,
> checkpointing, resumability and progress metric; the Bootstrapper contributes *what to emit*. One
> service, one actor identity, both halves preserved.

> **GDA-D3 — The `RealityManifest` is the only seeding input. The book is upstream of the manifest,
> never a second input to seeding.** §12R.2 reads the book directly (*"FOR each book region…"*,
> *"FOR each glossary entity marked player-relevant…"*), which predates the manifest's existence.
> Under §16 the ingestion pipeline turns the book into a manifest, and seeding consumes only that —
> otherwise there are two paths from book to world state that can disagree, and the digest pins
> neither.

> **GDA-D4 — Seeding emits events, never direct aggregate writes.** `PlaceBorn` / `LayoutBorn` /
> `TilemapBorn` / `GeographyBorn` / `EntityBorn`, per EVT-A3 (*"all canonical state changes flow
> through validated events"*). §12R.2's *"create region aggregate"* / *"create `npc_proxy`"* would
> bypass the log and leave a reality whose first state has no causal record — unreplayable from
> t=0, which defeats the same spine RLS-A13 protects.

> **GDA-D5 — The locale-translation step survives, re-homed.** §12R.2's *"if `reality.locale ≠
> book.source_locale`, invoke translation-service"* has no equivalent in the feature-layer story and
> is genuinely needed. Under the manifest it becomes precise: **populate `I18nBundle.translations`
> for the target locale** on manifest-derived user-facing strings. The English `default` is already
> required (RES_001 §2), so this fills a gap rather than replacing anything, and a failure degrades
> to `default` instead of failing the seed.

**Reconciled B2:**

```
provisioning   CREATE DATABASE + extensions + migrations                    (<30s, 12R.2)
     ↓ CAS
seeding        1. resolve ruleset, validate, digest, store      §16 §12 · RLS-A13
               2. load-time validators                          RLS-A10
               3. emit *Born events from manifest WorldContent  GDA-D4, checkpoint every 100
               4. populate I18nBundle.translations if locale mismatch   GDA-D5
               5. seed-time validators (PO-C2/C3, spawn_cell)   RLS-D23
               6. snapshot initial state                        12R.2
     ↓ CAS  (any step fails → stays `seeding`, resumable; never half-`active`)
active         ready for play
```

Ordering is forced, not chosen: rules before content (content validators reference rules), content
before seed-time validators (they reference content), everything before the snapshot.

> **Detail design: [`18_reality_bootstrap.md`](18_reality_bootstrap.md)** (`RBS-*`, 2026-07-26) —
> three seed sources on one lifecycle · the reality-scoped writer lease that answers "who writes the
> events that create the channels" (RBS-A3) · the 8-phase emission DAG · deterministic idempotency
> keys making resume correct rather than merely fast · two failure classes (transient resumes,
> **manifest-defect is terminal** — conflating them yields a reality stuck in `seeding` forever) ·
> and why `commit-service` needs **no bootstrap mode**. Composing the DAG found **RBS-F1: a circular
> dependency in the `*Born` order shipping today** — `PlaceBorn` is specified to emit `MemberJoined`
> for actors that cannot exist yet, since `spawn_cell` requires places first.

### B3 — Reality warm (`frozen → active`)

The best-specified boot level. On the transition the CP signals pre-population of the **reality
hotset** (DP-X3): a per-reality learned set, `reality_hotset(reality_id, aggregate_type, priority)`,
derived from the last 24h of active metrics; V1/V2 use a static default and learning is V3. **Pre-warm
runs in parallel with first-session bind and does not block the first player.**

Residual risk is stated rather than solved: *"Cold cache + genuine N-node thundering herd on first
read after a reality warms up… mitigated by hotset pre-warm + singleflight, but not fully eliminated"*
(DP-X4), with a V2 benchmark target of <2× sustained-QPS spike.

⚠ The V1 static hotset is **`player + session + region` aggregates** — see GDA-F8: `region` is not a
vocabulary the feature layer uses.

### B4 — Channel Cold→Hot (island spawn)

Composed from three specs that agree:

1. PC enters a Cold cell → island manager creates a cell island (SC-A7 — `sim-core` *requests*, the
   host *creates*).
2. Channel lifecycle `Dormant → Active` (DP-Ch31..Ch37).
3. State hydration = `dp-kernel::load_aggregate` — latest snapshot + delta events (the mechanism
   ~~`15`~~ **`14`** §10.5 step 3 already names for crash recovery — *same mis-citation as R3's,
   corrected 2026-07-26 with REC-62*).
4. Ruleset: `Arc<RealityRuleset>` from the registry by `(reality_id, epoch)`, interned by digest
   (RLS-A11/A12). WorldContent for **this channel only** (RLS-A1).
5. Per-cell rules (`combat_safety`, `time_flow_rate_override`) arrive from the **`place` aggregate**,
   not the manifest — §16 §2.1.

~~⛔ No stated latency budget for B4~~ — **corrected 2026-07-26: the budget exists and this doc
missed it.** **DP-Ch33 locks wakeup at ≤2 s p99** (in `17_channel_lifecycle.md`, the very file step
2 cites) and **DP-S2 locks reality cold-start at ≤10 s**. **GDA-Q1 rescopes** accordingly: the open
question is no longer "set a budget" but whether the proposed **W1 ≤500 ms must compose with the
≤2 s wakeup** it can sit behind — a measurement question, resolved at the S1 prototype.

### B5 — Session join (GDA-F5 — DESIGNED)

`services/game-server` is *"a hardened WebSocket edge with an echo room in it"* — auth, tickets,
rate-limit, audit, `EchoRoom`, 859 LOC. Transport is specified (PRR-20, RTM); DP-Ch16..Ch20 supply
durable subscribe with per-channel resume and Postgres catchup. What was missing is the **payload and
its ordering**.

> **Transport (settled 2026-07-26, REC-71):** **Colyseus carries the game** — W0/W1/W2,
> `turn.outcome`, the patch broadcast and the event stream all ride the game-server room protocol;
> the gateway WS remains platform/chat only (PRR-20 already sanctioned the second entry point).

> **GDA-A4 — Join is three waves, ordered by what the client cannot render without.** Not one
> snapshot. A single blocking payload would put the ruleset, the history and the neighbour cells on
> the critical path of the first frame, none of which the first frame needs.

| Wave | Budget | Contents | Sourced from |
|---|---|---|---|
| **W0 — bind ack** | ≤100 ms | session id · capability token (DP-K9) · `reality_id` · `channel_id` · `ruleset_digest` · `from_tokens: HashMap<ChannelId, u64>` (the **DP-Ch18 per-channel resume map** — the singular `resume_token` was wrong; corrected 2026-07-26, REC-71/72) · `client_protocol: u16` (REC-75) | meta registry · CP |
| **W1 — first frame** | ≤500 ms | own PC: `actor_core`, stat block (DF7), `vital_pool`, `actor_status`, **`InventorySummary`** (renderable client DTO — the ITM-A9 prompt digest keeps its LLM job; REC-73) · cell: `place`, `cell_scene_layout`, `tilemap_view`, entity roster as **`RosterEntry`** DTOs (named 2026-07-26, REC-73) · active `combat_session` if any | island memory if Hot (T1); else the R1 ladder |
| **W2 — streamed** | best-effort | channel history (last N turns) · ruleset client-subset · full inventory · adjacent-cell previews · i18n bundles beyond active locale | projections · ruleset store |

> **W1 ships a client DTO layer, not aggregates** (REC-73 generalized), and per REC-75 the server
> **upcasts events to the latest schema before fanout** — `client_protocol` in W0 is what makes
> that negotiable; the client never sees mixed schema versions.

> **GDA-D6 — The client receives a *ruleset subset*, keyed by digest and cached client-side across
> sessions.** The resolved ruleset is ~90 KB (§16a §5) and mostly server-only — merge strategies,
> training rules, spawn tables. The client needs render-and-label data: stat slot names and units,
> `item_defs` for items it can see, i18n bundles for the active locale, tier names. Because the
> digest is content-addressed (RLS-A13), the client can cache by digest and skip W2 entirely on
> re-join to an unchanged reality — the third payoff of content-addressing, after interning and
> replay.

> **GDA-D7 — Reconnect is W0 + catch-up, never W1.** The client presents its `from_tokens` map (one
> resume point per channel — DP-Ch18; corrected from a singular token 2026-07-26, REC-71/72); the
> server replays each durable channel stream from its token (DP-Ch16..Ch20, monotonic and gap-free).
> W1 is re-sent **only** when a token is older than the Redis retention window (7d / 1M entries,
> DP-X2) and Postgres catchup would exceed the W1 budget — at which point a fresh W1 is strictly
> cheaper than a long replay.

> **GDA-D8 (rewritten 2026-07-26) — Join acks early; it never *skips* the Cold→Hot.** As first
> written ("join must not force a Cold→Hot") this rewrote a LOCKED transition: **DP-Ch31 locks
> `Dormant → Active` as triggered by *"first `bind_session` to this channel"***, with DP-Ch33
> sequencing the wakeup. Conformant form: `bind_session` **does** trigger Dormant→Active; the W0
> ack returns fast while the wakeup proceeds, and W1 follows on Hot **within the ≤2 s DP-Ch33
> wakeup budget** — **ack-early, not skip**. The intent survives (the player never stares at a
> blocked socket); the mechanism is the locked one.

⛔ Residual (rescoped 2026-07-26): the **W1 ≤500 ms budget is proposed, not measured**, and it must
**compose** with B3 pre-warm and the ≤2 s DP-Ch33 wakeup it can sit behind. Recorded as **GDA-Q1**;
it is a measurement question, not a design one, and resolvable at the S1 prototype.

---

## 5. Runtime flows

### R1 — Read path (GDA-F3 — DESIGNED)

`02_storage` §4.4 documents the **write** path. There was **no read-path section anywhere** — a
striking asymmetry for a system whose founding premise is *"event-sourcing reads are expensive"*
([`06_data_plane/_index.md`](06_data_plane/_index.md)).

Every rung was already locked. What was missing is the **ladder** and, more importantly, **a way for
a caller to say which rung is acceptable**:

```
rung 0  island memory (T1)     authoritative while Hot    ~0
rung 1  Redis GET               dp::cache_key! · DP-X3     ≤10 ms
rung 2  projection (Postgres)   DP-X3                      ≤50 ms
rung 3  load_aggregate          snapshot + delta events    unbounded
```

> **GDA-A5 (superseded 2026-07-26 — `ReadFreshness` withdrawn).** As first written this axiom
> invented a per-call freshness enum, which DP-X1 prohibits outright (*"there is no runtime flag to
> upgrade coherency without upgrading tier"*; DP-A9 concurs). The tier-conformant statement:
>
> - **Reads use the DP-K4/K5 primitives at their tier's locked coherency (DP-X1).** The entry rung
>   is a property of the aggregate's **tier**, never a caller parameter.
> - **Read-your-writes already exists** — DP-K4's `wait_for: Option<&CausalityToken>` (DP-A19). A
>   client re-reading after its own turn passes its token; nothing new ships.
> - **The `Cached`/`Eventual` split is deleted** — DP-X3's cache→projection fallthrough is
>   automatic, and the two classes were indistinguishable under it.
> - **Rung 3 (`load_aggregate`) remains sanctioned for B4 island hydration only** (GDA-D9
>   unchanged).
>
> The ladder above survives as a *description* of where a read can land; what is withdrawn is the
> caller-chosen class. (The R8 table's "Freshness" column now reads as descriptive coherency labels
> for the primitive used, not values of an API parameter.)

> **GDA-A6 (rewritten 2026-07-26) — Non-owner T1 reads use the LOCKED `t1_read` primitive; the
> island-memory copy is never remotely readable.** As first written ("there is no non-owner T1
> read") this axiom deleted three locked contracts: `t1_read(reality_id, aggregate_type,
> aggregate_id)` is a locked DP-T1 primitive, served from **Redis at ≤10 ms p99** (DP-S4), with its
> own **DP-X9** cross-node coherency row. What *survives* is the island half: no island — and no
> remote caller — ever reads another island's in-process memory (SL: *"no island reads another
> island's state. Ever."*; DP-A16 states the write half). **Authoritative-class reads are
> island-local only**; a non-owner needing the T1 value either calls `t1_read` and gets the tier's
> locked coherency, or sends a **cross-island message** (R4) when it needs the value at a tick
> boundary.

> **GDA-D9 — Rung 3 is never on a player-facing path.** `load_aggregate` is unbounded by
> construction. Reaching it during a turn means a projection is missing or rebuilding, which is an
> **operational** condition (L3), not a slow read: it is reported, not absorbed. B4 island hydration
> is the one sanctioned rung-3 caller, and it is not player-facing because GDA-D8 keeps island spawn
> off the join ack.

### R2 — Turn commit (write path) ⚠ **the documented one is stale (GDA-F2)**

`02_storage` §4.4 describes: validate against projection → `BEGIN` → `SELECT … FOR UPDATE` on
`aggregate_version_index` → insert events → **update projections in the same transaction** (§4.6:
*"V1 decision: synchronous, in-transaction"*) → `LISTEN/NOTIFY` → stream consumer broadcasts.

**That is a pre-sim-core design and it contradicts the current one in three places:**

| §4.4 / §4.6 says | The current model says |
|---|---|
| the command handler writes directly, in a DB transaction | the **island** is the writer (SC-A4 §5.1); `commit-service` wraps `sim-core` on both sides (CS-A2) |
| validate against a **projection** read | preconditions re-validated **at step time, never at admission** (SC/§5); admission is the EVT-V1 pipeline (CS-A3) |
| projections update **in the same transaction** — reads strongly consistent | live state is island memory; the log is a **sink** (GDA-A1) |

Both descriptions are internally coherent. Only one can be built. The newer model is the one `13`,
`14`, `15` and `16` all assume, and the one AUD-F7's industry cross-check endorses.

#### The current write path (GDA-F2 — RESOLVED)

```
 1  player input           game-server WS edge · ticket + rate-limit + audit   (PRR-20)
 2  proposal bus           Redis Streams XREADGROUP, per-cell                  (15 §2)
 3  ADMISSION              EVT-L3 idempotency dedup
    commit-service         EVT-V5 hot-path gates  (<10 ms, reject-only, every path)
                           EVT-V1 validator pipeline, category-declared subset (CS-D9)
 4  sim-core step          seen-set dedup (I2) → preconditions re-validated NOW (SC-A1)
                           → Domain::apply(state, rules, input, rng)           (RLS-A12)
                           → Vec<Event>   · island memory is now authoritative
                             for STATE — the ACK time is tier-determined (5b)
 5  DURABILITY             DP commit primitive + the 02_storage outbox contract (DP-A8)
    commit-service         — never raw SQL (DP-R3/DP-A1); epoch token required (DP-A16);
                           UNIQUE(reality_id, channel_id, channel_event_id) enforced
                           by the primitive
 5b ACK — by tier          T1: already acked at step 4 (island apply)          (GDA-F11)
    (added 2026-07-26)     T2: ack on cache+outbox (DP-T2); projection catches up async
                           T3: ack only after invalidation fan-out; sync in-transaction
                               projection is the T3 path                       (GDA-D10)
 6  publish                outbox → Redis Stream dp:events:{reality}:{channel}
 7  broadcast              durable subscribe → Colyseus patch → clients        (R5)
```

> **GDA-D10 — §4.6's synchronous in-transaction projection survives; §4.4's sequence does not.**
> The two halves of the old design are separable and it is worth being precise about which is
> obsolete. What changed is **who writes and when validation happens** — the island is the writer,
> and preconditions re-validate at step time rather than as a projection read at admission. Whether
> the projection updates in the same transaction as the event insert is an **independent** choice,
> and §4.6's reasoning still holds at V1 turn rates: strong reads, no lag window, no stale-read bug
> class. It re-homes from the command handler to `commit-service` step 5. §4.6's V3 async escape
> hatch survives with it.
>
> **Rescoped 2026-07-26 (tier):** as first written GDA-D10 was tier-blind. The sync in-transaction
> projection is the **T3 path** — it is DP-T3's own invalidate-before-ack, re-homed. **T2 keeps
> ack-on-cache+outbox (DP-T2, <5 ms ack; projection catches up async)**; applying the sync
> projection to every write would make T2 pay the T3 ack cost, against DP-S5's 500/s vs 50/s
> sizing. The write path's tier column is step 5b above.

> **GDA-D11 — `02_storage` §4.4 and §4.6 get dated superseding notes, not deletion.** They are the
> only end-to-end write flow in the repo and currently read as authoritative; deleting them loses the
> optimistic-concurrency and sync-projection reasoning, which is still good. The note points here and
> marks §4.4's *sequence* superseded while §4.6's *decision* is retained per GDA-D10.

Note what did **not** change: optimistic concurrency on `aggregate_version` (§8.1) still applies at
step 5, and `UNIQUE(reality_id, channel_id, channel_event_id)` is the DB-level expression of the same
per-island total order SL-A9 asserts at the simulation layer. The two models agree on far more than
they disagree on — which is why the conflict survived unnoticed.

### R3 — LLM decision round-trip

Well specified across layers and worth recording as the model flow: `Driver::decide` returns a
**handle, never a `Decision`** — dispatch, never await (SL-A4, `14` §11); the result arrives later as
ordinary stamped ingress; a lost dispatch is **self-healing** because the actor sits `AwaitingDecision`
with no outstanding call, its deadline fires, and AGT-A2 fallback commits (~~`15` §10.5~~ **`14` §10.5**
— ⚠ CORRECTED 2026-07-26 (REC-62): the cited section lives in [`14_sim_core_spec.md`](14_sim_core_spec.md),
not `15`). Proposals
route through the LLM proposal bus ([`07_event_model/07`](07_event_model/07_llm_proposal_bus.md)) and
are admitted by `commit-service` under the origin-class subset (CS-D9).

### R4 — Cross-island message

`IslandMessage { from, to, causality, delivery_id, payload }`, delivered into the target's ingress at
its **next tick** (+1 tick, SL-A10); **no island ever reads another's state**; a missing target
discards with a recorded reason, never an error. Transport is IPC (~1 ms, SL-D20), mitigated by
spatial co-location (SL-D20b).

### R5 — Broadcast to clients

`commit-service` durability → Redis Stream `dp:events:{reality_id}:{channel_id}` → durable subscribe
with resume token and Postgres catchup (DP-Ch16..Ch20) → Colyseus room patch → client. Redaction per
`RedactionPolicy` (DP-Ch43..Ch45). Bubble-up to parent channels via `BubbleUpAggregator`
(DP-Ch25..Ch30).

> **GDA-A7 — The Colyseus room holds no authority; it is a projection of the event stream.** The seam
> was unspecified, and the only answer consistent with RTM-A3 (*"the realtime layer never writes
> kernel state"*) is that room state is derived. On disagreement the **stream wins** and the room
> re-derives — there is no merge, because a merge would make the room a second writer. This makes
> `game-server` reverting to WS-edge-only (CS-A5/CS-D7) a completeness result rather than a scoping
> one: with no authority in the room, there is nothing left in it to be a game.

### R8 — Prompt assembly (GDA-F10 — DESIGNED)

**The highest-frequency read in the game** — every PC turn, every NPC reply, every Chorus batch — and
the only one that costs money per execution.

The governance is deep and the code exists. [`02_storage/S09`](02_storage/S09_prompt_assembly.md)
specifies **ten layers**: threat model · template registry · the fixed 8-section structure ·
capability/privacy filter · injection defense · token budget · PII redaction · replay audit ·
regression harness · canon markup. [`crates/dp-kernel/src/prompt.rs`](../../../crates/dp-kernel/src/prompt.rs)
is 797 LOC of `Composer`, `Intent`, `Section`, `PromptBundle`, `PromptAuditEntry`.

**And the code says explicitly where the hole is.** `PromptContext` is documented as *"WHO +
WHAT-FOR; **no body**"*; `PromptBundle` as *"**No body field**"*; `ResolvedContext` as *"filter chain
V1 = **empty**"*; and the three substantive gates — `NoopSafetyHooks`, `NoopConsentGate`,
`NoopTokenBudgetGate` — are all *"V1 default = Noop (Q-L6L-1)"*. `RetrievalHints` exists as a struct
with nowhere to come from. The Composer is a **validated shell built around a hole**, and the hole is
exactly this flow: nothing states which aggregate fills which section, at what freshness, or what
gives way when the budget binds.

#### Section → source

> **GDA-A9 — Prompt assembly is a pure read-composition. It writes nothing but its audit row.** Every
> source below is read-only, which is what makes assembly safe to speculatively prefetch (SL-A4's
> never-await discipline) and safe to retry after a budget failure.

| Section | Sources | Coherency (descriptive — GDA-A5's enum is withdrawn) | Budget class |
|---|---|---|---|
| `[SYSTEM]` | versioned template file, immutable at runtime | `Exact` | **fixed** |
| `[WORLD_CANON]` | `canon_cache` — L1 axiomatic + L2 seeded, filtered to actor-knowable | `Cached` (see GDA-D15) | **semi-elastic** — L2 sheds, L1 never |
| `[SESSION_STATE]` | `scene_state` · `participant_presence` · `cell_scene_layout` · turn order | `Authoritative` if island-local, else `Cached` | **fixed** |
| `[ACTOR_CONTEXT]` | `actor_core` · DF7 stat block · `actor_progression_summary` · inventory **digest** (ITM-A9, ≤29 lines) · `actor_actor_opinion` · NPC_003 desires top-N | `Cached` | **semi-elastic** |
| `[MEMORY]` | `actor_session_memory` | `Cached` | **elastic** |
| `[HISTORY]` | recent channel events | `Eventual` | **elastic** |
| `[INSTRUCTION]` | template-owned | `Exact` | **fixed** |
| `[INPUT]` | the player's turn text | `Authoritative` | **fixed** |

> **GDA-D15 — `canon_cache`'s 60s TTL is *correct* here, and this is the symmetry worth naming.**
> RLS-D4 rejected that same cache for rules, because two islands resolving different `stat_slots`
> inside the TTL window diverge unreplayably. Prompt context is the opposite case: it is **advisory
> input to a generative call**, never an input to deterministic state transition. A 60-second-stale
> canon fact produces slightly dated flavour; a 60-second-stale stat slot produces a corrupt world.
> **Same cache, opposite verdicts, and the discriminator is whether the reader is deterministic.**

> **GDA-D16 — Retrieval is a distinct role from composition: the `ContextResolver`.** The Composer
> holds no body *by design*, so something must fetch. Making that the Composer's job would put I/O
> and freshness policy inside the component whose contract is template rendering and section-shape
> validation. `ContextResolver` owns the table above, honours `RetrievalHints`, and returns the
> populated `ResolvedContext` the filter chain (S09 12Y.5) then prunes. It is the natural owner of
> S09's currently-empty filter chain.

#### Budget: what gives way (GDA-D17)

S09 12Y.7 sets per-intent caps (`session_turn` 16K in / 4K out, `npc_reply` 12K/2K, …) and is
emphatic that over-budget **fails rather than silently truncating** — *"silent truncation would drop
canon facts unpredictably"* — with the caller expected to *"reduce K and retry."*

**It never says which K.** Left there, every call site invents its own answer, and the resulting
prompt composition is unreproducible across services.

> **GDA-D17 — The degradation ladder is declared, applied by the `ContextResolver`, and recorded in
> the audit row.** Shed in this order, by marginal narrative value per token, re-checking budget after
> each step:
>
> 1. **`[HISTORY]` depth** — oldest first. Recency dominates relevance in a turn-based scene.
> 2. **`[MEMORY]`** — lowest salience first.
> 3. **`[ACTOR_CONTEXT]` roster detail** — **reuse AIT_001 `tier_roster_caps`**, which already
>    specifies exactly this ladder (5 `FullPersona` → 8 `CondensedPersona` → 12 `SummaryLine` →
>    `OverflowFormat::Aggregate` *"…and N other patrons"*). It was written for prompt budget and is
>    already the right mechanism; nothing new needed.
> 4. **`[WORLD_CANON]` L2 facts** — least-recently-referenced first. **L1 is never shed.**
>
> **Fixed sections never shed.** If `[SYSTEM]` + `[INSTRUCTION]` + `[INPUT]` + `[SESSION_STATE]` + L1
> canon alone exceed the cap, assembly **fails** — and that is a genuine error, not a retrieval
> problem, because no amount of reducing K will fix it. It means the intent's cap is mis-set or the
> player's input is pathological.

Recording the applied ladder step in `prompt_audit` matters for the same reason S09's L8 replay audit
exists: without it, a prompt that degraded and a prompt that did not are indistinguishable after the
fact, and the quality regression is unattributable.

> **GDA-Q3 — Budget shares per section are unset.** The ladder says what sheds *first*; it does not
> say what each section gets when nothing needs shedding. Deliberately left open: the split is
> tuning, wants real transcripts, and hard-coding a guess now would be a number nobody could later
> justify. The ladder is the part that must be deterministic.

**Design ↔ code note:** S09 layers 4–7 (capability/privacy filter · injection defense · token budget ·
PII redaction) are all specified in detail and all currently **`Noop` in `prompt.rs`** per Q-L6L-1.
That is a legitimate V1 staging choice, but it means the prompt path has *no* enforcement today —
worth an explicit deferral row rather than living only in a doc-comment.

---

### R7 — Aggregate inventory and hotset (GDA-F7 / GDA-F8 — RESOLVED)

`02_storage` §5 defines four projections — PC, NPC, Region, WorldKV. The feature layer has since
declared far more, and **the registry for them already exists**:
[`_boundaries/01_feature_ownership_matrix.md`](_boundaries/01_feature_ownership_matrix.md) carries
**52 aggregate rows**, each with tier, scope and owning feature — `actor_core`, `entity_binding`,
`place`, `map_layout`, `tilemap_view`, `cell_scene_layout`, `actor_session_memory`,
`actor_faction_membership`, `world_stability`, `forge_audit_log`, and the rest.

> **GDA-D12 — The ownership matrix is the aggregate inventory SSOT. `02_storage` §5's four are
> *patterns*, not a catalogue.** They are still instructive as shapes — per-actor, per-NPC,
> per-region, world-KV — and each of the 52 is one of those shapes. They get a superseding pointer,
> like §4.4. **No new registry is created**; that would be a third place to drift.

> **GDA-D13 — DP-X3's V1 static hotset is re-stated in names that exist.** The current default,
> *"player + session + region aggregates"*, is the §5 vocabulary and would pre-warm nothing the
> feature layer reads. The V1 default becomes the **W1 first-frame set** (GDA-A4) — `actor_core` ·
> `entity_binding` · `place` · `cell_scene_layout` · `tilemap_view` · `vital_pool` ·
> `actor_status` · `actor_progression` — because "what the first frame needs" is exactly what
> pre-warm exists to have ready. B3 and B5 stop guessing separately at the same set.

### R6 — Ruleset epoch switch

`RulesetEpochActivated { reality_id, from_epoch, to_epoch, digest }` enters each affected island as an
ordinary `Producer::Admin` ingress item; applied between two `step()` calls; **no reality-wide
barrier** (RLS-D17); epoch monotonic per island (RLS-I1). Fully specified in §16 §9.

---

## 6. Lifecycle flows

| # | Flow | Status |
|---|---|---|
| **L1** | **Island dissolution** — 7 reasons, each with distinct pending-work and entity handling (`14` §10.1, modelled on Orleans `DeactivationReasonCode`); migration only at quiescence (SC-A3) | specified |
| **L2** | **Crash recovery** — CP detects writer death → new epoch token (DP-A16 *is* the fencing/split-brain guard) → rebuild via `load_aggregate` → PEL redelivery → EVT-L3 dedup. What is lost is enumerated (`14` §10.5) | specified |
| **L3** | **Projection rebuild** — [`02_storage/R02`](02_storage/R02_projection_rebuild.md); `crates/rebuilder` exists and the multi-aggregate failure was fixed via global-order replay | specified **+ built** |
| **L4** | **Fork** — events/projections fully specified ([`03_multiverse/03`](03_multiverse/03_fork_and_cascading.md)); **rules** specified 2026-07-26 (RLS-D10, copy the digest, never re-resolve) | specified |
| **L5** | **Freeze → archive → restore** | policy specified ([`03_multiverse/09`](03_multiverse/09_config_and_refs.md): 30d inactive → freeze, 90d frozen → MinIO); **flow designed below** |

### L5 — Freeze → archive → restore (DESIGNED)

The policy existed; the flow did not — including the question of how an archived reality is ever read
again, which nothing addressed.

```
active   ──30d no activity──►  frozen   ──90d frozen──►  archived  ──restore──► active
```

**Freeze** — islands dissolve with reason `Idle` (`14` §10.1: *"none expected"* pending work, unload,
re-spawn on demand); cache entries evicted; reality marked `frozen` in the meta registry; **no data
moves.** Freeze is reversible by definition — `frozen → active` is exactly B3, hotset pre-warm and
all.

**Archive** — `event_log` + `aggregate_snapshots` + projections → MinIO; reality DB dropped; meta
registry row **retained** with an archive pointer. The registry row is what keeps the reality
addressable; dropping it would orphan the objects.

> **GDA-A8 — Archive must include, or pin, the resolved ruleset.** RLS-A13 requires that a stored
> ruleset is *"never GC'd while any event references them"* — and an archived reality's events still
> reference theirs. Archiving the event log while letting the ruleset be pruned produces a restorable
> reality that **cannot be replayed**, which is the one thing archiving exists to prevent. Since
> rulesets are interned by digest across realities (RLS-A11), archive stores the **digest plus a
> refcount hold**, not a copy — a reality sharing a live preset's digest adds no bytes.

> **GDA-D14 — Restore is B2 with a different seed source.** `archived → provisioning → seeding →
> active`, where seeding replays the archived event log instead of emitting `*Born` from a manifest.
> The lifecycle machinery, CAS protection, checkpointing and resumability are all reused unchanged —
> the same GDA-A3 argument, one more time. Restore is therefore **not a new flow**, which is why it
> was easy to leave unwritten.

⛔ Residual: **who triggers restore** — the first read of an archived reality, or an explicit admin
action? A read-triggered restore puts a multi-minute provision-and-replay behind a user click.
Recorded as **GDA-Q2**; the conservative answer is explicit admin action with the read returning
`Unavailable{restorable}`, but it is a product call, not a technical one.

---

## 7. Resolution register

All nine resolved 2026-07-26. Axioms `GDA-A1..A7`, decisions `GDA-D1..D13`, one measurement question.

| ID | Finding | Resolution |
|---|---|---|
| **GDA-F1** | No end-to-end game data flow exists anywhere | **This document** — 6 boot levels, 16 flows |
| **GDA-F2** | `02_storage` §4.4/§4.6 write path contradicts sim-core / commit-service | **§5 R2.** Current 7-step path written. **GDA-D10** separates the two halves: §4.4's *sequence* is superseded (island is writer; preconditions at step time), §4.6's *decision* is **retained** (sync in-transaction projection, re-homed to commit-service step 5). **GDA-D11** — dated superseding notes, not deletion |
| **GDA-F3** | No read path | **§5 R1.** 4-rung ladder + **GDA-D9** rung 3 never player-facing. *(Corrected 2026-07-26: the `ReadFreshness` classes GDA-A5 first shipped are **withdrawn** — DP-X1 forbids caller-chosen coherency; GDA-A6 rewritten around the locked `t1_read`. See the corrected R1 text.)* |
| **GDA-F4** | No process-start spec | **§4 B1.** `Joining → Serving → Leaving`; **GDA-A2** the CP grants ownership so restart is idempotent via the existing epoch fence; **GDA-D1** `Joining` ≠ degraded mode and refuses traffic; **GDA-D2** rulesets resolve lazily |
| **GDA-F5** | No session-join data flow | **§4 B5.** **GDA-A4** three waves (W0 ack ≤100 ms · W1 first frame ≤500 ms · W2 streamed) + **GDA-D6** digest-keyed client ruleset subset, cacheable across sessions + **GDA-D7** reconnect is W0 + catch-up + **GDA-D8** join acks early on Cold→Hot *(rewritten 2026-07-26 — ack-early, not skip; DP-Ch31 conformant)* |
| **GDA-F6** | Two incompatible reality-seeding designs | **§4 B2.** **GDA-A3** `RealityBootstrapper` is a *role* hosted by the §12R.2 worker (the CS-A1 pattern) — both halves preserved; **GDA-D3** manifest is the only input; **GDA-D4** seeding emits events; **GDA-D5** locale translation survives as `I18nBundle.translations` population |
| **GDA-F7** | Storage ↔ feature vocabulary drift | **§5 R7. GDA-D12** — the ownership matrix already **is** the inventory (**52 aggregate rows**, tier + scope + owner). `02_storage` §5's four become *patterns* with a pointer. No new registry |
| **GDA-F8** | V1 hotset names aggregates that do not exist | **GDA-D13** — the hotset default becomes the **W1 first-frame set**, so B3 and B5 stop guessing separately at the same thing |
| **GDA-F9** | §16 had no data-architecture doc to slot into | This document is that home |
| **GDA-F11** | **The island model grants T1 coherency to T3 aggregates.** `13`/`14` make island memory authoritative while Hot, and this doc generalised that across all tiers. But DP-X1/DP-T3 lock *invalidate-before-ack* / *"no acknowledge until projection reflects write"* for **currency, trades, canon promotion, permission grants** — every one of which lives in island state. Nothing partitions island state by tier. **This is not a defect of this document; it is a real seam between the simulation model and the tier taxonomy**, and it was invisible until a flow tried to traverse both. | **Partition adopted doc-side 2026-07-26** (the candidate resolution, applied): the island stays authoritative for *state*, and **tier determines when the ack fires** — T1 at step 4, T2 on cache+outbox (DP-T2), T3 after invalidation fan-out (DP-T3). Written into GDA-A1 and R2 step 5b. **Residual:** the tier partition of *island state itself* still needs writing (SC owner), and any DP-side wording rides the **REC-53 AMEND bundle**. |
| **GDA-F10** | **No prompt-assembly data flow** — the highest-frequency read in the game and the only one that costs money per call. S09 has **10 governance layers** and `prompt.rs` has **797 LOC**, and the code names the hole itself: `PromptContext` is *"WHO + WHAT-FOR; **no body**"*, `ResolvedContext`'s filter chain is *"V1 = **empty**"*, `RetrievalHints` has nowhere to come from | **§5 R8.** Section→source table with a freshness class per source · **GDA-A9** assembly writes nothing but its audit row · **GDA-D15** `canon_cache`'s 60s TTL is *correct* here (the RLS-D4 symmetry — the discriminator is whether the reader is deterministic) · **GDA-D16** `ContextResolver` role, distinct from the Composer · **GDA-D17** declared degradation ladder reusing AIT_001 `tier_roster_caps`, L1 canon never shed, fixed sections never shed |

Also closed in passing: **GDA-A7** — the Colyseus room holds no authority and is a projection of the
event stream; on disagreement the stream wins. That seam was unspecified, and it makes
`game-server`'s reversion to WS-edge-only (CS-A5) a completeness result rather than a scoping one.

### Open

| ID | Question | Kind |
|---|---|---|
| **GDA-Q1** | The W1 ≤500 ms budget is **proposed, not measured**, and composes with B3 pre-warm and B4 island spawn — **neither of which is budgeted at all**, though B4 sits on the critical path of every cell transition. | measurement — resolvable at the S1 prototype |
| **GDA-Q2** | Who triggers **restore** of an archived reality — first read, or explicit admin action? Read-triggered puts a multi-minute provision-and-replay behind a user click. Conservative answer: admin action, with reads returning `Unavailable{restorable}`. | product |
| **GDA-Q3** | Per-section **budget shares** within an intent's cap. GDA-D17 fixes what sheds first; what each section gets when nothing needs shedding is tuning, and wants real transcripts rather than a guess nobody could later justify. | tuning |
| **GDA-D18** | **Deferral, not a question:** S09 layers 4–7 (capability/privacy filter · injection defense · token budget · PII redaction) are all specified and all **`Noop` in `prompt.rs`** (Q-L6L-1). Legitimate V1 staging, but it means the prompt path has **no enforcement today**. → needs a row in `docs/deferred/DEFERRED.md`, not just a doc-comment. | tracked deferral |

### The pattern

Every one of the nine was a **seam between two well-specified layers**, never a layer — the
predictable failure mode of designing bottom-up and never traversing, and the same shape as §16
(64 field specs, no loader) and AUD-F5/F6 (deep identity design, no items or stats).

And the §16 pattern repeated: **the resolutions kept turning out to be mechanisms that already
existed.** The ownership matrix was already the aggregate registry (F7). The epoch fence already
covered restart (F4). The CS-A1 role pattern already solved two-owners (F6). DP-Ch16's resume token
already distinguished reconnect from join (F5). Four of nine.

Two resolutions are worth flagging as *retentions* rather than replacements, because the instinct
when resolving a conflict is to pick a side: §4.6's synchronous projection decision **survives**
(GDA-D10) — only §4.4's sequence was actually wrong — and §12R.2's lifecycle machinery, checkpointing
and translation step **all survive** (GDA-A3), because the conflict was about ownership and input,
not about that machinery.

---

## 8. What this changes elsewhere

| Doc | Change | Gate |
|---|---|---|
| [`02_storage/00_overview_and_schema.md`](02_storage/00_overview_and_schema.md) | §4.4 dated superseding note → §5 R2 here (sequence obsolete). §4.6 note → **retained** per GDA-D10, re-homed to commit-service step 5. §5 note → GDA-D12, the four are patterns; inventory is the ownership matrix | storage owner |
| [`02_storage/HMP_followups.md`](02_storage/HMP_followups.md) §12R.2 | Bootstrap worker **hosts the `RealityBootstrapper` role** (GDA-A3); input becomes the manifest (GDA-D3); emits events (GDA-D4); translation step re-homed (GDA-D5). Lifecycle machinery unchanged | storage owner |
| [`06_data_plane/06_cache_coherency.md`](06_data_plane/06_cache_coherency.md) | DP-X3 V1 static hotset → the W1 set (GDA-D13) — still needed after the correction pass | DP owner (**LOCKED file** — **pending AMEND, REC-53 bundle**) |
| [`06_data_plane/04b_read_write.md`](06_data_plane/04b_read_write.md) | ~~Read primitives gain the `ReadFreshness` parameter (GDA-A5); non-owner T1 rule stated (GDA-A6)~~ **Withdrawn 2026-07-26** — `ReadFreshness` is withdrawn and GDA-A6 now conforms to the locked `t1_read`. **No 04b change needed.** | — |
| [`15_commit_service.md`](15_commit_service.md) | Step 5 owns the projection write (GDA-D10); cross-ref the R2 path | CS owner |
| [`14_sim_core_spec.md`](14_sim_core_spec.md) | Cross-ref GDA-A6 — the read half of *"no island reads another island's state"* | SC owner |
| [`_boundaries/01_feature_ownership_matrix.md`](_boundaries/01_feature_ownership_matrix.md) | Note that it **is** the aggregate inventory SSOT (GDA-D12) | lock |
| [`02_storage/S09_prompt_assembly.md`](02_storage/S09_prompt_assembly.md) | Cross-ref §5 R8: the section→source table, the `ContextResolver` role (GDA-D16), and the degradation ladder that answers 12Y.7's *"reduce K and retry"* — **which K** (GDA-D17) | storage owner |
| [`features/16_ai_tier/AIT_001_ai_tier_foundation.md`](features/16_ai_tier/AIT_001_ai_tier_foundation.md) | Note that `tier_roster_caps` **is** step 3 of the prompt degradation ladder — it was written for prompt budget and is now load-bearing for it by name | AIT owner |
| `docs/deferred/DEFERRED.md` | **GDA-D18** — S09 layers 4–7 are `Noop` in `prompt.rs` (Q-L6L-1): the prompt path has no capability/privacy, injection, budget or PII enforcement today | — |
| [`docs/DATA_ARCHITECTURE.md`](../../DATA_ARCHITECTURE.md) | §5 Living Worlds → point at this doc for game flows, not only at `06_data_plane/_index.md` | — |

~~**Two files are LOCKED** (`06_cache_coherency`, `04b_read_write`) and both changes are additive —
a new optional parameter and a corrected default. Neither alters an existing DP-X\* or DP-K\*
contract.~~ **Corrected 2026-07-26:** the sweep found **four** LOCKED files actually affected —
`03_tier_taxonomy`, `06_cache_coherency`, `08_scale_and_slos`, `17_channel_lifecycle` — plus DP-A9.
All remaining LOCKED-file changes are **pending-AMEND items in the REC-53 bundle**, **except** those
this correction pass made unnecessary: `ReadFreshness` is withdrawn, so **`04b_read_write` needs no
change at all**; the **GDA-D13 hotset default still needs `06_cache_coherency`**. The GDA-F11
ack-by-tier partition is what touches `03_tier_taxonomy`; the GDA-Q1 budget-composition note is
what touches `08_scale_and_slos` / `17_channel_lifecycle` if their SLO tables gain the join-path
composition row.

---

## 9. Build order

1. ~~**GDA-D11 superseding notes**~~ — ✅ **applied 2026-07-26** to `02_storage` §4.4 (⚠ sequence
   superseded) / §4.6 (✅ decision retained, re-homed) / §5 (⚠ patterns, not an inventory).
2. ~~**GDA-F6 seeding reconciliation**~~ — ✅ **detail-designed 2026-07-26**,
   [`18_reality_bootstrap.md`](18_reality_bootstrap.md). Outcome for AUD-F8: **`commit-service` needs
   no bootstrap mode** (RBS-A8). Remaining are three findings for other owners, one of them a
   CANDIDATE-LOCK correction (RBS-F1).
3. ~~**`ReadFreshness`** (GDA-A5) — one enum plus a parameter…~~ **Withdrawn 2026-07-26** — no enum
   ships; reads use the tier-locked DP-K4/K5 primitives plus the existing `wait_for` token
   (corrected §5 R1). Nothing to build.
4. **GDA-D13 hotset default** — one line, and it makes B3 pre-warm actually warm something.
5. **B5 session join** — the largest genuinely-new surface, and the one with a live budget question
   (GDA-Q1).
6. **B1 process start** — alongside `sim-core` S1.

Steps 1 and 4 are single editing passes. Nothing here contends with AUD-F8 for the critical path
except step 2, which unblocks it.
