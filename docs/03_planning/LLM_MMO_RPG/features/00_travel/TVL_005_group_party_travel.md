# TVL_005 — Group/Party Travel

> **Conversational name:** "Group/Party Travel" (TVP). V1+30d+ feature letting several actors travel a journey together as one unit — a PC and their Tracked-NPC companions crossing the realm in a single party rather than each issuing a solo `Travel:Initiate`. A NEW `travel_party` aggregate owns the member set, the leader, and the party lifecycle. A party travels on the *leader's* TVL_001 journey: the leader issues `Party:Travel`, which creates the leader's `actor_travel_state` journey and binds every member to it; per-turn ticks + `Travel:Arrive` cascade every member's `entity.current_cell_id` so the party stays in genuine lockstep. Members do not get individual journey rows. OnFoot-only V1+30d+; each member pays their own provisions. ≤6 members. PC + Tracked NPC parity inherited from TVL_001. A TVL_004 encounter on the party journey pauses the whole party; the leader resolves it. Composite party travel (TVL_002) and mounted/mixed-mode party travel (TVL_003) stay deferred.
>
> **Category:** TVL — Travel Mechanics (V1+30d+ feature; fifth TVL feature; the group layer TVL_001 TVL-D5 deferred and TVL_002/TVL_003/TVL_004 each declared a dependency on)
> **Status:** **DRAFT 2026-05-16** (Phase 0 TVP-D1..D7 LOCKED with user `approve all` directive)
> **Catalog refs:** [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — owns `TVL-*` stable-ID namespace (`TVP-*` validators/deferrals/questions per-feature)
> **Builds on:** [`TVL_001`](TVL_001_travel.md) (parent — a party travels on the leader's `actor_travel_state` journey; `Travel:Initiate` machinery, `Scheduled:TravelTick`, `Travel:Arrive`, selective TDIL clocks all reused; the cross-feature validator blocking a party member's solo travel is a TVL_001 closure-pass behavioral item) · [`TVL_002`](TVL_002_composite_travel.md) (composite party travel — a party on a multi-segment journey — deferred TVP-D5 / TVL_002 CTV-D8) · [`TVL_003`](TVL_003_mount_vehicle_travel.md) (mounted/mixed-mode party travel deferred TVP-D4 / TVL_003 TVM-D3) · [`TVL_004`](TVL_004_travel_encounters.md) (an encounter on the party journey pauses the whole party; the leader resolves it; party-wide outcome distribution deferred TVP-D6 / TVL_004 CTE-D7) · [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) (the Route the party traverses) · [`RES_001`](../00_resource/RES_001_resource_foundation.md) (each member pays their own provisions per TVL_001's distance-based model) · [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) (Tracked-tier discipline — only PC + Tracked NPCs party-travel) · [`EF_001`](../03_actor_substrate/EF_001_entity_foundation.md) (`actor.current_cell_id` — every member's is updated on party arrival) · [`DF05_001`](../DF/DF05_session_group_chat/DF05_001_session_foundation.md) (a `travel_party` is distinct from a DF05 `session` — different aggregate, different purpose; §10)
> **Resolves:** Solo-only travel (TVL_001..TVL_004 ship travel as a strictly per-actor mechanic — a PC adventuring with three Tracked-NPC companions must issue four separate `Travel:Initiate`s per leg and hope the per-turn ticks keep them roughly together; nothing makes them *actually* arrive as a unit) · The dependency three later TVL features each declared (TVL_002 CTV-D8 composite party travel, TVL_003 TVM-D3 multi-passenger vehicles, TVL_004 CTE-D7 party encounters all read "Requires TVL_005 Group/Party Travel" — TVL_005 ships the `travel_party` aggregate those features layer on) · Companion-NPC travel coherence (a Tracked NPC companion that the narrative treats as "traveling with" the PC has, pre-TVL_005, no mechanical binding — TVL_005's party binding makes "traveling together" a real aggregate state the LLM and the engine can both read)
> **Defers to:** future **composite party travel** (a party on a TVL_002 multi-segment composite journey — TVL_002 CTV-D8; needs the party binding to span the composite's segment handoffs — TVP-D5) · future **mounted / mixed-mode party travel** (a party where members ride — including mixed mounts at slowest-member pace, and multi-passenger vehicles — TVL_003 TVM-D3; needs slowest-member-pace logic + per-member mount validation — TVP-D4) · future **party-wide encounter outcome distribution** (a TVL_004 encounter outcome applied across all members rather than the leader alone — TVL_004 CTE-D7; TVP-D6) · future **mid-journey membership change** (a member joining/leaving while the party is `Traveling` — V1+30d+ membership is frozen for the trip; TVP-D7) · future **party formation UX / invitations** (a richer invite→accept handshake; V1+30d+ `Party:Join` is a direct co-located join — TVP-D8)

---

## §1 Why this exists

Three concrete gaps that TVL_005 closes.

**Gap 1 — travel is strictly solo.** TVL_001 through TVL_004 model travel as a per-actor mechanic: one `actor_travel_state` per actor, one `Travel:Initiate` per journey. A PC adventuring with three Tracked-NPC companions — the canonical wuxia "我们一行人" travelling band — must, every single leg, issue four separate `Travel:Initiate`s and trust that the per-turn `Scheduled:TravelTick` keeps the four journeys roughly synchronised. They are not *actually* a unit: a slightly different `time_flow_rate`, a per-actor encounter, or one journey initiated a turn late, and the "party" silently desyncs. TVL_005 makes "travelling together" a real aggregate.

**Gap 2 — three later TVL features explicitly depend on this.** TVL_002's CTV-D8 ("Group/party composite travel"), TVL_003's TVM-D3 ("Multi-passenger vehicles … or a TVL_005 travel party"), and TVL_004's CTE-D7 ("Multi-actor / party encounters") each carry the literal deferral text "Requires TVL_005 Group/Party Travel". The travel arc was designed expecting a party aggregate to exist. TVL_005 ships the `travel_party` aggregate; once it lands, those three deferrals have something concrete to layer on.

**Gap 3 — companion travel has no mechanical anchor.** A Tracked NPC the narrative calls the PC's travelling companion has, pre-TVL_005, no mechanical link to the PC's journey. The chat-service LLM is told "Tiểu Long Nữ travels with Lý Minh" by the prose, but the engine has no `travel_party` state to ground that on — the two actors are just two independent journeys that happen to share a route. TVL_005's party binding makes "travelling together" a state the engine enforces (lockstep arrival) and the LLM can read (S9 `[TRAVEL_CONTEXT]` gains the party roster).

TVL_005 introduces no new travel physics. The journey, ticks, clocks, hospitality, encounters all come from TVL_001/TVL_004 unchanged — the party rides the *leader's* TVL_001 journey. TVL_005 adds a `travel_party` aggregate, a formation lifecycle, and the binding that cascades the leader's journey to every member.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Travel party** | `travel_party` aggregate (T2/Reality, sparse per-party) — NEW V1+30d+ | One row per party. Sparse — only formed parties exist. Closed (`Disbanded`) when emptied or admin-disbanded. |
| **PartyId** | `pub struct PartyId(pub(crate) Ulid)` opaque newtype | Module-private constructor; allocated at `Party:Form`. |
| **Leader** | One `PartyMember` with `role = Leader` — exactly one per party | The leader issues `Party:Travel` and the membership-management ops. Leadership transfers (§5.6) if the leader leaves a `Forming` party. |
| **Member** | A `PartyMember` `{ actor_id, role, joined_at_fiction_time }` in `travel_party.members` | Includes the leader. ≤6 total V1+30d+ (TVP-V5). |
| **PartyStatus** | Closed enum 3 V1+30d+ — Forming / Traveling / Disbanded | `Forming` — idle at a cell, membership mutable, the leader may initiate travel · `Traveling` — bound to the leader's journey, membership frozen · `Disbanded` — terminal. On `Travel:Arrive` a party transitions `Traveling → Forming` (now at the destination cell, ready to re-travel or disband). |
| **Party travel** | The party rides the *leader's* TVL_001 `actor_travel_state` journey | `Party:Travel` creates the leader's journey (an EVT-T3 cascade — a normal TVL_001 journey, system-created rather than player-`Travel:Initiate`d) and sets `bound_journey_id`. Members get **no** individual `actor_travel_state` rows. |
| **Lockstep arrival** | The defining guarantee — every member arrives at the same fiction-instant | The leader's `Scheduled:TravelTick` advances the one shared journey; `Travel:Arrive` cascades `entity.current_cell_id` to **all** members at once. There is no per-member drift because there is only one journey. |
| **Per-member provisions** | Each member pays their own TVL_001 distance-based provisions at `Party:Travel` | `food/water_per_league × route.distance_units` is deducted from *each member's* `resource_inventory`. If any one member is short → the whole `Party:Travel` rejects (TVP-V8). The leader does not subsidise. |
| **Membership freeze** | While `Traveling`, `travel_party.members` is immutable | `Party:Join` / `Party:Leave` are valid only while `Forming` (TVP-V3). Mid-journey membership change is deferred (TVP-D7). |
| **One party per actor** | An actor is a member of at most one `travel_party` (any non-`Disbanded`) | A second `Party:Form`/`Party:Join` for an actor already in a party → reject `travel.actor_already_in_party` (TVP-V6). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

TVL_005 introduces no new EVT-T* category.

| TVL_005 event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| An actor forms a party | **EVT-T1 Submitted** | `Party:Form { leader_actor_id, cell_id }` (NEW V1+30d+ sub-type) | PC via client-app / Tracked NPC via chat-service Chorus per NPC_002 | Creates a `travel_party` with the creator as the sole `Leader` member, `status=Forming`. |
| An actor joins a party | **EVT-T1 Submitted** | `Party:Join { party_id, actor_id }` (NEW V1+30d+ sub-type) | PC / Tracked NPC | The actor must be co-located with the party's cell and the party `Forming` (TVP-V3/V4). |
| An actor leaves a party | **EVT-T1 Submitted** | `Party:Leave { party_id, actor_id }` (NEW V1+30d+ sub-type) | PC / Tracked NPC | Valid only while `Forming` (TVP-V9). Leader-leave triggers the §5.6 transfer/dissolve. |
| The leader sends the party travelling | **EVT-T1 Submitted** | `Party:Travel { party_id, route_id, direction }` (NEW V1+30d+ sub-type) | The party leader (PC / Tracked NPC) | Mode is OnFoot V1+30d+ (TVP-V12) — not a payload field. Creates the leader's `actor_travel_state` journey + binds the party. |
| Party / journey-binding state mutation | **EVT-T3 Derived** | `aggregate_type=travel_party` | travel-service | Includes the cascade that creates the leader's `actor_travel_state` journey at `Party:Travel` and updates every member's `entity.current_cell_id` at `Travel:Arrive`. |
| Per-turn progress | **EVT-T5 Scheduled** | `Scheduled:TravelTick` (TVL_001 sub-type, unchanged) | EVT-G framework Generator | Ticks the one bound journey. TVL_005 adds no tick mechanism. |
| Admin disbands a party | **EVT-T8 Administrative** | `Forge:DisbandParty { party_id, reason }` (NEW V1+30d+ sub-type) | Forge admin via S5/S13 admin tooling | Sets `status=Disbanded`; if the party was `Traveling`, the leader's bound journey is also Canceled (TVL_001 `TravelStatus::Canceled`). Uses the existing Forge admin capability. |

**No new GeographyDeltaKind** — a party is per-actor-group runtime state, does not touch `world_geometry`.

**`Party:*` are EVT-T1 Submitted not EVT-T8 Admin** — forming and leading a party is regular gameplay. Only `Forge:DisbandParty` is EVT-T8.

---

## §3 Aggregate inventory

One new aggregate owned by TVL_005. **No new field on any TVL_001..TVL_004 aggregate** — a party member's party-bound state is derivable by querying `travel_party` rows; the TVL_001 closure pass for TVL_005 is **behavioral only — three items** (§3.2 / TVP-Q1), one of which *writes* the existing `entity.travel_journey_id` field for members but adds no new field.

### 3.1 `travel_party` (T2/Reality, sparse per-party) — PRIMARY (NEW V1+30d+)

```rust
#[derive(Aggregate)]
#[dp(type_name = "travel_party", tier = "T2", scope = "reality")]
pub struct TravelParty {
    pub party_id: PartyId,                          // primary key (sparse — only formed parties exist)
    pub leader_actor_id: ActorId,                   // the current leader; ∈ members with role=Leader
    pub members: Vec<PartyMember>,                  // includes the leader; 1..=6 V1+30d+ (TVP-V5)
    pub status: PartyStatus,                        // Forming | Traveling | Disbanded
    pub current_cell_id: CellId,                    // where the (idle) party sits while Forming; the leader's cell
    pub bound_journey_id: Option<JourneyId>,        // Some(..) while Traveling — the leader's actor_travel_state journey
    pub formed_at_fiction_time: FictionTime,        // leader.actor_clock at Party:Form
}

pub struct PartyMember {
    pub actor_id: ActorId,                          // FK into EF_001 entity registry; PC or Tracked NPC
    pub role: PartyRole,                            // Leader | Member
    pub joined_at_fiction_time: FictionTime,        // for the §5.6 oldest-member leadership transfer
}

pub enum PartyRole {                                // closed enum 2 V1+30d+
    Leader,                                         // exactly one per party; issues Party:Travel + membership ops
    Member,                                         // a non-leader member
}

pub enum PartyStatus {                              // closed enum 3 V1+30d+
    Forming,                                        // idle at current_cell_id; membership mutable; leader may Party:Travel
    Traveling,                                      // bound to the leader's journey; membership frozen
    Disbanded,                                      // terminal — emptied, or admin Forge:DisbandParty
}
```

**Rules:**

- `members` holds 1..=6 entries V1+30d+ (TVP-V5); exactly one has `role=Leader` and its `actor_id == leader_actor_id`.
- Every member's `actor_id` references an actor with `tracking_tier ≥ Tracked` (TVP-V7) — Untracked NPCs cannot party-travel (they have no travel state at all).
- An actor appears in at most one non-`Disbanded` `travel_party` (TVP-V6 — `travel.actor_already_in_party`).
- `status` transitions: `Forming ⇄ Traveling` (Travel at `Party:Travel`, back to `Forming` at `Travel:Arrive`); any state `→ Disbanded` (terminal). `Disbanded` is never left.
- `bound_journey_id` is `Some(j)` exactly while `status == Traveling`; `j` is the leader's `actor_travel_state` journey, `Active` for the trip's duration.
- `current_cell_id` equals the leader's `current_cell_id` while `Forming`; it is updated to the destination at `Travel:Arrive` (when the party returns to `Forming`).
- Membership (`Party:Join` / `Party:Leave`) mutates only while `Forming` (TVP-V3). A `Party:Travel` is valid only while `Forming`.
- When `members` would drop to zero (last member leaves), the party transitions `Disbanded` (§5.6).

### 3.2 Cross-feature interaction with TVL_001 (no schema field)

TVL_005 adds **no new field** to `actor_travel_state` or `entity_binding`. A party member's "bound to a party" status is derived by querying `travel_party` (find a non-`Disbanded` party whose `members` contains the actor). The TVL_001 closure pass for TVL_005 is therefore **behavioral only — three items**:

1. **Cross-feature validator (TVP-V11)** added to the TVL_001 `Travel:Initiate` pipeline — an actor who is a member of **any non-`Disbanded`** `travel_party` may not initiate a solo journey (`travel.actor_in_party`); they must `Party:Leave` first. Mirrors TVL_002's CTV-V15 cross-feature gate.
2. **Member in-transit marking** — at `Party:Travel`, the binding cascade sets **each member's** `entity.travel_journey_id` to the bound leader's journey_id and latches each member's `current_cell_id` (exactly the in-transit treatment TVL_001 §5.1 applies to a solo journeying actor), routed through the standard cell-change cascade so DF05 / PL_005 correctly see every member leave the origin cell. `Travel:Arrive`, a Canceled bound journey, and `Forge:DisbandParty` each clear `travel_journey_id` for every member. Without this, a non-leader member would read as stationary-and-available at the origin for the whole trip (HIGH-1 fix).
3. **Arrival cascade extension** — TVL_001's `Travel:Arrive` cascade, for a journey that is a `travel_party.bound_journey_id`, updates `entity.current_cell_id` for **every** party member, not just the journeying leader.

All three are behavioral; no `schema_version` bump and **no new field** — item 2 writes the *existing* TVL_001 `entity.travel_journey_id` field. This contrasts with TVL_002 (`composite_journey_id`), TVL_003 (`mount_id`), and TVL_004 (`encounter_schedule`), which each added a new `actor_travel_state` field; TVL_005 adds none (TVP-Q1).

---

## §4 Closed enums (TVL_005 V1+30d+)

### 4.1 PartyRole (2 V1+30d+) · PartyStatus (3 V1+30d+)

See §3.1. `PartyRole` {Leader, Member}; `PartyStatus` {Forming, Traveling, Disbanded}. `PartyMember` is a struct, not an enum.

TVL_005 reuses TVL_001's `JourneyId` / `TravelDirection` and (for the leader's journey) `TravelMode::OnFoot`.

---

## §5 Party lifecycle

### 5.1 `Party:Form`

```
Actor (PC OR Tracked NPC) issues Party:Form { cell_id }:
  ↓ EVT-T1 Submitted validator pipeline:
    TVP-V7 leader-tracked (tracking_tier ≥ Tracked) → pass.
    TVP-V6 actor-not-already-in-a-party (no non-Disbanded travel_party contains the actor) → pass.
    TVP-V10 no-active-solo-journey (the actor has no Active actor_travel_state — MED-1 fix; an actor
      mid-solo-journey cannot form a party) → pass.
    TVP-V4 leader-at-cell (cell_id == actor.current_cell_id) → pass.
  ↓ EVT-T3 Derived: travel_party row created — party_id, status=Forming, current_cell_id=cell_id,
    members=[{ actor, role=Leader, joined_at=actor.actor_clock }], leader_actor_id=actor.
```

### 5.2 `Party:Join` / `Party:Leave` (while `Forming` only)

```
Party:Join { party_id, actor_id }:
  ↓ TVP-V1 party-exists / TVP-V3 party-forming (status==Forming) / TVP-V7 member-tracked /
    TVP-V6 actor-not-already-in-a-party / TVP-V10 actor-has-no-active-solo-journey /
    TVP-V4 member-co-located (actor.current_cell_id == party.current_cell_id) /
    TVP-V5 size-cap (party.members.len() < 6) → pass.
  ↓ EVT-T3 Derived: party.members += { actor_id, role=Member, joined_at=actor.actor_clock }.

Party:Leave { party_id, actor_id }:
  ↓ TVP-V1 party-exists / TVP-V3 party-forming → pass. (Leaving while Traveling → reject
    travel.party_leave_while_traveling, TVP-V9.)
  ↓ EVT-T3 Derived: party.members -= the actor's entry.
    if the actor was the Leader → §5.6 leadership transfer / dissolve.
    if party.members is now empty → status = Disbanded.
```

### 5.3 `Party:Travel` (the party departs)

```
The party leader issues Party:Travel { party_id, route_id, direction }:
  ↓ EVT-T1 Submitted validator pipeline:
    TVP-V1 party-exists / TVP-V2 leader-only (issuer == party.leader_actor_id) /
      TVP-V3 party-forming → pass.
    TVP-V12 mode-onfoot: the party journey is OnFoot V1+30d+ (mounted party deferred TVP-D4) → pass.
    route validity — the leader's cell == route's from-cell (Forward) / to-cell (Backward); route ∈
      wg.routes; route.kind OnFoot-compatible — all per TVL_001's Travel:Initiate gates → pass.
    TVP-V4 all-members-at-origin: EVERY member's current_cell_id == the leader's origin cell → pass.
    TVP-V10 no-member-in-a-solo-journey: no member has an Active actor_travel_state → pass.
    TVP-V8 all-members-provisioned: EVERY member has ≥ food/water_per_league × route.distance_units
      in their own resource_inventory → pass. (Any one member short → reject; the leader does not
      subsidise.)
    TVP-V13 party-channel-bound: leader, all members, and route share one continent channel → pass.
  ↓ EVT-T3 Derived: the leader's actor_travel_state journey created — a normal TVL_001 journey,
    system-created (mode=OnFoot, route_id, direction; TVL_001 §5.1 journey structure). This
    journey-creation SKIPS TVL_001's built-in provisions deduction (TVL-V8 + the §5.1 RES_001
    cascade) — the per-member cascade below is the SINGLE authoritative deduction for all members
    INCLUDING the leader (HIGH-2 fix — mirrors TVL_002's "per-segment provisions not re-deducted").
  ↓ EVT-T3 Derived cascade: RES_001 — each member's resource_inventory food/water deducted ONCE,
    per-member, per TVL_001's distance-based model (the leader pays here, not in the line above —
    no double-charge).
  ↓ EVT-T3 Derived cascade: each member's entity.travel_journey_id is set to the leader's journey_id
    and their current_cell_id is latched (the standard TVL_001 in-transit treatment — HIGH-1 fix;
    routed through the standard cell-change cascade so DF05/PL_005 see every member leave the cell).
  ↓ EVT-T3 Derived: travel_party.status = Traveling; bound_journey_id = Some(the leader's journey_id).
    members frozen.
```

### 5.4 Per-turn ticks + party arrival

```
Scheduled:TravelTick advances the ONE bound journey (the leader's) exactly per TVL_001 §5.2 —
  selective TDIL clock advancement applies to the leader's actor/body clocks; each member's own
  actor/body clocks advance per the standard per-turn turn-boundary semantic (TDIL-A3) — the party
  is in one channel, one turn stream, so the members stay clock-aligned without TVL_005 doing
  anything special.
On the leader's Travel:Arrive (TVL_001 §5.3):
  ↓ EVT-T3 Derived cascade (TVL_001 closure-pass extension §3.2): for EVERY member of the bound
    party, entity.current_cell_id is set to the arrival cell AND entity.travel_journey_id is cleared
    to None — lockstep arrival. The per-member update is routed through the standard cell-change
    cascade so each member's DF05 session (MovedCell) / PL_005 state transitions correctly
    (HIGH-1 / LOW-3 — a party member's cell change is not special-cased away from the normal path).
  ↓ hospitality at arrival (TVL_001 §5.3) is evaluated for the leader; V1+30d+ the party shares the
    leader's hospitality result (if no inn + wakeful > 16h, the Exhausted check applies to the
    leader; party-wide status distribution is deferred TVP-D6, same boundary as the encounter case).
  ↓ EVT-T3 Derived: travel_party.status = Traveling → Forming; current_cell_id = the arrival cell;
    bound_journey_id = None. The party is now idle at the destination — free to Party:Travel again,
    Party:Join/Leave, or disband.
```

### 5.5 Encounter interaction (TVL_004)

```
A TVL_004 encounter fires on the bound journey (the leader's actor_travel_state) exactly per
TVL_004 §5.2 — the journey pauses; because every member is bound to that one journey, the WHOLE
party is paused (no member's progress advances — there is only one journey).
  ↓ the LEADER resolves the encounter — Encounter:Resolve { encounter_id, approach } — on behalf of
    the party (the encounter's actor_id is the leader; TVL_004 CTE-V5 owner check passes for the
    leader).
  ↓ V1+30d+ the encounter OUTCOME applies to the leader only (provisions/status/resource per
    TVL_004 §5.3). Party-wide outcome distribution — every member shares the bandit-ambush wounds,
    the storm's provisions loss — is deferred (TVP-D6 = TVL_004 CTE-D7). A TVL_004 Hazard
    DivertToCell reroute that Cancels the leader's journey also Disbands... see §5.6.
```

### 5.6 Leadership transfer · disband

```
Leader leaves a Forming party (Party:Leave by the leader, status==Forming):
  ↓ if other members remain → leadership transfers to the member with the EARLIEST
    joined_at_fiction_time (deterministic; ties broken by actor_id lexicographic order); that
    member's role → Leader; party.leader_actor_id updated. Party stays Forming.
  ↓ if no members remain → status = Disbanded.

Leader leaves while Traveling → REJECTED (TVP-V9 travel.party_leave_while_traveling) — the leader is
  committed for the trip; a non-leader cannot leave while Traveling either (membership frozen).

Admin Forge:DisbandParty { party_id, reason } (EVT-T8):
  ↓ EVT-T3 Derived: status = Disbanded. If the party was Traveling, the leader's bound journey is
    also Canceled (TVL_001 TravelStatus::Canceled; proportional provisions refund per the TVL-Q3
    policy, to each member's resource_inventory). Every member's entity.travel_journey_id is cleared
    to None (HIGH-1 — release the in-transit marking). Members are released — each free to travel solo.

A TVL_004 Hazard DivertToCell reroute Cancels the leader's bound journey (TVL_004 §5.5):
  ↓ the party's bound_journey_id journey is Canceled → travel_party.status = Disbanded; every member
    is moved to the divert cell (the party scattered to shelter) and each member's
    entity.travel_journey_id is cleared to None (HIGH-1); members released. (A gentler "party
    survives a reroute intact" behavior is deferred — TVP-D6 scope.)
```

---

## §6 Multiverse inheritance

TVL_005 V1+30d+ inherits the standard DP-Ch + EVT-T2 snapshot-fork contract:

- At snapshot fork: parent's `travel_party` rows copy bit-exactly into the child — `members`, `leader_actor_id`, `status`, `bound_journey_id` all preserved. A `Traveling` party's `bound_journey_id` references the leader's `actor_travel_state` journey, which TVL_001's own fork contract (TVL-19) copies with `journey_id` preserved — the FK stays valid.
- Child and parent advance + disband their parties independently.
- L1/L2 cascade: no L2 layer — `travel_party` is reality-local per-actor-group runtime state with no canonical-author declaration (a `canonical_parties` RealityManifest decl seeds L0/L1 at bootstrap, like every other canonical decl).
- Determinism: TVL_005 adds no RNG. The party rides the leader's TVL_001 journey, whose determinism (TVL-19) is unchanged. The §5.6 leadership transfer is deterministic (earliest `joined_at_fiction_time`, `actor_id` tie-break).

---

## §7 Validation pipeline (TVL_005 V1+30d+ additive validators)

| Validator | Stage | Reject rule_id |
|---|---|---|
| **TVP-V1** party-exists | `Party:Join`/`Leave`/`Travel` ReferentialIntegrityGate | `travel.party_unknown` (party_id ∉ travel_party rows, or status == Disbanded) |
| **TVP-V2** leader-only | `Party:Travel` AuthorizationGate | `travel.party_not_leader` (issuer != travel_party.leader_actor_id) |
| **TVP-V3** party-forming | `Party:Join`/`Leave`/`Travel` ReferentialIntegrityGate | `travel.party_not_forming` (status != Forming — membership + departure ops require Forming) |
| **TVP-V4** member-co-located | `Party:Form` / `Party:Join` / `Party:Travel` ReferentialIntegrityGate | `travel.party_member_not_co_located` (an actor's current_cell_id != the party's cell / the leader's origin cell) |
| **TVP-V5** party-size-cap | `Party:Join` SchemaGate | `travel.party_size_cap_exceeded` (party.members.len() would exceed 6 V1+30d+) |
| **TVP-V6** actor-not-already-in-a-party | `Party:Form` / `Party:Join` ReferentialIntegrityGate | `travel.actor_already_in_party` (the actor is in another non-Disbanded travel_party) |
| **TVP-V7** member-tracked | `Party:Form` / `Party:Join` AuthorizationGate | `travel.party_member_untracked` (actor.tracking_tier ∉ {Pc, TrackedMajor} — Untracked excluded) |
| **TVP-V8** all-members-provisioned | `Party:Travel` ReferentialIntegrityGate | `travel.party_member_insufficient_provisions` (any member lacks the per-member distance-based food/water) |
| **TVP-V9** no-leave-while-traveling | `Party:Leave` ReferentialIntegrityGate | `travel.party_leave_while_traveling` (status == Traveling — membership is frozen for the trip) |
| **TVP-V10** no-member-in-solo-journey | `Party:Form` / `Party:Join` / `Party:Travel` ReferentialIntegrityGate | `travel.party_member_already_traveling` (a forming-leader / joiner / member has an Active solo actor_travel_state — MED-1 fix added the `Party:Form` stage) |
| **TVP-V11** actor-not-in-a-party | TVL_001 `Travel:Initiate` ReferentialIntegrityGate (cross-feature gate) | `travel.actor_in_party` (the actor is a member of ANY non-Disbanded travel_party — solo travel blocked; they must `Party:Leave` first; MED-1 fix broadened this from "Traveling party" to "any party" so a Forming-party member cannot wander off and dangle; mirrors TVL_002 CTV-V15) |
| **TVP-V12** party-mode-onfoot | `Party:Travel` (structural assertion) | `travel.party_mode_unavailable_v1plus30d` — **defensive/structural V1+30d+**: `Party:Travel` carries no `mode` payload field (§2.5), so the party journey is *constructed* OnFoot and TVP-V12 cannot fail at runtime; it documents the OnFoot-only invariant and becomes a real input gate when mounted party travel (TVP-D4) adds a `mode` field |
| **TVP-V13** party-channel-bound | `Party:Travel` ChannelScope check | `travel.cross_channel_initiate_forbidden` (TVL_001 reused — leader, all members, and route must share one continent channel) |

---

## §8 Failure UX — `travel.*` namespace extension

TVL_005 V1+30d+ extends the existing `travel.*` RejectReason namespace owned by TVL_001 (party travel is within the travel domain — no new namespace). **12 NEW V1+30d+ rule_ids** (10 user-facing + 2 schema-level) + 1 reused TVL_001 id.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d+) | English fallback | New? |
|---|---|---|---|---|---|
| `travel.party_unknown` | schema | `Party:Join`/`Leave`/`Travel` | "Đoàn du hành được nêu không tồn tại." | "Travel party not found." | NEW |
| `travel.party_not_leader` | user | `Party:Travel` | "Chỉ trưởng đoàn mới có thể dẫn đoàn lên đường." | "Only the party leader can set the party travelling." | NEW |
| `travel.party_not_forming` | user | `Party:Join`/`Leave`/`Travel` | "Đoàn đang du hành — không thể thay đổi thành viên hay khởi hành lại." | "The party is travelling; membership and departure are locked." | NEW |
| `travel.party_member_not_co_located` | user | `Party:Form`/`Join`/`Travel` | "Mọi thành viên phải ở cùng một ô để hợp đoàn hoặc khởi hành." | "All members must be at the same cell to join or depart." | NEW |
| `travel.party_size_cap_exceeded` | user | `Party:Join` | "Đoàn du hành đã đủ người (tối đa 6)." | "Travel party is full (max 6)." | NEW |
| `travel.actor_already_in_party` | user | `Party:Form`/`Join` | "Bạn đã ở trong một đoàn du hành khác." | "You are already in another travel party." | NEW |
| `travel.party_member_untracked` | schema | `Party:Form`/`Join` | "Chỉ PC và NPC chính mới có thể gia nhập đoàn du hành." | "Only PCs and Tracked NPCs can join a travel party." | NEW |
| `travel.party_member_insufficient_provisions` | user | `Party:Travel` | "Một thành viên không đủ lương thực hoặc nước cho hành trình." | "A party member lacks food or water for the journey." | NEW |
| `travel.party_leave_while_traveling` | user | `Party:Leave` | "Không thể rời đoàn khi đang du hành." | "You cannot leave the party mid-journey." | NEW |
| `travel.party_member_already_traveling` | user | `Party:Form`/`Join`/`Travel` | "Một thành viên đang trong một hành trình riêng." | "A member is already on a solo journey." | NEW |
| `travel.actor_in_party` | user | TVL_001 `Travel:Initiate` (cross-feature gate) | "Bạn đang ở trong một đoàn du hành — hãy rời đoàn trước khi đi riêng." | "You are in a travel party; leave it before travelling solo." | NEW |
| `travel.party_mode_unavailable_v1plus30d` | user | `Party:Travel` | "Đoàn du hành chỉ có thể đi bộ ở phiên bản này." | "Party travel is OnFoot-only in this version." | NEW |
| `travel.cross_channel_initiate_forbidden` | schema | `Party:Travel` | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |

Of the 12 new ids: 10 are user-facing; `party_unknown` + `party_member_untracked` are schema-level (defensive — `party_member_untracked` only fires at a malformed canonical seed or admin grant). `party_mode_unavailable_v1plus30d` is the structural/defensive assertion of TVP-V12 (§7) — unreachable at runtime V1+30d+ since `Party:Travel` carries no `mode` field.

i18n: V1+30d+ ships `I18nBundle` per the RES_001 §2 cross-cutting contract from day one.

---

## §9 Cross-service handoff

| Service | Role | V1+30d+ status |
|---|---|---|
| **travel-service** | Authoritative owner of the `travel_party` aggregate; applies `Party:Form`/`Join`/`Leave`/`Travel`; at `Party:Travel` creates the leader's `actor_travel_state` journey + binds the party; at `Travel:Arrive` runs the lockstep-arrival member cascade. Co-located with `actor_travel_state` / `composite_journey` / `travel_encounter` / `mount` — one bounded context. | V1+30d+ |
| **world-service** | Reads `world_geometry.routes` for the leader's-journey route validation | V1+30d+ |
| **api-gateway-bff** | Routes `Party:*` POSTs; the player party UI GETs `travel_party` for the roster + status | V1+30d+ UI |
| **chat-service** (S9) | `[TRAVEL_CONTEXT]` gains the party roster (member display names + leader) when an actor is party-bound — the LLM narrates the band travelling together | V1+30d+ |
| **auth-service** | No new capability — `Party:*` are regular gameplay; `Forge:DisbandParty` uses the existing Forge admin capability | V1+30d+ unchanged |
| **knowledge-service** | Reads party history for the actor companionship knowledge graph (planned V1+ activation per CLAUDE.md two-layer pattern) | Not V1+30d+ |

**No new service.** The `travel_party` aggregate is owned by `travel-service`.

---

## §10 Composition with foundation siblings & TVL_001..TVL_004

| Sibling | Composition with TVL_005 |
|---|---|
| **TVL_001 Travel** | **Parent.** A party rides the *leader's* `actor_travel_state` journey — all of TVL_001's journey machinery is reused unchanged. The TVL_001 closure pass for TVL_005 is **behavioral only — three items** (no new schema field — §3.2): (1) the cross-feature validator TVP-V11 on `Travel:Initiate` (a member of any non-Disbanded party is blocked from solo travel); (2) the `Party:Travel` cascade marks every member in-transit — sets each member's existing `entity.travel_journey_id` to the bound journey_id + latches `current_cell_id`; (3) the `Travel:Arrive` cascade extends `entity.current_cell_id` (and clears `travel_journey_id`) to every bound-party member. The leader's journey-creation deliberately skips TVL_001's built-in provisions deduction — the per-member cascade is the single deduction (HIGH-2). |
| **TVL_002 Composite Travel** | Composite party travel — a party on a multi-segment composite journey — is **deferred** (TVP-D5 = TVL_002 CTV-D8). V1+30d+ `Party:Travel` takes a single `route_id` (one atomic TVL_001 leg). A composite party would need the party binding to survive the composite's segment handoffs. |
| **TVL_003 Mount/Vehicle Travel** | Mounted / mixed-mode party travel is **deferred** (TVP-D4 = TVL_003 TVM-D3). V1+30d+ a party is OnFoot-only (TVP-V12) — a party where members ride (and especially a *mixed* party at slowest-member pace) needs per-member mount validation + pace reconciliation. |
| **TVL_004 Travel Encounters** | An encounter fires on the bound journey (the leader's `actor_travel_state`); since every member is bound to that one journey, the encounter pauses the **whole party**. The **leader** resolves it (`Encounter:Resolve`). V1+30d+ the outcome applies to the leader only — party-wide outcome distribution is deferred (TVP-D6 = TVL_004 CTE-D7). A `Hazard` `DivertToCell` reroute Cancels the leader's journey → the party Disbands, members scatter to the divert cell (§5.6). |
| **GEO_004 ROUTE_001** | The leader's-journey `route_id` is a normal ROUTE_001 route; the OnFoot mode↔route rules (TVL_001 / TVL_003 §5.1) apply unchanged. |
| **RES_001** | Each member pays their **own** provisions at `Party:Travel` (TVL_001 distance-based, per-actor) — TVP-V8 rejects the whole departure if any member is short; the leader does not subsidise. `Forge:DisbandParty` of a Traveling party refunds each member proportionally. |
| **TDIL_001** | The party is one channel, one turn stream — members stay clock-aligned via the standard per-turn turn-boundary semantic (TDIL-A3); TVL_005 does nothing special. The leader's journey advances the leader's actor/body clocks per TVL_001's selective discipline. |
| **AIT_001** | Tracked-tier discipline — members + leader are PCs or Tracked NPCs (TVP-V7); Untracked NPCs have no travel state, cannot party-travel. |
| **EF_001 Entity Foundation** | `actor.current_cell_id` is read (co-location checks) and written (lockstep arrival cascade) for every member. No new EF_001 field. |
| **DF05_001 Session/Group Chat** | A `travel_party` is **distinct from** a DF05 `session` — different aggregate, different purpose: a session is for explicit social acts *at a cell* (DF5-A1 same-channel), a travel party is for *moving together between cells*. A party may of course form a DF05 session when idle at a rest stop, but that is a separate aggregate; TVL_005 declares no schema link. V1+ a convenience that auto-suggests a session for a party is possible (TVP-D8 scope). |
| **NPC_002 Chorus** | A Tracked NPC's `Party:Join` / `Party:Travel` choices are Chorus-driven — the LLM decides in character whether the companion travels with the PC, same flow as a PC. |
| **PL_001 Continuum** | Turn-boundary fire — the bound journey's ticks use TVL_001's `Scheduled:TravelTick`. No PL_001 schema change. |

---

## §11 RealityManifest extension

**One new RealityManifest field** — author-declared starting parties:

```rust
pub canonical_parties: Option<Vec<PartyDecl>>,       // None → the reality starts with no parties

pub struct PartyDecl {
    pub leader_actor_ref: ActorRef,                  // a Tracked actor declared elsewhere in the manifest
    pub member_actor_refs: Vec<ActorRef>,            // the other members; leader + members ≤ 6
    pub formed_at_cell: CellId,                      // where the party sits Forming at reality seed
}
```

- `canonical_parties` is **OPTIONAL** V1+30d+ — a reality that omits it starts with no parties; parties form at runtime via `Party:Form`.
- Validated at reality seed: every `leader_actor_ref` / `member_actor_refs` entry resolves to a Tracked actor co-located at `formed_at_cell`; the total ≤ 6; no actor appears in two declared parties.
- The party-size cap (6), the OnFoot-only constraint, and the lifecycle are hardcoded V1+30d+ — not author-tunable (a larger cap / author-tunable rules deferred V2+).

Bootstrap order: TVL_005 V1+30d+ activates AFTER TVL_001 V1+30d ships (the leader's journey rides TVL_001's `actor_travel_state`). Realities pre-TVL_001-ship cannot travel, hence cannot party-travel.

V1+30d+ feature-flag: `services/travel-service` config `party_travel_enabled: bool` (default true V1+30d+; false leaves only solo TVL_001..TVL_004 travel). Mid-life flip on an existing reality FORBIDDEN per `generator_pipeline_version` discipline.

---

## §12 Sequences

### 12.1 A PC + two Tracked-NPC companions travel together

```
lý_minh, tieu_long_nu, and hong_qigong are all at cell khai_phong.
  ↓ lý_minh issues Party:Form { cell_id: khai_phong } → travel_party p created, status=Forming,
    members=[lý_minh (Leader)].
  ↓ tieu_long_nu issues Party:Join { party_id: p } → TVP-V4 (at khai_phong) / TVP-V5 (2 ≤ 6) /
    TVP-V6 (not in another party) → pass; members += tieu_long_nu (Member).
  ↓ hong_qigong issues Party:Join { party_id: p } → pass; members = [lý_minh, tieu_long_nu, hong_qigong].
  ↓ lý_minh (leader) issues Party:Travel { party_id: p, route_id: imperial_highway, direction: Forward }:
    TVP-V2 (lý_minh is leader) / TVP-V3 (Forming) / TVP-V12 (OnFoot) → pass.
    TVP-V4 (all 3 at khai_phong) / TVP-V10 (none on a solo journey) → pass.
    TVP-V8 (each of the 3 has ≥ 24 food / 48 water for the 24-league route) → pass.
  ↓ EVT-T3: lý_minh's actor_travel_state journey created (OnFoot, imperial_highway).
  ↓ EVT-T3 cascade RES_001: food/water deducted from EACH of the 3 members' own resource_inventory.
  ↓ EVT-T3: p.status = Traveling; bound_journey_id = Some(lý_minh's journey). Membership frozen.
  ↓ Scheduled:TravelTick advances the one journey; at Travel:Arrive at tuong_duong:
    EVT-T3 cascade → entity.current_cell_id = tuong_duong for ALL THREE members (lockstep).
    p.status = Traveling → Forming; current_cell_id = tuong_duong. The band has arrived together.
```

### 12.2 A party member tries to wander off solo — blocked

```
The party p (§12.1) is Traveling. tieu_long_nu issues a solo Travel:Initiate for a different route:
  ↓ TVP-V11 (cross-feature gate on TVL_001 Travel:Initiate): tieu_long_nu is a member of a
    non-Disbanded party → REJECT travel.actor_in_party.
  ↓ UI: "Bạn đang ở trong một đoàn du hành — hãy rời đoàn trước khi đi riêng."
  (TVP-V11 fires the same for a member of a FORMING party — MED-1 fix: a member must Party:Leave
   before any solo travel, so a Forming party never scatters into an undepartable state.)
```

### 12.3 Party departure rejected — one member under-provisioned

```
A 4-member party at Party:Travel; three members are well-stocked, hong_qigong has only 10 food for a
24-league route:
  ↓ TVP-V8 all-members-provisioned: hong_qigong's resource_inventory.food 10 < 24 → REJECT
    travel.party_member_insufficient_provisions. No journey created; nobody's provisions deducted.
  ↓ Workflow: hong_qigong acquires food (RES_001), OR leaves the party (Party:Leave while Forming),
    then the leader retries Party:Travel.
```

### 12.4 Leader leaves a forming party — leadership transfers

```
Party p, status Forming, members [lý_minh (Leader, joined T0), tieu_long_nu (joined T1),
hong_qigong (joined T2)]. lý_minh issues Party:Leave { party_id: p }:
  ↓ TVP-V3 (Forming) → pass.
  ↓ EVT-T3: lý_minh removed; members non-empty → leadership transfers to the earliest joined_at —
    tieu_long_nu (T1 < T2); tieu_long_nu.role → Leader; p.leader_actor_id = tieu_long_nu.
```

### 12.5 Admin disbands a traveling party

```
A Forge admin issues Forge:DisbandParty { party_id: p, reason: "..." } while p is Traveling:
  ↓ EVT-T3: p.status = Disbanded. The leader's bound journey is Canceled (TVL_001
    TravelStatus::Canceled); each member gets a proportional provisions refund to their own
    resource_inventory. All members released — each free to travel solo again.
```

---

## §13 Acceptance criteria

15 V1+30d+-testable acceptance scenarios AC-TVL-61..75. LOCK granted when ≥10 pass integration tests against the `travel-service` reference impl + TVL_001 fixtures.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-TVL-61** | `Party:Form` by a Tracked actor at its cell → `travel_party` created, status=Forming, the creator the sole Leader member. | — |
| **AC-TVL-62** | `Party:Join` by a co-located Tracked actor while Forming → the actor added as a Member. | — |
| **AC-TVL-63** | `Party:Join` that would make `members` exceed 6 → reject. | `travel.party_size_cap_exceeded` |
| **AC-TVL-64** | `Party:Join` by an actor not at the party's cell → reject. | `travel.party_member_not_co_located` |
| **AC-TVL-65** | `Party:Join` by an actor already in another party → reject. | `travel.actor_already_in_party` |
| **AC-TVL-66** | `Party:Travel` by the leader, all members co-located + provisioned → the leader's `actor_travel_state` journey created; each member's provisions deducted; party status → Traveling, `bound_journey_id` set. | — |
| **AC-TVL-67** | `Party:Travel` by a non-leader member → reject. | `travel.party_not_leader` |
| **AC-TVL-68** | `Party:Travel` where one member lacks provisions → reject; **no** journey created and **no** member's provisions deducted. | `travel.party_member_insufficient_provisions` |
| **AC-TVL-69** | The bound journey reaches `Travel:Arrive` → `entity.current_cell_id` updated to the destination for **every** member (lockstep); party status → Forming at the destination. | — |
| **AC-TVL-70** | A party member attempts a solo `Travel:Initiate` while in a party (Forming OR Traveling) → reject. | `travel.actor_in_party` |
| **AC-TVL-71** | `Party:Join` or `Party:Leave` while the party is Traveling → reject. | `travel.party_not_forming` / `travel.party_leave_while_traveling` |
| **AC-TVL-72** | The leader leaves a Forming party with other members → leadership transfers to the earliest-joined member; the party stays Forming. | — |
| **AC-TVL-73** | The last member leaves a party → party status → Disbanded. | — |
| **AC-TVL-74** | A TVL_004 encounter fires on the bound journey → the whole party pauses (no member progresses); the leader resolves it; the journey + party resume together. | — |
| **AC-TVL-75** | `Forge:DisbandParty` of a Traveling party → status Disbanded, the leader's journey Canceled, each member proportionally refunded; members released. | — |

---

## §14 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **TVP-D1** | Mid-journey membership change (a member joining/leaving while the party is Traveling) | V1+30d+ | V1+30d+ membership is frozen for the trip (TVP-V3/V9). A mid-journey leave would need a "drop a member at the next cell" or "split the party" mechanic. |
| **TVP-D2** | Party formation invitations — a richer invite → accept handshake (the leader invites; the invitee accepts) | V1+30d+ | V1+30d+ `Party:Join` is a direct co-located join (the joiner acts). An invitation flow pairs with a notification substrate. |
| **TVP-D3** | Author-tunable party rules — a larger size cap, role permissions, sub-leader roles | V2+ | V1+30d+ the 6-cap + the 2-role model are hardcoded. |
| **TVP-D4** | Mounted / mixed-mode party travel — members ride; mixed-mount parties move at slowest-member pace; multi-passenger vehicles | V1+30d+ | = TVL_003 TVM-D3. Needs per-member mount validation + pace reconciliation; V1+30d+ a party is OnFoot-only (TVP-V12). |
| **TVP-D5** | Composite party travel — a party on a TVL_002 multi-segment composite journey | V1+30d+ | = TVL_002 CTV-D8. Needs the party binding to survive composite segment handoffs; V1+30d+ `Party:Travel` is a single atomic route. |
| **TVP-D6** | Party-wide encounter + hospitality outcome distribution — an encounter/hospitality outcome applied across all members, not the leader alone | V1+30d+ | = TVL_004 CTE-D7. V1+30d+ a TVL_004 encounter outcome and the arrival hospitality result apply to the leader only. |
| **TVP-D7** | Party split / merge — dividing one party into two, or merging two parties | V2+ | V1+30d+ a party only forms (one member at a time) and disbands. |
| **TVP-D8** | Party ↔ DF05 session convenience — auto-suggesting/forming a chat session for an idle party | V1+ | A UX convenience; V1+30d+ a `travel_party` and a DF05 `session` are fully independent aggregates. |
| **TVP-D9** | NPC-led parties with autonomous travel decisions (a Tracked-NPC leader deciding routes via Chorus without a PC) | V2+ | V1+30d+ a Tracked NPC *can* be a leader, but rich autonomous NPC-party route planning pairs with NPC_002 V2+ autonomy. |

---

## §15 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **TVP-Q1** | A party member's "party-bound" state — a field on `actor_travel_state`/`entity`, or derived? | V1+30d+: **derived** — query `travel_party` for a non-Disbanded party containing the actor with `status==Traveling`. No schema field is added — unlike TVL_002 (`composite_journey_id`), TVL_003 (`mount_id`), and TVL_004 (`encounter_schedule`), which each added an `actor_travel_state` field via the TVL_001 closure pass. TVL_005 genuinely needs no *new* field: the `travel_party` aggregate is itself the membership index. The TVL_001 closure pass for TVL_005 is therefore behavioral only — three items per §3.2 (the TVP-V11 cross-feature validator + the member in-transit marking + the `Travel:Arrive` member cascade); item 2 *writes* the **existing** `entity.travel_journey_id` field for members (HIGH-1 fix /review-impl), which is a behavioral write, not a new field. |
| **TVP-Q2** | Lockstep clocks — do members' `actor_clock`/`body_clock` stay aligned without TVL_005 doing anything? | V1+30d+: yes — the party is in one continent channel, one turn stream; the standard per-turn turn-boundary advances every member's clocks identically (TDIL-A3). The leader's *journey* advances the leader's clocks via TVL_001's selective discipline; the members' clocks advance via the ordinary turn-boundary they all share. No drift, no TVL_005 mechanism. |
| **TVP-Q3** | Can a PC and a Tracked NPC be in a party together, or PC-only / NPC-only? | V1+30d+: **mixed** — any combination of PCs and Tracked NPCs (TVP-V7 only requires Tracked tier). The canonical case is one PC + N Tracked-NPC companions; a multi-PC party is also allowed. |
| **TVP-Q4** | If the leader's journey is Canceled (admin / TVL_004 reroute), what happens to members? | V1+30d+: the party `Disbands` and members scatter to the journey's resolved end cell (§5.6) — a Cancel is disruptive by nature. A gentler "party survives intact, returns to Forming" behavior is deferred (TVP-D6 scope). |
| **TVP-Q5** | Does a party share one set of provisions, or per-member? | V1+30d+: **per-member** — each member pays their own distance-based food/water at `Party:Travel` (TVP-V8); a shared party larder is not modelled (it would need a party-owned inventory — V2+). |
| **TVP-Q6** | Storage — monolithic `Vec<TravelParty>` per reality vs per-party rows? | V1+30d+: sparse aggregate per `party_id`, event-sourced via T2/Reality discipline (same as the other TVL aggregates — TVL-Q7 / CTV-Q6 / CTE-Q7 / TVM-Q6). Typical count is small. |
| **TVP-Q7** | Can a party `Party:Travel` again immediately after arriving (chained legs), to approximate a composite journey? | V1+30d+: yes — on arrival the party returns to `Forming` at the destination; the leader may immediately issue another `Party:Travel`. This is the V1+30d+ way to do a multi-hop party trip (one atomic leg at a time) until composite party travel (TVP-D5) lands — it mirrors how TVL_001 atomic travel relates to TVL_002 composite. |

---

## §16 Cross-references

- [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — catalog; `TVL-*` namespace; TVL_005 sub-section
- [`_index.md`](_index.md) — folder index; TVL_005 row added 2026-05-16
- [`TVL_001 Travel`](TVL_001_travel.md) — parent; the party rides the leader's `actor_travel_state` journey
- [`TVL_002 Composite Travel`](TVL_002_composite_travel.md) — composite party travel deferred (TVP-D5 / CTV-D8)
- [`TVL_003 Mount/Vehicle Travel`](TVL_003_mount_vehicle_travel.md) — mounted party travel deferred (TVP-D4 / TVM-D3)
- [`TVL_004 Travel Encounters`](TVL_004_travel_encounters.md) — an encounter pauses the whole party; leader resolves; party-wide outcome deferred (TVP-D6 / CTE-D7)
- [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) — the route the party traverses
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) — per-member provisions
- [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) — Tracked-tier discipline
- [`DF05_001 Session/Group Chat`](../DF/DF05_session_group_chat/DF05_001_session_foundation.md) — distinct from `travel_party` (§10)
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — NEW `travel_party` aggregate row
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — NEW EVT-T1 sub-types `Party:Form`/`Join`/`Leave`/`Travel` + `travel.*` party rule_ids (§1.4); NEW EVT-T8 sub-shape `Forge:DisbandParty` (§4)

---

## §17 Implementation readiness

**Design layer (this commit):** ✅ NEW `travel_party` aggregate schema + 2 V1+30d+ closed enums (`PartyRole` / `PartyStatus`) + the `PartyMember` struct + the formation lifecycle (`Party:Form`/`Join`/`Leave`/`Travel`) + the leader's-journey binding + the lockstep-arrival cascade + 13 validator slots (TVP-V1..V13) + 13 `travel.*` rule_ids (12 new + 1 reused) + 9 deferrals + 7 open questions + the §5.6 leadership-transfer/disband rules + RealityManifest `canonical_parties` extension + cross-feature coordination with TVL_001/TVL_002/TVL_003/TVL_004/ROUTE_001/RES_001/AIT_001/DF05_001 + 15 acceptance scenarios — all declared.

**Implementation phase (V1+30d+):** 📦 `travel_party` aggregate + apply_delta logic in `travel-service`; the **TVL_001 closure pass — behavioral only, three items** (no new schema field): (1) the cross-feature validator TVP-V11 on `Travel:Initiate` (a member of any non-Disbanded party blocked from solo travel); (2) the `Party:Travel` cascade marks every member in-transit — writes the *existing* `entity.travel_journey_id` field + latches `current_cell_id`, routed through the standard cell-change cascade; (3) the `Travel:Arrive` cascade extended to update + clear those fields for every bound-party member. The leader's journey-creation skips TVL_001's built-in provisions deduction (the per-member cascade is the single deduction — HIGH-2). `Party:Form`/`Join`/`Leave`/`Travel` + `Forge:DisbandParty` handlers; chat-service `[TRAVEL_CONTEXT]` party-roster extension; CI gates: lockstep-arrival invariant (every member of a bound party shares one `current_cell_id` after `Travel:Arrive`), in-transit-marking invariant (every member of a Traveling party has `travel_journey_id == bound_journey_id`), one-party-per-actor invariant, single-provisions-deduction invariant (no member — leader included — is charged twice), apply_delta total-function for the `Party:*` events + the binding cascade.

**Downstream consumer integration (V1+30d+ / V2+):** 📦 TVL_002 CTV-D8 composite party travel (TVP-D5) · TVL_003 TVM-D3 mounted/mixed-mode party travel (TVP-D4) · TVL_004 CTE-D7 party-wide encounter outcome distribution (TVP-D6) · knowledge-service companionship graph.

**Status:** DRAFT 2026-05-16. CANDIDATE-LOCK upon §13 acceptance scenarios passing integration tests against the reference `travel-service` implementation. LOCK upon downstream consumer integration (TVP-D4/D5/D6 — the three sibling features' party deferrals — resolve).

**Fifth TVL feature; the group layer the arc was converging on.** TVL_001 TVL-D5 deferred it; TVL_002 CTV-D8, TVL_003 TVM-D3, and TVL_004 CTE-D7 each declared "Requires TVL_005". TVL_005 ships the `travel_party` aggregate — travel stops being a strictly-solo mechanic, and the three sibling deferrals finally have the party aggregate they were written against.
