# 08 — Realtime Movement & Presence Authority (DRAFT)

> **Status:** DRAFT — created 2026-06-20. Captures a gap opened by the medium correction
> ([`00_VISION.md` §0](00_VISION.md): the game is a rendered 2D/2.5D world with **near-realtime
> avatar movement**, not a text/turn-based MUD). The existing authority machinery is entirely
> **turn-based**; this doc specifies the missing **near-realtime movement & presence** authority
> layer and the seam where it hands off to the turn-based layer.
> **Not yet locked.** Contracts here are PROPOSED; they must claim a `_boundaries/` ownership
> lock and pass reconciliation before any `RTM-A*` axiom is locked. The `RTM-Q*` decisions
> (§7) are deferred by explicit user direction ("update the spec first, clear questions later").

---

## 1. Why this doc exists

The authority boundary for **state-changing actions** is already well designed and largely locked:

| Concern | Where (locked) |
|---|---|
| Client requests, trusted server authorizes | **DP-A6** — Python/LLM `produce: [Proposal]` only; Rust commit-service is the sole authoritative writer of `Submitted` (EVT-T1) |
| Validation gate | **EVT-V\*** validator pipeline (ordered, no-skip) |
| LLM cannot mutate state | **A5-D3** — *"state-changing actions MUST come from client `/verb` commands, NEVER from LLM tool calls"* |
| Combat authority | **COMB_001** — engine owns 100% of math, seeded RNG `(reality_id, turn_id, actor_id, action_idx, kind)`, replay-deterministic |
| Travel authority | **TVL_001** — `Travel:Initiate` validated (TVL-V1..V10), server-owned per-turn `TravelTick` |
| Public edge | **I1 / PRR-20** — api-gateway-bff, plus the Colyseus game-server WS as a sanctioned second entry |

**The gap:** every one of those routes through a **turn boundary** (`TurnEvent` → `dp::advance_turn`
→ `PL_001` turn). Even movement is turn-based: `TVL_001` is "pick a route, tick along it per
turn." That is a turn-based travel model. It is **not** an avatar walked around a tilemap in
near-realtime — which §0 of the vision now says the game is. Near-realtime movement & presence
has **no authority model**. The only adjacent item is `D-GAME-WS-EDGE-CONTROLS` (WS auth/rate-limit),
which is edge control, not movement validation or reconciliation.

This doc fills that gap without reopening the locked turn-based design.

---

## 2. Two authority cadences

| Layer | Cadence | What it governs | Authority model | Status |
|---|---|---|---|---|
| **Turn-based, event-sourced** | discrete turns | interactions, combat, all state mutation | Proposal → EVT-V\* validate → Submitted (DP-A6) | ✅ locked |
| **Realtime movement & presence** | near-realtime (~10 Hz) | avatar position, visible co-presence | client-predict → server-validate delta → reconcile | ⬅ **this doc** |

The realtime layer is **subordinate**: it never mutates kernel/aggregate state. It moves avatars
through space and renders co-presence; anything with game-state consequence (entering combat,
arriving somewhere that triggers a scene, picking something up) **crosses into the turn-based layer**
via the existing commit path (§5).

---

## 3. Proposed authority axioms (`RTM-A*`)

