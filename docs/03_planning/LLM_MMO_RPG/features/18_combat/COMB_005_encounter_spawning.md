# COMB_005 — Encounter Spawning & Hostile Population

> **Conversational name:** "Spawn" (SPN). What puts an **enemy** in the world, when a fight **starts**, and
> when the enemy **comes back**. Owns hostile spawn declarations, the deterministic epoch respawn model, the
> aggro/engagement trigger, encounter formation, and the newbie-zone safety validator COMB_001 declared and
> never built.
>
> **Category:** COMB — Combat (COMB_005)
> **Status:** **DRAFT 2026-07-26**. Resolves the final third of **AUD-F9** ([`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md))
> — *"no spawning/population (nothing puts enemies in the world)."*
> **SPN-Q1..Q9 LOCKED** in this pass; `SPN-A1..A8` axioms codified.
> **Stable IDs in this file:** `SPN-A*` axioms · `SPN-Q*` decisions · `SPN-D*` deferrals · `SPN-V*`
> validators · `AC-SPN-*` acceptance criteria. Owns the `spawn.*` reject namespace.
> **Builds on:** [AIT_001](../16_ai_tier/AIT_001_ai_tier_foundation.md) `cell_untracked_density` +
> `Generated:UntrackedNpcSpawn` (EVT-G2) + `tier_capacity_caps` — **the ambient-population owner this doc
> layers on and does not replace** · [COMB_001](COMB_001_combat_foundation.md) §6 encounter SM + Q4
> disparity cap · [COMB_002](COMB_002_tactical_grid.md) §7 wilderness arena · [COMB_003](COMB_003_threat_and_targeting.md)
> §8 the formation seam · [COMB_004](COMB_004_loot_and_spoils.md) §10 `loot_budget` ·
> [PF_001](../00_place/) `PlaceDecl` + `combat_safety` · [TMP_001](../00_tilemap/TMP_001_tilemap_foundation.md)
> `TerrainKind` + seeded generation · [PL_001](../04_play_loop/PL_001_continuum.md) `fiction_clock` ·
> [FAC_001](../00_faction/) stance · [RTM](../../08_realtime_movement_authority.md) A6..A8 AOI ·
> [11 AGT](../../11_agent_decision_standard.md) D5 engagement promote/demote.
> **Determinism is inviolable** — population is a pure function of `(place, epoch, seed)` (SPN-A2).

---

## §1 — Purpose, and the boundary that shapes it

### What already exists (and is not this doc)

AIT_001 **already owns ambient population**. It declares `cell_untracked_density` per `PlaceType`,
materialises untracked NPCs lazily at cell-entry observation via `Generated:UntrackedNpcSpawn` (EVT-G2),
caps density at 12 per cell (AIT-V3) and caps tracked tiers via `tier_capacity_caps` (AIT-V2). A tavern has
four patrons because AIT_001 says so.

What AIT_001 does **not** answer — and what the audit means by *"nothing puts enemies in the world"*:

| Question | Owner before this doc |
|---|---|
| Which of a cell's population are **hostile combatants**? | nobody |
| What puts a wolf pack in a forest tile that has no `PlaceType`? | nobody (AIT_001 is cell/PlaceType-scoped) |
| What makes a fight **start** without a PC pressing attack? | nobody — COMB_001 §6 trigger 3 is *"(V1+30d) Lex ambush"* |
| When do defeated enemies **come back**? | nobody |
| What stops a level-40 boss spawning in the newbie zone? | **declared** as COMB_001 closure item 8, **never built** |

> **SPN-A1 — COMB_005 layers on AIT_001; it does not replace it.** AIT_001 owns *how many actors exist in a
> place and at what tier*. COMB_005 owns *which are hostile, how they group, when they engage, and when they
> return*. A hostile group's members **are** AIT_001 untracked NPCs, counted against AIT_001's density and
> capacity caps — never a parallel population with its own budget. Two population owners would produce two
> answers to "how crowded is this cell", which is exactly the drift `_boundaries/` exists to prevent.

### V1 minimum scope

- **`HostileSpawnDecl`** on PF_001 `PlaceDecl` and on TMP terrain (§3) — the declaration that a place
  *produces* enemies.
- **Epoch respawn** (§4) — population is a pure function of `(place, epoch, seed)`; **no roster aggregate,
  no timers** (SPN-A2/A3).
- **Aggro & engagement** (§5) — the trigger COMB_001 §6 left as a V1+ stub, generalised beyond Lex ambush.
- **Encounter formation** (§6) — from trigger to `CombatSessionBorn`, including the arena choice
  (cell grid vs COMB_002 §7 wilderness arena) and the handoff to COMB_003.
- **Tier promotion on engagement** (§7) — AGT-D5's promote/demote lever, applied to combat.
- **The newbie-zone validator** (§8) — COMB_001 closure item 8, finally owned and enforced.
- **`spawn_group`** (§9) — the identity COMB_004 §10's anti-farm budget hangs on.
- **8 V1 rule_ids** in the `spawn.*` namespace + **7 validators** SPN-V1..V7 + **AC-SPN-1..13**.

### V1 NOT shipping

| Feature | Defer to | Why |
|---|---|---|
| Dynamic difficulty / level-scaling to the party | **won't-fix V1** (SPN-D1) | contradicts the user's *"no level, no power rating"* direction (PROG_001 §1); a place's danger is a property of the place |
| Roaming / migrating spawn groups | V1+ (SPN-D2) | needs group pathing between cells; RTM movement authority covers actors, not groups |
| Event / world-state-triggered invasions | V2 (SPN-D3) | needs a world-event system; `RealityFlag` gating reserves the hook |
| Mid-encounter reinforcement waves | V1+ (SPN-D4) | `combat_session` sides are fixed at Born (COMB_001 §2); adding mid-fight members reopens initiative and threat seeding |
| Summoned combatants (from ABL abilities) | V2+ (SPN-D5 ≡ ABL-D7) | same reason as SPN-D4 |
| Named-boss rare-spawn timers / world bosses | V1+30d (SPN-D6) | needs cross-cell coordination and an announcement surface |
| PvP matchmaking / arenas | V1+ (SPN-D7) | PvP has no owner at all yet (audit taxonomy) |
| Spawn-density heat balancing / telemetry | V1+30d (SPN-D8) | ops concern; the epoch model makes it measurable when wanted |
| Player-placed spawns (traps, lures) | V2 (SPN-D9) | SPN-A8 forbids player writes to spawn declarations; a lure would be a distinct authored mechanic |

---

## §2 — Concepts & axioms

| Concept | Maps to | Notes |
|---|---|---|
| **HostileSpawnDecl** | Declaration on `PlaceDecl` (cell) or `TerrainSpawnDecl` (tile) | System-tier, author/admin-only (SPN-A8). |
| **spawn_group** | Derived identity `(place_ref, decl_index, epoch)` | **Not a row.** The key COMB_004 §10's anti-farm budget and `first_kill_only` hang on. |
| **spawn epoch** | `floor(fiction_day / respawn_period_days)` | The whole respawn model (§4). |
| **aggro radius** | Chebyshev tiles + LoS | §5; engine-computed (TG-A1). |
| **encounter formation** | trigger → sides → arena → `CombatSessionBorn` | §6. |
| **danger band** | PF_001 `combat_safety` × archetype tier | §8; the newbie-zone guard. |

### Axioms

- **SPN-A1** — *(above)* COMB_005 layers on AIT_001's population ownership.
- **SPN-A2 (Population is derived, never a stored roster).** The hostile population of a place at a given
  fiction time is a **pure function** of `(HostileSpawnDecl, epoch, blake3 seed)`. There is no
  "spawned enemies" aggregate, no spawn timer, no scheduler tick. Same pattern as TMP_001's tilemap
  generation, CSC_001's fixture placement and DF07's derived stat block — and it is what makes population
  survive replay and MV12 time-travel with zero spawn-specific machinery.
- **SPN-A3 (Respawn is epoch arithmetic, not a timer).** `epoch = floor(fiction_day / respawn_period_days)`.
  Within one epoch the population is fixed; crossing an epoch yields a fresh deterministic population.
  A timer would need durable per-group state, a scheduler, and an answer for time-dilated chambers
  (TDIL_001) where two places advance at different rates. Epoch arithmetic needs none of those: each place
  reads its **own** fiction clock, so dilation is handled by construction.
- **SPN-A4 (Materialisation is lazy, at observation).** Nothing spawns until a PC's AOI (RTM-A6..A8) or
  cell entry observes the place — reusing AIT_001's existing `Generated:UntrackedNpcSpawn` trigger rather
  than adding a second one. An unobserved forest has no wolves *and no cost*; this is the
  quantum-observation principle AIT_001 and PROG_001 Q4 already lock.
- **SPN-A5 (Engagement is engine-decided; the LLM never starts a fight).** The aggro predicate (§5) is pure
  engine arithmetic over distance, LoS, faction stance and safety band. A Major NPC's LlmDriver may *choose
  to strike* once an encounter exists (COMB_001 §6 trigger 2), but it can never conjure an encounter into
  being. Extends COMB-A1/TG-A1 to encounter *existence*.
- **SPN-A6 (Hostile spawns respect every existing cap).** A hostile group's members count against AIT_001's
  `cell_untracked_density` (≤12) and, on promotion, against `tier_capacity_caps`. If a cell's ambient
  population already fills the budget, the hostile group is **truncated, not stacked on top**
  (`spawn.density_truncated`, a warning on an accepted generation — never a rejection, because a place
  becoming briefly crowded must not break world generation).
- **SPN-A7 (No hostile spawn may exceed its place's danger band).** Enforced at **schema stage**, not at
  runtime (§8). A newbie zone cannot declare a high-tier spawn at all; the author is told at authoring
  time. This is COMB_001 closure item 8, and making it a schema reject rather than a runtime clamp is what
  makes it a guarantee rather than a mitigation.
- **SPN-A8 (Spawn declarations are System-tier).** Author/admin-only, via RealityManifest + an audited
  `Forge:EditSpawnDecl`. No player action creates, moves or suppresses a spawn declaration. A
  player-writable spawn table would let one player repopulate — or depopulate — the world for everyone.

### Event-model mapping

COMB_005 introduces **no new aggregate and no new EVT-T\* category.** It reuses AIT_001's generator and
COMB_001's lifecycle:

| Trigger | Event | Owner |
|---|---|---|
| Hostile group materialises at observation | **EVT-G2** `Generated:UntrackedNpcSpawn` (existing, extended payload) | AIT_001 |
| Engagement fires → encounter forms | **EVT-T4 System** `CombatSessionBorn` (existing) | COMB_001 |
| Untracked → Tracked promotion on engagement | existing AIT_001 promotion path (AGT-D5) | AIT_001 |
| Epoch rollover | **nothing** — derived (SPN-A3); no event, no tick | — |
| Author edits a spawn decl | **EVT-T8** `Forge:EditSpawnDecl` | WA_003 Forge (new sub-action) |

> The empty row is the point. A respawn is not an event; it is the passage of fiction time changing the
> answer to a pure function. Nothing is written, nothing is scheduled, nothing can drift.

---

## §3 — `HostileSpawnDecl`

```rust
/// On PF_001 PlaceDecl (cell-tier) and on TMP_001 terrain (non-cell tiles).
pub struct HostileSpawnDecl {
    pub archetype: ActorClassRef,          // SAME key as DF07 stat_archetypes + COMB_004 loot_tables
    pub group_size: QtyRange,              // { min, max }; rolled per epoch (§4)
    pub tier_hint: SpawnTier,              // Untracked (default) | Minor | Major — see §7
    pub danger_tier: u8,                   // 0..=9; checked against the place's band (§8)

    pub respawn_period_days: u16,          // fiction-days per epoch; 0 ⇒ never respawns (one-shot)
    pub aggro: AggroDecl,                  // §5
    pub active_window: Option<DayPhaseRange>,  // e.g. wolves only at night (PL_001 fiction clock)
    pub condition: Option<RealityFlag>,    // world-state gate (V2 hook, SPN-D3)

    pub loot_budget: u16,                  // COMB_004 §10 anti-farm budget per epoch
}

pub struct AggroDecl {
    pub radius_tiles: u8,                  // 0 ⇒ never initiates; purely defensive
    pub requires_los: bool,                // corner-line LoS (COMB_002 §5)
    pub hostile_to: HostilityRule,         // AnyNonAllied | FactionStanceBelow(threshold) | Never
}
```

- **`archetype` is the same `ActorClassRef`** that keys DF07 `stat_archetypes` and COMB_004 `loot_tables`.
  One identifier ties a `bandit`'s stats, drops and spawn behaviour together, and it means this doc adds
  **no new actor-identity concept**.
- **`danger_tier` is a property of the spawn, not of the party** (SPN-D1). A place is dangerous or it is
  not; it does not become dangerous because a strong player arrived.
- **`respawn_period_days: 0`** is the one-shot case — a scripted ambush, a story encounter. It spawns in
  epoch 0 and never again, with no special-casing beyond the epoch formula returning a constant.

---

## §4 — The epoch respawn model (SPN-A2/A3 · SPN-Q2 LOCKED)

```pseudo
fn hostile_population(place, decl, decl_index, fiction_day) -> Vec<SpawnedGroup>:
    if decl.respawn_period_days == 0:  epoch = 0                        // one-shot; no div-by-zero
    else:
        offset = blake3(reality_id, place.channel_id, decl_index) % decl.respawn_period_days   // §4.2
        epoch  = (fiction_day + offset) / decl.respawn_period_days      // integer div
    if !active_window_contains(decl, fiction_day):        return []
    if !reality_flag_met(decl.condition):                 return []

    seed  = blake3(reality_id, place.channel_id, decl_index, epoch)     // same family as TMP_001/CSC_001
    rng   = ChaCha8Rng::from_seed(seed)
    size  = decl.group_size.min + rng.range(0, decl.group_size.max - decl.group_size.min)
    size  = min(size, ait_remaining_density_budget(place))              // SPN-A6 truncation
    if size == 0:                                        return []      // §4.3 — no group, no group_id
    group_id = SpawnGroupId(place.channel_id, decl_index, epoch)        // §9 — derived, not stored

    return [SpawnedGroup { group_id, archetype: decl.archetype, size, tier_hint: decl.tier_hint }]
```

**Why epochs rather than timers** (SPN-Q2). A respawn timer needs: a durable per-group "last killed at"
row, a scheduler that ticks it, cleanup when a place is unloaded, and a policy for time-dilated chambers
where two places disagree about how much time has passed. Epoch arithmetic needs **none** of that — each
place divides its own fiction-day by its own period, so:

- **Replay is free.** The same fiction day yields the same population, always.
- **Time dilation is free.** A TDIL_001 chamber running at 10× simply crosses epochs 10× faster; no
  cross-clock reconciliation exists to get wrong.
- **Unloading is free.** There is no state to clean up, so a cell can be evicted from memory at any moment.

**The tradeoff, and its V1 resolution (was SPN-QO1 — now closed, see §4.2):** all groups sharing a period
would otherwise respawn on the same fiction-day boundary rather than on a per-group "N days after *you*
killed it" clock. Clearing a camp one hour before the boundary means it returns almost immediately. **V1
ships the stateless phase offset** rather than deferring it; true per-kill timers stay rejected (stateful).
The anti-farm budget (COMB_004 §10) — which is *also* epoch-keyed — blunts what remains.

### §4.1 Materialisation is edge-triggered, not level-triggered (the load-bearing rule)

`hostile_population()` is a pure function of fiction time, so its *value* changes the instant an epoch
rolls over. If materialisation followed that value continuously, three things break:

| Break | What a player would see |
|---|---|
| Epoch rolls while the PC stands in the cell | enemies **pop into existence beside them**, unannounced |
| Epoch rolls **mid-encounter** | a second group appears while the first is still being fought |
| `active_window` opens mid-encounter (night falls) | wolves join a fight already in progress |

> **SPN-A9 (Materialisation is edge-triggered).** A place's population is **latched at observation** and
> does **not** re-evaluate while it stays observed. The latched set is refreshed only on an
> **observation edge** — the place transitions unobserved → observed — and **never** while a
> `combat_session` is active in it. Formally: `hostile_population()` remains the pure function it is
> (SPN-A2, replay intact); what is edge-triggered is *when the engine samples it*.

Consequences, all intended:
- A player camping a spawn point across an epoch boundary sees **nothing appear**; they must leave AOI and
  return. This is the standard MMO behaviour and it is the anti-camp mechanism, arriving for free.
- An encounter is **closed at formation** — the participant list is fixed at `CombatSessionBorn`, which is
  what SPN-D4 (no reinforcement waves) already required and what COMB_001 §2's fixed `sides` assumes.
- Replay is unaffected: the sampling instants are observation events, which are already in the event log.

### §4.2 Phase offset (was SPN-QO1 — RESOLVED, V1 active)

```
epoch = (fiction_day + phase_offset(group_key)) / respawn_period_days      // integer division
phase_offset(k) = blake3(reality_id, channel_id, decl_index) % respawn_period_days   // stateless, stable
```

De-synchronises boundaries across groups **without storing anything**: the offset is a pure function of
the declaration's identity, so it is stable across restarts, identical on replay, and free. Deferring it
was the wrong call in the first draft — it costs one hash, and shipping it later would shift every respawn
time in every existing world, which is exactly the kind of change that should not land after balance data
exists. It does **not** fix the "cleared just before *my* boundary" case (that needs per-kill state, still
rejected); it fixes the far more visible one where an entire region repopulates in lockstep.

---

## §5 — Aggro & engagement (SPN-A5 · SPN-Q3 LOCKED)

This is COMB_001 §6's third trigger, which read *"(V1+30d) Lex ambush"* and is now generalised:

```pseudo
// evaluated when an actor's position changes within a cell holding a hostile group
// (RTM AOI already delivers the position stream; no polling loop is added)
fn should_engage(hostile, subject) -> bool:
       hostile.aggro.radius_tiles > 0
    ∧ chebyshev(hostile.tile, subject.tile) ≤ hostile.aggro.radius_tiles
    ∧ (!hostile.aggro.requires_los || los_clear(hostile.tile, subject.tile))   // COMB_002 §5
    ∧ hostility_holds(hostile.aggro.hostile_to, hostile.faction, subject.faction)  // FAC_001
    ∧ !pf_001_safe(subject)                                                    // §8 safety band
    ∧ !comb_q4_disparity_shielded(hostile, subject)                            // COMB_001 Q4
    ∧ subject.tier == Pc || hostile.aggro.engages_npcs                         // §5.1
```

- **Engine-only, deterministic, no RNG.** Same distance metric and LoS routine COMB_002 already ships; no
  new spatial machinery, and the LLM is not consulted (SPN-A5).
- **Evaluated on position change**, riding the RTM position stream, not on a spawn-side polling tick. This
  keeps hostile evaluation proportional to *movement*, not to *world size*.
- **`radius_tiles = 0` means purely defensive** — bandits who will fight if struck but never initiate. This
  is the correct default for most ambient population, and it is why the field is not a bool.

### §5.1 NPC-vs-NPC engagement

`engages_npcs` defaults **false** in V1. Hostile groups engage PCs; they ignore each other. Two reasons,
both practical: NPC-vs-NPC fights burn LLM budget and tier capacity on encounters no player observes
(directly against AIT_001's quantum-observation principle), and a world where wolves clear the bandit camps
overnight depopulates itself with nobody watching. Faction warfare as **observed emergent content** is
SPN-D2/D3 territory. Recorded as **SPN-Q4** so the V1 cut is a decision, not an omission.

---

## §6 — Encounter formation (SPN-Q5 LOCKED)

```
should_engage() fires
  │
  ├─ 1. participants  — the hostile group ∪ the subject ∪ eligible actors in the cell
  │                     (COMB_001 §6 FAC_001 side bucketing; sides cap = 2 V1, Q5)
  ├─ 2. arena         — cell-tier place ⇒ the CSC_001 16×16 interior (TG-A2)
  │                     non-cell tile  ⇒ COMB_002 §7 deterministic wilderness arena,
  │                                       seeded blake3(reality_id, encounter_id), terrain-flavoured
  ├─ 3. placement     — engine places both sides at skeleton start areas; the COMB_002 §7
  │                     connectivity invariant guarantees neither start area is walled off
  ├─ 4. tier          — §7 promotion for the participants that warrant it
  ├─ 5. CombatSessionBorn  (COMB_001 §2)  — sides, grid, initiative (Q7 AV, initiator ×0.75)
  └─ 6. handoff       — COMB_003 §8 seeds the threat table from initiator + FAC/REP stance
```

Steps 2 and 3 are the reason COMB_002 §7's arena generator exists and has had no caller until now.
Step 6 is the exact seam COMB_003 §8 declared: **initiator + participant list, nothing else crosses.**

**Non-combatants** (COMB_001 §6 neutral civilians) are excluded at step 1 and remain in the cell, not in the
session — consistent with the concept notes' side-bucketing rule and with THR-A6's eligibility guard.

### §6.1 Formation collisions (the sides-cap problem)

COMB_001 Q5 caps an encounter at **2 sides**. Automatic engagement can generate situations that want more,
and the first draft did not say what happens. Locked:

| Collision | Rule |
|---|---|
| **A second hostile group of a *different* faction aggros the same PC** | it **joins the existing hostile side** — encounter-local alliance (COMB_001 Q5's own words) overrides faction rivalry for the duration. Mutual enemies of the PC fight alongside each other and can sort it out afterwards. **No third side is created.** Multi-side is COMB-Q2 (V1+; `sides: Vec<Side>` already allows it) |
| **An actor already in a `combat_session` is aggroed by a new group** | the group joins that actor's **existing** encounter; a second session is **never** created for an actor already in one (SPN-V8). Two concurrent sessions over one actor would give it two initiative queues and two threat contexts |
| **The joining group would exceed the arena's start-area capacity** | the group is **truncated** to what the arena can place, warning `spawn.formation_truncated`. Placement failure must never block an encounter that is already legal |
| **The joining group arrives mid-encounter** | it does **not** — SPN-A9/SPN-D4: participants are fixed at `CombatSessionBorn`. A group whose aggro fires while a session is active in the cell is **deferred**, and engages only after that session resolves. This is why "reinforcement waves" is a real deferred feature rather than an accident of timing |
| **Two PCs from mutually hostile factions are aggroed by one group** | both join the friendly side (the group is the common enemy). PC-vs-PC hostility inside one encounter is **PvP** — `COMB-Q3`, out of V1 scope |

The through-line: **engagement never manufactures a side.** It adds participants to one of the two that
COMB_001 already defined, or it waits. That keeps Q5 locked without making automatic aggro unusable, and it
localises every genuinely-multi-side case to COMB-Q2.

---

## §7 — Tier promotion on engagement (SPN-Q6 LOCKED)

AGT-D5 specifies engagement promote/demote as *the* cost lever. Applied here:

| `tier_hint` | At spawn | On engagement | After the encounter |
|---|---|---|---|
| `Untracked` (default) | one archetype block for the whole group (DF07 §9); zero per-actor state | **stays Untracked** — `EngineDriver` bulk resolve, group HP pool, zero LLM | discarded |
| `Minor` | untracked until engaged | promoted to Minor Tracked; `ScriptDriver` reaction table; **zero LLM** | demoted after `demote_after_days`, unless it took a durable action |
| `Major` | untracked until engaged | promoted to Major Tracked; `LlmDriver` via NPC_002 Chorus | stays Tracked (a named actor persists) |

- **Promotion runs through AIT_001's existing path** — including its `tier_capacity_caps` check. If the cap
  is full, promotion **fails soft**: the actor fights at the lower tier rather than blocking the encounter
  (`spawn.promotion_capped`, a warning). A capacity limit must degrade AI quality, never prevent a fight —
  the same *demote-not-stall* principle AGT-D5 locks.
- **The default is `Untracked`** so a reality that declares spawns carelessly cannot accidentally commit to
  an LLM call per bandit. Cost is opt-in, per declaration.

---

## §8 — The danger band: newbie-zone protection (SPN-A7 · COMB_001 closure item 8)

COMB_001 §9 item 8 declared: *"PF_001 — `combat_safety: CombatSafetyLevel` on PlaceDecl + NewbieZone
high-tier-spawn validator."* The field was declared; the validator was never built. It is built here.

```pseudo
// SPN-V4 — SCHEMA stage, at manifest validation. Not a runtime clamp.
for place in reality.places:
    band = max_danger_tier_for(place.combat_safety)     // Sanctuary 0 · Newbie 2 · Normal 6 · Perilous 9
    for decl in place.hostile_spawns:
        assert decl.danger_tier <= band                  else reject spawn.danger_tier_exceeds_band
        assert !(place.combat_safety == Sanctuary && decl.aggro.radius_tiles > 0)
                                                         else reject spawn.aggro_in_sanctuary
```

**Schema stage, not runtime, is the whole point.** A runtime clamp means the bad declaration ships, and the
protection depends on every code path remembering to clamp. A schema reject means the reality **cannot be
loaded** with a boss in the newbie zone, and the author learns at authoring time. This mirrors THR-Q7's
reasoning (guard at accrual, not at selection) and PL_007's ITM-V10 collision check.

Three layers compose, and they are deliberately not merged (COMB_001 Q4 already warns against
double-capping):

| Layer | Stage | Stops |
|---|---|---|
| **SPN-V4** danger band | schema | a dangerous enemy *existing* in a safe place |
| **PF_001 `combat_safety`** | runtime | a fight *starting* there (§5 predicate) |
| **COMB_001 Q4 disparity cap** | resolution | *damage* from a mismatched blow (flat 50%) |

---

## §9 — `spawn_group` (the anti-farm key)

`SpawnGroupId = (channel_id, decl_index, epoch)` — **derived, never stored** (SPN-A2). It is what
COMB_004 §10 hangs its two anti-farm mechanisms on:

- `first_kill_only` entries fire once per `spawn_group` — and because the epoch is in the key, the *next*
  epoch is a different group and the entry is eligible again. No counter to reset, no cleanup.
- `loot_budget` decrements within a group; at zero only guaranteed entries fire.

The budget's decrement is the **one** piece of per-group runtime state either doc needs, and it is
ephemeral — it lives as long as the group is materialised and vanishes with it, so an unobserved camp
carries no cost. Recorded plainly because it is the sole exception to "nothing is stored".

---

## §10 — Decisions (SPN-Q1..Q9 — LOCKED 2026-07-26)

| # | Question | Resolution & reasoning |
|---|---|---|
| **SPN-Q1** | Does COMB_005 own population, or does AIT_001? | **AIT_001 owns population; COMB_005 owns hostility, engagement and respawn** (SPN-A1). AIT_001 already ships density, lazy materialisation and caps. A second population owner would give two answers to "how crowded is this cell" — hostile groups are AIT_001 untracked NPCs, counted against AIT_001's budget. |
| **SPN-Q2** | Respawn timers or epoch arithmetic? | **Epochs** (SPN-A3, §4). Timers need durable state, a scheduler, unload cleanup and a time-dilation policy; epochs need none and are replay-exact by construction. The cost is boundary-synchronised respawns — mitigated by the epoch-keyed loot budget, with a stateless phase offset recorded as SPN-QO1 for V1+. |
| **SPN-Q3** | Who decides a fight starts? | **The engine, via a pure predicate** (SPN-A5, §5). An LLM that could initiate encounters could initiate them anywhere, at any cost, past every safety band. It may choose to strike inside an existing encounter; it may not create one. |
| **SPN-Q4** | Do hostile NPCs fight each other? | **No in V1** (`engages_npcs = false`, §5.1). Unobserved NPC-vs-NPC combat burns LLM budget and tier capacity on content nobody sees — directly against AIT_001's quantum-observation principle — and a self-clearing world depopulates itself. Faction warfare as *observed* content is SPN-D2/D3. |
| **SPN-Q5** | Where does a wilderness fight happen? | **COMB_002 §7's deterministic arena** (§6 step 2). The generator was designed for this and has had no caller until now; cell fights use the CSC_001 16×16 interior per TG-A2. No new spatial machinery. |
| **SPN-Q6** | What tier do spawned enemies run at? | **Untracked by default, promoted on engagement per `tier_hint`** (§7, AGT-D5). Default-Untracked means a careless declaration cannot commit to an LLM call per bandit. Promotion fails **soft** at capacity — degrade AI quality, never block a fight. |
| **SPN-Q7** | Newbie-zone protection at schema or runtime? | **Schema** (SPN-A7, §8). A runtime clamp ships the bad declaration and depends on every path remembering to clamp; a schema reject makes the reality unloadable and tells the author at authoring time. This is the COMB_001 closure item 8 that was declared and never built. |
| **SPN-Q8** | Does difficulty scale to the party? | **No — won't-fix V1** (SPN-D1). It contradicts PROG_001 §1's *"no level, no power rating"* direction. A place's danger is a property of the place; that is what makes exploration meaningful and what makes the danger band (§8) enforceable at schema stage. |
| **SPN-Q9** | Who may write spawn declarations? | **Author/admin only** (SPN-A8), via RealityManifest + audited `Forge:EditSpawnDecl`. A player-writable spawn table lets one player repopulate or depopulate the world for everyone — a cross-tenant defect, not a feature. |

---

## §11 — Closure-pass-extensions

| # | Target | Change | Status |
|---|---|---|---|
| 1 | **COMB_001 §6** | trigger 3 generalised from *"(V1+30d) Lex ambush"* to **§5 aggro engagement** (V1 active); Lex ambush becomes one `HostilityRule` case | applied this cycle |
| 2 | **COMB_001 §9 item 8** | **RESOLVED** — the NewbieZone high-tier-spawn validator is SPN-V4 (§8) | applied this cycle |
| 3 | **PF_001 `PlaceDecl`** | gains `hostile_spawns: Vec<HostileSpawnDecl>`; `combat_safety` gains the `max_danger_tier_for` band mapping (§8) | declared |
| 4 | **TMP_001** | non-cell tiles carry `TerrainSpawnDecl` keyed by `TerrainKind` (forest → wolves, mountain → bandits), same shape as §3 | declared |
| 5 | **AIT_001** | `Generated:UntrackedNpcSpawn` payload extended with `spawn_group_id` + `archetype`; hostile groups consume the existing density budget (SPN-A6) | declared |
| 6 | **COMB_002 §7** | the wilderness arena generator gains its caller (§6 step 2) — **no change to the generator** | confirmed |
| 7 | **COMB_003** | formation hands over initiator + participants at `CombatSessionBorn` (§6 step 6) — the seam COMB_003 §8 declared | confirmed |
| 8 | **COMB_004** | `spawn_group` + `loot_budget` + epoch key supplied (§9) | confirmed |
| 9 | **WA_003 Forge** | new audited admin sub-action `Forge:EditSpawnDecl` (SPN-A8) | declared |

---

## §12 — Failure-mode UX (`spawn.*` namespace)

| Reject rule | Stage | User-facing message (I18nBundle `default`) | When |
|---|---|---|---|
| `spawn.danger_tier_exceeds_band` | 0 schema | (schema-level) | `danger_tier` > the place's `combat_safety` band (§8) |
| `spawn.aggro_in_sanctuary` | 0 schema | (schema-level) | `aggro.radius_tiles > 0` in a `Sanctuary` place |
| `spawn.archetype_unknown` | 0 schema | (schema-level) | `ActorClassRef` has no DF07 `stat_archetypes` entry (an enemy with no stats) |
| `spawn.group_size_invalid` | 0 schema | (schema-level) | `min > max`, or `max` > AIT_001's per-cell density cap (12) |
| `spawn.respawn_period_invalid` | 0 schema | (schema-level) | `respawn_period_days` > the reality's fiction-year length (effectively never, expressed by accident) |
| `spawn.density_truncated` | generation | (informational warning) | SPN-A6 truncation — the group spawned smaller than declared |
| `spawn.promotion_capped` | runtime | (informational warning) | tier promotion blocked by `tier_capacity_caps`; the actor fights at a lower tier (§7) |
| `spawn.formation_truncated` | runtime | (informational warning) | a joining group exceeded the arena's start-area capacity and was truncated (§6.1) — placement never blocks a legal encounter |
| `spawn.session_already_active` | runtime | (ops-level) | engagement attempted to create a second `combat_session` for an actor already in one (SPN-V8); the group joins the existing encounter or defers instead |
| `spawn.condition_unresolvable` | 0 schema | (schema-level) | `condition` names an undeclared `RealityFlag` |

Per RES_001 §2, every `spawn.*` reject carries `RejectReason.user_message: I18nBundle` with an English
`default` plus a Vietnamese translation from day one.

**Player-visible data contract:** a place's danger is communicated in-fiction (narration, NPC warnings,
terrain description) and by the PF_001 safety band where the client surfaces it — **never** as a numeric
`danger_tier` or a spawn-table readout. Enemies are observed, not enumerated.

---

## §13 — Validators

| ID | Stage | Check |
|---|---|---|
| **SPN-V1** | 0 schema | decl well-formed: `group_size.min ≤ max ≤ 12`; `danger_tier ≤ 9`; `aggro.radius_tiles ≤ grid_max`; `loot_budget` ≥ 0 |
| **SPN-V2** | 0 schema | every `archetype` resolves in DF07 `stat_archetypes` **and** (if it drops anything) in COMB_004 `loot_tables` — an enemy with no stat block cannot fight |
| **SPN-V3** | 0 schema | every `condition` `RealityFlag` and every `active_window` phase resolves |
| **SPN-V4** | 0 schema | **the danger-band guard** (§8): `danger_tier ≤ max_danger_tier_for(place.combat_safety)`, and no aggro in `Sanctuary` |
| **SPN-V5** | generation | density conservation: hostile group size + ambient population ≤ AIT_001's `cell_untracked_density` cap; excess truncates and warns, never stacks |
| **SPN-V6** | runtime | the §5 engagement predicate is **the only** path to `CombatSessionBorn` from an NPC-initiated fight; no driver may call it directly (SPN-A5) |
| **SPN-V7** | replay | `hostile_population(place, decl, epoch)` is a pure function ⇒ identical population for identical `(place, epoch, seed)`; no wall-clock, no `Instant::now`, no un-seeded RNG in the path |
| **SPN-V8** | runtime | **one session per actor**: engagement never creates a second `combat_session` containing an actor already in an active one (§6.1); and no participant is added to a session after `CombatSessionBorn` (SPN-A9 / SPN-D4) |
| **SPN-V9** | runtime | **edge-triggered materialisation** (SPN-A9): a place's latched population does not change while it remains observed, and never while a `combat_session` is active in it |

> **SPN-V4, SPN-V6 and SPN-V7 are the non-vacuous set.** SPN-V4 can fail: it is a real constraint over
> author data, and a manifest declaring a tier-8 boss in a Newbie place must be **rejected at load**, not
> clamped — its bite-test is exactly that manifest. SPN-V6 can fail: a driver calling `CombatSessionBorn`
> directly bypasses the safety band and disparity cap, which is a plausible shortcut for whoever implements
> the Lex-ambush case, and the check catches it. SPN-V7 can fail: reading a wall clock instead of the
> fiction clock — the single most likely spawn bug — makes population non-reproducible on replay; its
> bite-test is substituting `Instant::now()` for `fiction_day`.

---

## §14 — Acceptance criteria (AC-SPN-1..13)

1. **Spawn-free reality plays** — a manifest declaring no `hostile_spawns`: the world is populated by
   AIT_001 ambient NPCs only, no fight ever auto-starts, and PC-initiated combat still works.
2. **Determinism** — the same `(place, epoch)` yields the same group size and composition on two machines
   and across a replay (SPN-A2 / SPN-V7).
3. **Wall-clock bite test** — substituting `Instant::now()` for the fiction clock in the epoch computation
   makes population non-reproducible and trips SPN-V7.
4. **Epoch respawn** — a camp cleared on fiction-day 3 with `respawn_period_days: 7` is absent for the rest
   of epoch 0 and present again at day 7 (epoch 1), with a **different** deterministic composition.
5. **One-shot spawn** — `respawn_period_days: 0` spawns once and never returns.
6. **Lazy materialisation** — an unobserved place generates **zero** actors; entering it materialises them
   through AIT_001's existing `Generated:UntrackedNpcSpawn` path, not a new one (SPN-A4).
7. **Density composition** — a tavern already holding 10 ambient NPCs with a 5-strong hostile decl spawns
   **2**, warns `spawn.density_truncated`, and never exceeds AIT_001's cap of 12 (SPN-A6 / SPN-V5).
8. **Aggro fires** — a PC stepping within `radius_tiles` with clear LoS triggers `CombatSessionBorn`;
   stepping to `radius + 1`, or behind an obstacle with `requires_los`, does not.
9. **Defensive spawn** — `radius_tiles: 0` never initiates, but fights back when struck.
10. **Newbie-zone guard (bite test)** — a manifest declaring `danger_tier: 8` in a `combat_safety: Newbie`
    place is **rejected at load** with `spawn.danger_tier_exceeds_band`; the reality does not start
    (SPN-V4). This is COMB_001 closure item 8 finally biting.
11. **Formation-path guard (bite test)** — a driver invoking `CombatSessionBorn` directly, bypassing §5,
    trips SPN-V6 — proving the safety band cannot be routed around.
12. **Wilderness arena** — an encounter on a non-cell forest tile generates a COMB_002 §7 arena, seeded and
    terrain-flavoured (trees as obstacles), with both start areas reachable (connectivity invariant).
13. **Tier promotion soft-fail** — with `tier_capacity_caps` full, a `Major` hostile engages at a lower tier
    with `spawn.promotion_capped` and the encounter proceeds normally (§7).

---

## §15 — Edge cases (resolved 2026-07-26)

An adversarial pass over §4–§7. Rows 1–4 were live defects — each would have shipped a visible bug.

| # | Case | Resolution |
|---|---|---|
| 1 | **Epoch rolls while the PC stands in the cell** — enemies pop in beside them | **SPN-A9** materialisation is edge-triggered, latched at observation (§4.1). Also yields anti-camp for free |
| 2 | **Epoch rolls mid-encounter** — a second group appears mid-fight | same rule; population never re-samples while a session is active (§4.1). SPN-V9 |
| 3 | **Two hostile groups aggro one PC** — wants a 3rd side, Q5 caps at 2 | the second joins the existing hostile side; engagement **never manufactures a side** (§6.1) |
| 4 | **An actor already in a session is aggroed again** — two initiative queues, two threat contexts | the group joins the existing encounter; a second session is never created (§6.1). SPN-V8 |
| 5 | **`group_size` truncated to 0** by a full density budget | no group and no `group_id` at all (§4, `size == 0` guard) — an empty group must not hold a loot budget |
| 6 | **`respawn_period_days: 0`** | one-shot, `epoch = 0`, no division (§4) |
| 7 | **`active_window` opens mid-encounter** (night falls during a fight) | no join — same edge-trigger rule (§4.1) |
| 8 | **Aggro fires while a session is active in the cell** | deferred until that session resolves; this is why reinforcement waves are a real deferred feature (SPN-D4), not a timing accident (§6.1) |
| 9 | **Arena start area cannot place the whole group** | truncate + `spawn.formation_truncated`; placement never blocks a legal encounter (§6.1) |
| 10 | **Two mutually-hostile PCs aggroed by one group** | both join the friendly side; PC-vs-PC is PvP, `COMB-Q3` (§6.1) |
| 11 | **Region-wide lockstep respawn** — every camp returning on the same day | stateless phase offset, now V1 (§4.2) |
| 12 | **Untracked group promoted to Tracked mid-encounter, then the encounter ends** | AIT_001 owns demotion (`demote_after_days`); COMB_005 adds no lifecycle of its own (§7) |

## §15.1 — Open questions resolved (were SPN-QO1/QO2)

**SPN-QO1 — the stateless phase offset. RESOLVED: ship it in V1** (§4.2), reversing the first draft's
deferral. The reasoning that deferred it — *"it changes every respawn time, so it should land with balance
data"* — is backwards: that is precisely the argument for shipping it **before** any balance data exists.
Landing it later would invalidate whatever tuning had been done against lockstep boundaries. It costs one
`blake3` and stores nothing.

**SPN-QO2 — which clock does `active_window` read? RESOLVED: the place's own fiction clock**, made
explicit rather than left flagged. SPN-A3 already establishes that each place divides its own clock for
epochs, and using a *different* clock for `active_window` would let a time-dilated chamber be
simultaneously mid-epoch by one clock and mid-night by another — two notions of "when" in one place. The
same rule now also governs COMB_004's `spoils_claim` expiry (§7.1 there), so **all three time-dependent
combat behaviours read one clock**: the clock of the place where the thing is happening. TDIL_001 needs no
per-feature exception.

## §15.2 — Deferred (SPN-D1..D9)

See the §1 "V1 NOT shipping" table — each row is the corresponding `SPN-D*`. **No open questions remain.**

## §16 — Cross-references

- Audit finding — [`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) AUD-F9
- **The population owner this layers on** — [`AIT_001`](../16_ai_tier/AIT_001_ai_tier_foundation.md) `cell_untracked_density`, `Generated:UntrackedNpcSpawn`, `tier_capacity_caps`
- Encounter SM + the trigger this fills + Q4 cap — [`COMB_001`](COMB_001_combat_foundation.md) §6, §9 item 8
- Wilderness arena (its first caller) — [`COMB_002`](COMB_002_tactical_grid.md) §7
- Threat seeding handoff — [`COMB_003`](COMB_003_threat_and_targeting.md) §8
- Anti-farm key + budget — [`COMB_004`](COMB_004_loot_and_spoils.md) §10
- Places + safety band — [`PF_001`](../00_place/) · Terrain spawns — [`TMP_001`](../00_tilemap/TMP_001_tilemap_foundation.md)
- Fiction clock — [`PL_001`](../04_play_loop/PL_001_continuum.md) · AOI — [`08 RTM`](../../08_realtime_movement_authority.md) A6..A8
- Promote/demote cost lever — [`11_agent_decision_standard.md`](../../11_agent_decision_standard.md) AGT-D5
