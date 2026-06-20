# 08 — Realtime Movement & Presence Authority

> **Status:** **RESOLVED + LOCKED (2026-06-20).** Axioms `RTM-A1..A9` are locked; all ten
> `RTM-Q1..Q10` decisions are resolved (§7). Created 2026-06-20 to fill a gap opened by the medium
> correction ([`00_VISION.md` §0](00_VISION.md): a rendered 2D/2.5D world with **near-realtime
> avatar movement**, not a text/turn-based MUD). The existing authority machinery is entirely
> **turn-based**; this doc specifies the missing **near-realtime movement & presence** layer and the
> seam where it hands off to the turn-based layer.
> **Accompanying registration:** new IDs registered in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md);
> decision rows `RTM-D1..D10` in [`decisions/locked_decisions.md`](decisions/locked_decisions.md).
> **Still pending (lock-gated):** add the game-server + `RTM` namespace owner to the `_boundaries/`
> ownership matrix under a `_LOCK.md` claim. Also the design home for `D-GAME-WS-EDGE-CONTROLS`.
> The "tilemap kernel" this doc validates against is **TMP_001 Tilemap Foundation**
> ([`features/00_tilemap/TMP_001_tilemap_foundation.md`](features/00_tilemap/TMP_001_tilemap_foundation.md);
> `TileState: Walkable/Open/Obstacle/Occupied`, blake3-deterministic).
>
> ⚠️ **Scope flag (Q8):** seamless cross-region visibility makes the **seamless-world-server problem**
> (cross-node state sharing + server-node handoff) a **V1 deliverable** — the heaviest item here.
> Implementation planning may stage *delivery* (V1→V2) without reopening the *design*.

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
turn." That is **not** an avatar walked around a tilemap in near-realtime — which §0 of the vision
now says the game is. This doc fills that gap without reopening the locked turn-based design.

---

## 2. Two authority cadences

| Layer | Cadence | What it governs | Authority model | Status |
|---|---|---|---|---|
| **Turn-based, event-sourced** | discrete turns | interactions, combat, all state mutation | Proposal → EVT-V\* validate → Submitted (DP-A6) | ✅ locked |
| **Realtime movement & presence** | near-realtime (~10 Hz broadcast + client interpolation, Q6) | avatar position, visible co-presence | client-predict → server-validate delta → reconcile | ✅ locked (this doc) |

The realtime layer is **subordinate**: it never mutates kernel/aggregate state. It moves avatars
through space and renders co-presence; anything with game-state consequence (entering combat,
arriving somewhere that triggers a scene, picking something up) **crosses into the turn-based layer**
via the existing commit path (§5).

---

## 3. Authority axioms (`RTM-A*`) — LOCKED 2026-06-20

- **RTM-A1 — Position is ephemeral, server-authoritative runtime state.** *(Q3)*
  Live position lives in the game-server runtime (+ Redis for cross-node presence), **never** in the
  canonical event log — at ~10 Hz × N avatars, logging every position would detonate **R01 (event
  volume)**. Only *semantic transitions* (§5) become events. **Checkpoint clause:** position is
  **periodically snapshotted** to durable store (~30 s / on region or node transition / on disconnect)
  for crash recovery — a *state snapshot*, not an event, so R01 is unaffected. (Standard MMO practice:
  position is "non-critical" data, flushed periodically, never per-tick.)

- **RTM-A2 — Every client movement is a *request*, validated and reconciled.** *(Q2, Q10)*
  The game-server validates each movement **delta** (position-delta model, Q2): walkability +
  max-speed-per-elapsed-tick + no-teleport/no-clip. Illegal → authoritative **snap-back**. Client
  prediction is provisional and always yields to server correction. **Rules are shared, not
  reimplemented (Q10):** the walkability/speed check is authored once in Rust (with the tilemap
  kernel), compiled to **WASM**, and run inside the TS game-server — zero rule-drift, no per-move
  RPC. The Rust kernel remains the authoritative **source/publisher** of the tilemap + actor-speed
  *data*, which the game-server holds in memory and feeds to the WASM check.

- **RTM-A3 — The realtime layer may not write kernel/aggregate state directly.**
  Preserves **DP-A1** (DP primitives are the only path to kernel state) and **DP-A6** (Rust
  commit-service is the sole authoritative writer). State consequences enter only through the
  turn-based commit path (§5). The realtime transport carries *position*, not *truth*.