> PROPOSED — pending `_boundaries/` lock. Numbered in a new `RTM` namespace per the ID discipline
> ([`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)).

- **RTM-A1 — Position is ephemeral, server-authoritative runtime state.**
  Live position lives in the Colyseus room (+ Redis for cross-node presence), **never** in the
  canonical event log. This is deliberate: at ~10 Hz × N avatars, logging every position would
  detonate **R01 (event volume)**. Only *semantic transitions* (§5) become events.
  **Checkpoint clause:** position is nonetheless **periodically snapshotted** to durable store
  (~30 s / on region transition / on disconnect) for crash recovery — a *state snapshot*, not an
  event, so R01 is unaffected. This is standard MMO practice (position is "non-critical" data,
  flushed periodically, never per-tick) and maps onto the existing snapshot/projection machinery.

- **RTM-A2 — Every client movement is a *request*, validated and reconciled.**
  The game-server validates each movement delta against the **tilemap kernel**: walkability +
  max-speed-per-elapsed-tick + no-teleport/no-clip. Illegal → authoritative **snap-back**. Client
  prediction is provisional and always yields to server correction. (This is the realtime analogue
  of `TVL-V*`; the client may *predict* but may never *assert*.)

- **RTM-A3 — The realtime layer may not write kernel/aggregate state directly.**
  Preserves **DP-A1** (DP primitives are the only path to kernel state) and **DP-A6** (Rust
  commit-service is the sole authoritative writer). State consequences enter only through the
  turn-based commit path (§5). The realtime transport carries *position*, not *truth*.

- **RTM-A4 — Realtime↔turn-based handoff is a server-owned transition.**
  Entering a turn-based encounter is decided and committed by the server, not asserted by a client.
  The participants' session mode flips `realtime-move` → `turn-submit` on commit, and back on
  encounter end (§5).

- **RTM-A5 — The Colyseus WS edge inherits the gateway's edge controls.**
  Same JWT validation, per-connection + per-user caps, and connection-lifecycle audit as
  api-gateway-bff (**I1 / PRR-20**). Tracked as `D-GAME-WS-EDGE-CONTROLS`; this doc is its design home.

> Interest-management axioms (**RTM-A6..A8**) and the two-layer anti-cheat axiom (**RTM-A9**) are
> defined in §6, alongside their design narrative.

---

## 4. Realtime movement — proposed flow

```
client (predicts)                game-server (Colyseus room, trusted)         kernel
   |  move-input / delta  ───────────▶  validate delta vs tilemap (RTM-A2)
   |                                     ├─ legal  → update room position, broadcast authoritative
   |  ◀─── authoritative positions ──────┤           position to room members at patch rate
   |  (reconcile / snap-back)            └─ illegal → snap-back this client, audit (anti-cheat)
   |
   |  crosses a semantic boundary?  ────▶  emit transition into turn-based layer  ──▶  §5
```

- **Validation reuses the tilemap kernel** the foundation already ships — no new geometry authority.
- **Presence** = room membership scoped to `(reality_id, region/cell)`; only co-located avatars are
  broadcast to each other. Interest management makes this a first-class subsystem — see **§6**.
- **No state mutation** happens on this path. Position is the only thing that changes, and it is
  ephemeral (RTM-A1).

---

## 5. The seam — handoff to the turn-based layer

A realtime-moving avatar reaches something with game-state consequence (an enemy, an interactable,
a region boundary that triggers a scene). The game-server **does not resolve it inline** — it crosses
into the locked turn-based machinery:

1. Game-server detects the trigger and emits it into the event layer (as a **Proposal** it cannot
   author, or — if it holds a narrow claim — a movement-transition **Submitted**; see **RTM-Q5**).
2. The **commit-service** runs the normal **EVT-V\*** pipeline and commits the authoritative event
   (`entered_region`, `combat_started`, `interaction_opened`).
3. On commit, participants flip to `turn-submit` mode. For combat this enters **COMB_001**'s
   server-authoritative resolution unchanged (seeded RNG, LLM-zero-math).
4. **Instanced (proposed default, RTM-Q4):** the encounter suspends the participants' realtime
   movement; non-participants keep moving in realtime elsewhere. On encounter end, mode flips back.

This keeps the turn-based authority design **untouched** — the realtime layer is just a new *producer*
of transitions into it, gated by the same validator.

Relationship to `TVL_001`: **long-distance travel stays turn-based** (`/travel route_id` + per-turn
ticks). Realtime movement is **local** (walk within a region/scene). The two scales coexist — see
**RTM-Q1**.

---

## 6. Interest management & presence scope (AOI)

Broadcasting every avatar's position to every client does not scale — it is the first thing that
breaks an MMO at population, and it is simultaneously a **tenancy leak** (you would receive players
you must not see). **Interest management (IM)** decides *which* entity updates each client receives.
Industry treats this as a first-class subsystem, not a side-effect of room membership; so do we.

- **RTM-A6 — Presence is AOI-scoped, never world-broadcast.**
  A client receives entity updates only for its **Area of Interest** = same `reality_id` ∧ same
  region/room ∧ within an interest radius. World-broadcast of all entities is forbidden — for
  bandwidth *and* tenancy.

- **RTM-A7 — AOI is the runtime visibility boundary, and it is reality-isolated.**
  AOI enforces the multiverse tenancy rule at the transport: two avatars in the *same region of
  different realities* never enter each other's AOI. (Composes peer-reality isolation
  ([`03_multiverse/`](03_multiverse/)) with the User-Boundaries tenancy doctrine — a presence
  broadcast that crossed realities would be the realtime analogue of the `entity_kinds` global-row bug.)

- **RTM-A8 — Update fidelity degrades with distance / priority (LOD).**
  Near entities update at full patch rate; distant/offscreen entities update less often or drop out;
  dense regions apply a per-client interest **cap** (nearest-first). Graceful degradation, never
  unbounded fanout.

**Mechanism (proposed, V1):** coarse partition = **one Colyseus room per region** (room membership =
AOI for V1). Colyseus already does property-level **delta encoding** at patchRate, so "send only what
changed" is free. Fine-grained within-region culling (spatial grid + per-entity neighbor lists) is a
**V2** concern, triggered when region size/density outgrows "a room is a reasonable AOI" — see RTM-Q7.

**Anti-cheat is two-layered** (industry standard; hard validation alone is insufficient):

- **RTM-A9 — Movement integrity has two layers.**
  (1) **Hard validation** (RTM-A2): per-delta bounds, synchronous, authoritative reject + snap-back —
  **V1 mandatory.** (2) **Anomaly detection** (**V2**): statistical / behavioral analysis over the
  recorded action stream flags sophisticated evasion (sub-threshold speed creep, teleport-via-desync)
  for audit / action. The event-sourced turn log is its natural substrate.

---

## 7. Open questions (deferred — clear later)

> Format per the track convention ([`07_event_model/99_open_questions.md`](07_event_model/99_open_questions.md)).
> Each carries a **proposed default** so the spec is internally coherent until decided.

### RTM-Q1 — Two movement scales?
**What:** Is near-realtime *local* tilemap movement a distinct layer from turn-based *long-distance*
travel (`TVL_001`)? **Why deferred:** confirm before pinning the travel↔movement boundary.
**Proposed default:** **YES** — realtime local movement + turn-based inter-region travel; preserves
the locked `TVL_001` design instead of reopening it.

### RTM-Q2 — Movement authority model
**What:** Position-delta validation (client computes position, server bounds/rejects it) vs
input-based server simulation (client sends inputs, server simulates the position). **Why deferred:**
cost vs strictness tradeoff. **Proposed default:** **position-delta validation** — cheaper, and
combat (not movement) is the competitive crux, so full input-sim is unwarranted for V1.

### RTM-Q3 — Position in the event log
**What:** Ephemeral realtime state with only semantic transitions evented (RTM-A1) vs every position
evented. **Why deferred:** ties directly to **R01 event volume**. **Proposed default:** **ephemeral** —
position in Colyseus/Redis; only §5 transitions become events.

### RTM-Q4 — Realtime↔turn-based handoff
**What:** Instanced (freeze participants into a turn-based encounter; world continues around them)
vs in-world (turns resolve in the shared realtime space). **Why deferred:** large cascade into
netcode + concurrency. **Proposed default:** **instanced for V1** — sealed deterministic encounter,
far simpler to make cheat-proof; in-world is a V2+ ambition.

### RTM-Q5 — Game-server producer claim for transitions
**What:** Does the game-server hold a narrow `produce: [Submitted]` claim for *movement-transition*
events, or must it emit **Proposals** and let the commit-service author everything (strict DP-A6)?
**Why deferred:** purity vs latency at the seam. **Proposed default:** **route through commit-service
as Proposals** for state transitions (keeps DP-A6 clean); ephemeral position needs no claim. Revisit
if seam latency hurts. Relates to **EVT-Q1** (multi-role producer binding).

### RTM-Q6 — Room / patch tick rate
**What:** The Colyseus room patch rate for authoritative position broadcast. **Why deferred:** tune
against playtest feel + bandwidth. **Proposed default:** **~10 Hz** to start (Colyseus default is
50 ms / 20 Hz; MMORPGs commonly run lower).

### RTM-Q7 — AOI partitioning structure & V1 scope
**What:** Coarse Colyseus-room-per-region for V1 (room membership = AOI) vs fine-grained intra-region
spatial grid (grid cells + per-entity neighbor lists). **Why deferred:** depends on V1 region
size/density, which is unmeasured. **Proposed default:** **room-per-region for V1**; add an
intra-region spatial grid in **V2** when a single region's avatar count makes whole-room broadcast
too costly.

### RTM-Q8 — Cross-boundary visibility
**What:** At a region edge, can a client see *into* the adjacent region (seamless world), or is each
region a hard visibility cell (nothing of the next region until you cross)? **Why deferred:** seamless
edges need cross-room state sharing (significant). **Proposed default:** **hard cell for V1**
(visibility = your room), matching the Colyseus room boundary; seamless edges are **V2+**.

### RTM-Q9 — Dense-region interest cap
**What:** When many avatars cluster in one AOI, cap the per-client tracked-entity set by
proximity/priority. **Why deferred:** the cap N and priority function need playtest data. **Proposed
default:** **nearest-first cap** (render the closest N, summarize/drop the rest); N pending V1 load
data. Relates to **G2 (load testing)**.

---

## 8. Prior art & industry alignment

Checked against production-MMO practice (2026-06-20 web survey). The spec's bones match how real
MMOs are built; the survey *added* the two-layer anti-cheat (RTM-A9), the AOI subsystem (RTM-A6..A8),
and the RTM-A1 checkpoint clause.

| Spec axiom / decision | Industry practice | Verdict |
|---|---|---|
| RTM-A2 predict → validate → reconcile | server-authoritative + client-side prediction + reconciliation is the standard pattern | ✅ matches |
| RTM-A2 hard speed/teleport check | distance ÷ elapsed-time vs cap; reject impossible deltas | ✅ matches |
| RTM-A9 two-layer anti-cheat | hard validation **+** statistical/behavioral anomaly detection on the recorded stream | ✅ adopted from survey |
| RTM-A1 ephemeral + checkpoint | position is "non-critical": in-memory, periodic DB flush (~30 s / zone-change / logout), never per-tick | ✅ matches |
| RTM-Q6 ~10 Hz | MMORPGs run low (WoW historically 4 Hz; 10 Hz "fine"); Colyseus default 50 ms = 20 Hz | ✅ conservative-correct |
| RTM-A6..A8 AOI | "broadcasting all state to everyone is not practical"; grid/region partition + neighbor tracking + distance-based update frequency is a first-class subsystem | ✅ adopted from survey |
| RTM-Q4 instanced turn-based combat | authoritative server; turn-based netcode is trivial (send action → resolve → broadcast); instancing standard | ✅ matches |
| Colyseus transport (PRR-20) | purpose-built authoritative-server framework; "clients are dumb visual representations"; property-level delta sync | ✅ validates choice |

**Sources:**
[Gambetta — prediction & reconciliation](https://www.gabrielgambetta.com/client-side-prediction-server-reconciliation.html) ·
[Roblox — server-side movement validator](https://devforum.roblox.com/t/serversided-movement-validator/4651762) ·
[Detecting cheating in real-time](https://medium.com/@amol346bhalerao/how-game-developers-detect-and-stop-cheating-in-real-time-0aa4f1f52e0c) ·
[Interest management thesis (McGill)](https://www.cs.mcgill.ca/~jboula2/thesis.pdf) ·
[Dynetis — interest management](https://www.dynetisgames.com/2017/04/05/interest-management-mog/) ·
[G2A — tick rate](https://www.g2a.com/news/glossary/what-is-tick-rate-in-gaming-how-server-updates-affect-hit-registration-and-online-play/) ·
[Colyseus — state synchronization](https://docs.colyseus.io/state) ·
[PRDeving — MMO architecture](https://prdeving.wordpress.com/2023/09/29/mmo-architecture-source-of-truth-dataflows-i-o-bottlenecks-and-how-to-solve-them/) ·
[Wikipedia — Turn-based MMORPG](https://en.wikipedia.org/wiki/Turn-based_MMORPG)

---

## 9. Cross-references

- Vision medium statement — [`00_VISION.md` §0](00_VISION.md)
- Turn-based authority — [`07_event_model/`](07_event_model/) (DP-A6, EVT-T1/T6, EVT-V\*)
- LLM state-change allowlist — [`05_llm_safety/02_command_dispatch.md`](05_llm_safety/02_command_dispatch.md) (A5-D3)
- Combat authority — [`features/18_combat/`](features/18_combat/) (COMB_001)
- Turn-based travel — [`features/00_travel/TVL_001_travel.md`](features/00_travel/TVL_001_travel.md)
- Event-volume risk — [`02_storage/R01_event_volume.md`](02_storage/R01_event_volume.md)
- WS edge controls — `D-GAME-WS-EDGE-CONTROLS` (this doc is its design home)
- Invariants — [`00_foundation/02_invariants.md`](00_foundation/02_invariants.md) (I1, I6, DP-A1, DP-A6)