- **RTM-A4 — Realtime↔turn-based handoff (and node handoff) is a server-owned transition.** *(Q4, Q8)*
  Entering a turn-based encounter, *and* migrating an avatar across a server-node boundary in the
  seamless world (Q8), are server-decided transitions — never client-asserted. Session mode flips
  `realtime-move` → `turn-submit` on encounter entry and back on exit; node handoff transfers
  authoritative position between nodes via the cross-node presence store (RTM-A1).

- **RTM-A5 — The Colyseus WS edge inherits the gateway's edge controls.**
  Same JWT validation, per-connection + per-user caps, and connection-lifecycle audit as
  api-gateway-bff (**I1 / PRR-20**). Tracked as `D-GAME-WS-EDGE-CONTROLS`; this doc is its design home.

(Interest-management axioms **RTM-A6..A8** and the two-layer anti-cheat axiom **RTM-A9** are in §6.)

---

## 4. Realtime movement — flow

```
client (predicts)                game-server (trusted, WASM validator)        Rust kernel
   |  move-input / delta  ───────────▶  wasm(walkability + speed) (RTM-A2)
   |                                     ├─ legal  → update position, broadcast authoritative
   |  ◀─── authoritative positions ──────┤           position to AOI subscribers @ ~10 Hz
   |  (reconcile / snap-back, interpolate)└─ illegal → snap-back this client, audit (anti-cheat)
   |                                                      ▲ tilemap + speed DATA published here ─┘
   |  crosses a semantic boundary?  ────▶  emit Proposal into turn-based layer  ──▶  §5
```

- **Validation rules** run as the kernel's Rust check compiled to **WASM** (RTM-A2) — no reimplementation.
- **Presence** is **AOI-scoped** via the global spatial grid, reality-isolated — see **§6**.
- **No state mutation** happens on this path; position is ephemeral (RTM-A1).

---

## 5. The seam — handoff to the turn-based layer

A realtime-moving avatar reaches something with game-state consequence (an enemy, an interactable,
a region boundary that triggers a scene). The game-server **does not resolve it inline** — it crosses
into the locked turn-based machinery:

1. **Game-server emits a Proposal** (EVT-T6) for the transition *(Q5 — keeps DP-A6's single
   authoritative writer; the game-server is a **proposer**, never a writer)*.
2. The **commit-service** runs the normal **EVT-V\*** pipeline and commits the authoritative event
   (`entered_region`, `combat_started`, `interaction_opened`).
3. On commit, participants flip to `turn-submit` mode. For combat this enters **COMB_001**'s
   server-authoritative resolution unchanged (seeded RNG, LLM-zero-math).
4. **Instanced — dedicated encounter scene (Q4):** entering combat moves participants into a
   **dedicated combat instance** (its own sub-session/room). Their realtime position is checkpointed
   (RTM-A1) on leave and restored on return. Non-participants continue in the realtime world and see
   the participants depart into the encounter; on encounter end, participants return to their region
   at the saved position.

This keeps the turn-based authority design **untouched** — the realtime layer is just a new *producer*
of transitions into it, gated by the same validator.

Relationship to `TVL_001`: **long-distance travel stays turn-based** (`/travel route_id` + per-turn
ticks); realtime movement is **local** (walk within / across regions). The two scales coexist *(Q1)*.

---

## 6. Interest management & presence scope (AOI)

Broadcasting every avatar's position to every client does not scale — it is the first thing that
breaks an MMO at population, and it is simultaneously a **tenancy leak**. **Interest management (IM)**
decides *which* entity updates each client receives — a first-class subsystem, not a side-effect of
room membership.

- **RTM-A6 — Presence is AOI-scoped, never world-broadcast.** *(Q7, Q8)*
  A client receives entity updates only for its **Area of Interest** = same `reality_id` ∧ within an
  interest radius on the **global spatial grid**, which **may span region boundaries** (seamless, Q8).
  World-broadcast of all entities is forbidden — for bandwidth *and* tenancy.

- **RTM-A7 — AOI is the runtime visibility boundary, and it is reality-isolated.**
  AOI may cross *region* boundaries but **never** *reality* boundaries: two avatars in the same region
  of different realities never enter each other's AOI. (Composes peer-reality isolation
  ([`03_multiverse/`](03_multiverse/)) with the User-Boundaries tenancy doctrine — a cross-reality
  presence broadcast would be the realtime analogue of the `entity_kinds` global-row bug.)

- **RTM-A8 — Update fidelity degrades with distance / priority (LOD).** *(Q9)*
  Near entities update at full patch rate; distant entities update less often or drop out; dense AOIs
  apply a per-client interest **cap** (nearest-first; N pending V1 load data). Graceful degradation,
  never unbounded fanout.

**Mechanism (LOCKED, V1):** AOI is a **global spatial grid** (grid cells + per-entity neighbor lists)
from V1 (Q7), **not** room-membership. Interest sets are computed per-client from grid-cell
neighborhoods and **span region boundaries** (seamless, Q8) — so V1 takes on the
**seamless-world-server problem**: cross-node state sharing (Redis-backed, RTM-A1) and **server-node
handoff** as avatars cross grid/region/node boundaries (server-owned, RTM-A4). Colyseus rooms remain
a *transport detail*, not a hard visibility wall; Colyseus property-level delta encoding still applies
within a node's patch. **Scope note (Q8):** seamless-world is the heaviest item in this spec;
implementation planning may stage *delivery* to V2 without reopening the *design*.

**Anti-cheat is two-layered** (hard validation alone is insufficient):

- **RTM-A9 — Movement integrity has two layers.**
  (1) **Hard validation** (RTM-A2 WASM check): per-delta bounds, synchronous, authoritative reject +
  snap-back — **V1 mandatory.** (2) **Anomaly detection** (**V2**): statistical / behavioral analysis
  over the recorded action stream flags sophisticated evasion (sub-threshold speed creep,
  teleport-via-desync). The event-sourced turn log is its natural substrate.

---

## 7. Decisions (RESOLVED 2026-06-20)

> All ten resolved with the user on 2026-06-20. Recorded as `RTM-D1..D10` in
> [`decisions/locked_decisions.md`](decisions/locked_decisions.md).

| # | Decision | Resolution |
|---|---|---|
| **RTM-Q1** | Two movement scales? | ✅ **Yes** — realtime *local* movement + turn-based *long-distance* `TVL_001`; the locked travel design is preserved. |
| **RTM-Q2** | Movement authority model | ✅ **Position-delta validation** — client computes position, server validates the delta (WASM) and snap-backs; sufficient since combat (not movement) is the competitive surface. |
| **RTM-Q3** | Position in event log | ✅ **Ephemeral + periodic checkpoint** — position in runtime/Redis; only §5 transitions are events; durable snapshot for crash recovery (RTM-A1). |
| **RTM-Q4** | Realtime↔turn handoff | ✅ **Instanced — dedicated encounter scene** — combat spins up a dedicated instance; position checkpointed on leave / restored on return (§5.4). |
| **RTM-Q5** | Producer claim for transitions | ✅ **Route via commit-service** — game-server emits Proposals; the Rust commit-service authors the Submitted. Keeps DP-A6's single authoritative writer. |
| **RTM-Q6** | Tick / patch rate | ✅ **~10 Hz + client interpolation** — tunable up to 15–20 Hz if playtest feels stiff. |
| **RTM-Q7** | AOI partitioning structure | ✅ **Global spatial grid from V1** (grid cells + per-entity neighbor lists), not room-membership. |
| **RTM-Q8** | Cross-region visibility | ✅ **Seamless cross-region from V1** — AOI spans region boundaries; commits V1 to the seamless-world-server problem (cross-node sharing + node handoff). *Heaviest item — see scope flag + §6.* |
| **RTM-Q9** | Dense-region interest cap | ✅ **Nearest-first cap** — render the closest N, summarize/drop the rest; N pending V1 load data (relates to **G2**). |
| **RTM-Q10** | TS↔Rust validation seam | ✅ **Rust core via WASM** — walkability/speed check authored once in Rust, compiled to WASM, run in the TS game-server; kernel publishes the data. Zero rule-drift, no per-move RPC. |

**Consequences to track at implementation time:**
- WASM build dependency: the game-server bundles a **version-pinned** WASM artifact from the Rust
  kernel — register in the service map / `contracts/language-rule.yaml`; pin to the kernel's tilemap
  schema version.
- Seamless-world infra (Q7+Q8): cross-node presence store + node-handoff protocol (RTM-A4) is now a
  V1 build item — size it in the V1 plan; it dominates the realtime-layer effort.
- Combat instance lifecycle (Q4): instance create/destroy + position save/restore ties to RTM-A1.

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
| RTM-A6..A8 AOI | "broadcasting all state to everyone is not practical"; grid partition + neighbor tracking + distance-based update frequency is a first-class subsystem | ✅ adopted from survey |
| RTM-Q8 seamless cross-region | the "seamless world server" (cross-node state sharing + zone handoff) — real but hard; many MMOs avoid it with zone loads | ⚠️ ambitious — V1 scope flag |
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
- ID registration — [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md); decisions — [`decisions/locked_decisions.md`](decisions/locked_decisions.md)
