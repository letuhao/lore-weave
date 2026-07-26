# COMB_001 — Combat Foundation

> **Status:** **CANDIDATE-LOCK 2026-07-26** (concept Q1–Q9 LOCKED 2026-04-27 → DRAFT 2026-06-20 → this
> closure pass). Promoted because the three structural gaps that kept it at DRAFT are now closed:
> **AUD-F6** stat inputs (DF07_001, parallel track), **AUD-F5** items (PL_007/PL_007b, parallel track),
> **AUD-F9** the encounter's missing ends (COMB_003/004/005, this cycle) and **AUD-F10** the ability
> catalogue (ABL_001, this cycle). Every symbol the law-chain, the action set and the reject namespace
> referenced now has a declaring owner — see §0.
> **Owns** the `COMB-*` namespace, the `combat_session` aggregate, the `combat.*` reject namespace, and
> the combat EVT sub-types. Concept notes remain the full derivation + market survey + chaos-backend
> reference.
> **Determinism + LLM-zero-math + LLM-zero-space are inviolable** (TDIL-A9 / §4 / TG-A1) — and are now
> joined by **LLM-zero-targeting** (THR-A1) and **LLM-zero-encounter-creation** (SPN-A5), which close the
> last two axes on which an agent could have improvised past the engine.

---

## §0 — The combat feature family

COMB_001 is the **spine**; four siblings own the surfaces it references. Nothing below duplicates
COMB_001's locked decisions (action set, HSR initiative, 4-step law-chain, Q1–Q9) — each fills a gap it
declared.

| Doc | Owns | Closes |
|---|---|---|
| **COMB_001** (this) | encounter SM, action set, damage law-chain, initiative, sides, mortality/KO, `combat_session` | the spine |
| [`COMB_002`](COMB_002_tactical_grid.md) | tactical grid, movement, range/LoS, NPC stance, wilderness arena | AUD-F1 |
| [`COMB_003`](COMB_003_threat_and_targeting.md) | **whom** a hostile attacks — threat accrual, hysteresis, bounded candidate list | AUD-F9 (threat) |
| [`COMB_004`](COMB_004_loot_and_spoils.md) | what an encounter **produces** — loot tables, seeded rolls, rights window, progression award | AUD-F9 (loot) |
| [`COMB_005`](COMB_005_encounter_spawning.md) | what puts enemies in the world and **starts** the fight — spawn decls, epoch respawn, aggro, formation | AUD-F9 (spawning) |
| [`COMB_006`](COMB_006_pvp_and_stakes.md) | **when a player may fight a player** — consent channels, stakes, the disparity-cap waiver, notoriety | COMB-Q3 / PC-D2 |
| [`ABL_001`](../19_ability/ABL_001_ability_foundation.md) | what `Skill` refers to — ability catalogue, `EffectOp`, `PowerTerm` | AUD-F10 |

**Consumed from outside the family** (both authored in a parallel track, 2026-07-26):
[`DF07_001`](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) supplies every stat the law-chain reads;
[`PL_007`](../04_play_loop/PL_007_item.md) + [`PL_007b`](../04_play_loop/PL_007b_inventory.md) supply the
items `Strike`'s tool and `UseItem` operate on.

**The encounter, end to end:**

```
COMB_005 spawns + engages → COMB_001 forms the session → COMB_003 seeds threat
   → rounds: COMB_001 initiative · COMB_002 movement/range · ABL_001 abilities · DF07 stats · PL_007 items
   → COMB_001 resolves win/lose → WA_006 finalises mortality → COMB_004 rolls spoils
```

---

## §1 — Architecture (3-layer, LLM-zero-math LOCKED)

Combat is a **turn-based, instanced, engine-authoritative** encounter. The 3 layers are now **Agent
Decision Standard drivers** (AGT-A3) over a closed combat tool-vocabulary:

| Layer | Owns | Driver (AGT) |
|---|---|---|
| **L1 CombatEngine** (deterministic, NO LLM) | initiative queue, damage law-chain, hit/dodge/crit (seeded RNG), status tick, win/lose, **all spatial math** (movement/range/LoS, TG-A1) | — (engine) |
| **L2 ActionSelection** | picks each actor's `Decision` from the combat `allowed_tools` set | PC=**HumanDriver** (UI) · Major NPC=**LlmDriver** (NPC_002 Chorus, via ai-gateway) · Minor=**ScriptDriver** (AIT_001 `combat_reaction_table`) · Untracked=**EngineDriver** (bulk) |
| **L3 Narration** (LLM, post-resolution) | prose over the round's `ResolutionResult` batch; **cannot modify any number** | LlmDriver (async, non-blocking) |

> **COMB-A1 — The LLM never computes combat math or space.** It selects intent (action + target + TG-A4
> stance) from the closed vocabulary; the engine resolves everything. A `Decision` is a Proposal →
> EVT-V* → commit (DP-A6, AGT-A6). Hallucinated/out-of-set action → reject + **fallback `Defend`**.

---

## §2 — `combat_session` aggregate (ephemeral, sparse)

```rust
pub struct CombatSession {
    pub session_id: CombatSessionId,
    pub channel_id: ChannelId,                 // single cell per TDIL-A5
    pub started_at_turn: u64,
    pub sides: Vec<Side>,                       // cap = 2 V1 (Q5); side_a friendly / side_b hostile to initiator
    pub round_number: u32,
    pub initiative_queue: Vec<(ActorRef, i32)>, // (actor, action_value) — HSR
    pub next_action_idx: u32,                   // monotonic per-session; seeds RNG (Q8)
    pub grid: TacticalGrid,                      // COMB_002 — battlefield positions + obstacles (ephemeral)
    pub state: CombatState,                      // Active / Resolved / Cancelled

    // ─── added at CANDIDATE-LOCK 2026-07-26; all ephemeral, all die with the session ───
    // ALL ordered maps, deliberately: the per-round checkpoint serialises this struct, so a hash
    // container would put iteration order into the replay bytes and make DF7-V4's byte-identical
    // assertion fail nondeterministically (DF07_002 EC-3; same reason ABL uses BTreeSet, ABL-V7).
    pub stat_snapshots: BTreeMap<ActorRef, StatSnapshot>,           // DF07 §8.1 — { stats, prog, epoch };
                                                //   resolved once at Born, epoch-refreshed at round
                                                //   boundaries only. `prog` carries the kinds any declared
                                                //   ABL PowerTerm.scale reads, so ability scaling cannot
                                                //   drift while slots stay frozen (DF07_002 HIGH-2)
    pub threat_table: BTreeMap<(ActorRef, ActorRef), i32>,          // COMB_003 §3 — (observer, target)
    pub current_target: BTreeMap<ActorRef, ActorRef>,               // COMB_003 §4.2 hysteresis anchor
    pub cooldowns: BTreeMap<(ActorRef, AbilityId), u8>,             // ABL_001 §7.2 — decremented per round
    pub group_pools: BTreeMap<ActorRef, GroupPool>,                 // Untracked bulk groups — see below
    pub origin_spawn_group: Option<SpawnGroupId>,                   // COMB_005 §9 — COMB_004 anti-farm key
}

/// The pooled body of an Untracked `EngineDriver` group (AC-COMB-7). One row per group, keyed by the
/// group's single `ActorRef` — the same identity COMB_003 §6.1 uses for its one-observer threat rows.
pub struct GroupPool {
    pub max: u32,          // DF07 supplies the ceiling: archetype.MaxHp × member_count (DF07 §9)
    pub current: u32,      // damage to any member subtracts here; there is no per-member HP
    pub member_count: u16, // decremented for display/AV only; the pool is the real body
}
```

> **Why these are fields here rather than aggregates elsewhere.** Each is meaningful only *within* an
> encounter and meaningless after it. Hosting them on the session that already has the right lifetime
> means COMB_003, COMB_004, COMB_005 and ABL_001 together add **exactly one** new persistent-ish structure
> across the whole family (COMB_004's `spoils_claim`, §7 there), and the per-round checkpoint already
> covers them for replay.
>
> **⚠ `group_pools` added 2026-07-26 by the `/review-impl` seam pass (DF07_002 §1.5 HIGH-1).** It was the
> family's one genuinely missing structure: AC-COMB-7 required a pooled HP bar, COMB_004 SPO-A1/A6 fire
> loot generation *when that pool reaches zero*, and DF07 §9 supplied its ceiling — but nothing declared
> where the **current** value lived, and Untracked actors hold no RES_001 `vital_pool` row (AIT-A8). Since
> Untracked is the default tier for every COMB_005 spawn, the default enemy path was unimplementable and
> the loot trigger read a value nothing stored. **Ownership:** COMB_001 owns the structure and its
> decrement; DF07 supplies `max`; COMB_004 reads `current == 0` as its Untracked finalisation trigger;
> COMB_005 supplies `member_count` at formation. A group's members have no individual HP by construction —
> that is the point of the pooled model, and it is why no per-member KO exists to reverse (SPO-A1).
- **Lifecycle:** Born `EVT-T4 CombatSessionBorn` → mutated per round `EVT-T3 CombatRoundDelta` → removed
  `EVT-T4 CombatSessionResolved`. **In-memory + per-round checkpoint** (replay-recoverable, TDIL-A9).
- **Ephemeral** like RTM position (RTM-A1): not in the canonical event log beyond the lifecycle + round
  deltas; the *outcomes* (HP/status/KO) commit to the durable aggregates (RES_001 vital_pool, PL_006
  actor_status, PCS_001/WA_006 mortality).

---

## §3 — Action set V1 + action economy

Closed `allowed_tools` set (AGT-A2) for a combatant, V1: **Strike · Defend · Skill · UseItem · Flee**
(payloads + per-turn caps per concept §6). **Tactical-grid economy (TG-A3):** each turn grants a
**movement budget** (≤ `move_range`, A* path) **and** one action, in either order. The concept-notes
"No Move verb V1" is **superseded** — movement is a turn phase, not a competing verb.

| Tool | Payload | Engine effect |
|---|---|---|
| `Strike` | `{ target }` | melee adjacency or ranged range+LoS (TG); damage via §4 law-chain (engine-sourced, **no `damage_amount`**). Weapon contributes only through the DF7 snapshot + `InstrumentTag` — no item field enters the chain |
| `Defend` | — | applies `defending` (PL_006; 50% next-hit reduction) |
| `Skill` | `{ ability_id, target? }` | **ABL_001** `AbilityDecl` — cost, range/LoS, cooldown and effects all declared there; `Damage` ops re-enter the §4 chain via `PowerTerm` (ABL-A3) |
| `UseItem` | `{ item_instance_id, target? }` | **PL_007** possession + context gate, then the item's declared use-effect; consumption happens only on successful resolution |
| `Flee` | — | speed-vs-fastest-hostile roll; success → exits encounter (and clears the actor's COMB_003 threat rows) |

> **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 — `Skill` is typed (resolves AUD-F10).** The verb keeps its
> player-facing name, but `skill_id` was never a declared type: the concept notes said *"V1 skills come
> from PROG_001 skill kinds"*, which cannot work — a PROG kind is a number that grows, not an effect you
> fire (ABL-A1). `Skill` takes an **`AbilityId`**. Consequently `combat.skill_unknown` and
> `combat.skill_insufficient_stamina` delegate to `ability.unknown` / `ability.insufficient_resource`, and
> `combat_session.cooldowns` hosts ABL's encounter-ephemeral cooldown state (§2).

---

## §4 — Deterministic engine (engine-owned)

> **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 — DF07_001 Actor Stat Block DRAFT (resolves AUD-F6).** The
> law-chain's stat inputs now have a defined producer: `strike_power` / `armor` / `acc` / `dodge` /
> `crit_mult` / `crit_chance` / `speed` are **DF7 stat slots**, and `move_range` (TG-A3) is derived from
> `Speed` via `stat_tuning`. Three bindings apply:
> (a) **Snapshot, not live-read** — each combatant's block is resolved once at `CombatSessionBorn`, stored
> in `combat_session` with its `StatEpoch`, and refreshed only at **round boundaries** when the epoch
> changes (DF7-Q5) — never mid-action.
> (b) **Fixed-point** — stat resolution is integer milli-unit math (DF7-A4); `acc`/`dodge`/`crit_chance`
> are per-mille slots (÷1000 at use), so `hit_chance = clamp(0.5 + acc − dodge, 0.05, 0.95)` is unchanged
> in meaning. The seeded damage/crit rolls stay here, in the resolution layer.
> (c) **Crit is V1** — this reverses PROG-D25 (crit deferred), which the locked seed roles
> (`role ∈ {damage, crit, hit, position}`) already assumed (DF7-Q11).
> `defending`, `slowed`/`hasted`/`stunned` (AV mutations) and `knocked_out` stay **resolution-time and
> COMB-owned** — they are explicitly *not* stat modifiers (DF7-A8), and registering one as such trips
> validator DF7-V6. See [DF07_001 §8](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md).

- **Damage law-chain (4-step, LOCKED, concept §5.1):** `base = max(1, atk.strike_power − def.armor)` →
  `× elem_mult` (V1 1.0) → `× (1 − resist)` (V1 0) → `× roll(0.85–1.15) × crit_mult`; **status applies
  AFTER damage**. V1 collapse: `floor(max(1, sp − armor) × roll × crit)`. Chain *order* is locked for V1+
  DF7 promotion.
- **Hit/dodge:** `hit_chance = clamp(0.5 + acc − dodge, 0.05, 0.95)`; miss → damage 0 + MissEvent.
- **Initiative (HSR action value, Q7):** `av = 10000/speed`; lowest acts; reset on act; status mutates AV
  (`slowed +20%`, `hasted −20%`, `stunned +100%`); initiator first-turn AV ×0.75.
- **Win/lose:** all hostiles HP=0 → Victory; all friendlies HP=0 → Defeat → WA_006 mortality; all-Flee →
  Disengaged/Routed. For an Untracked group, "HP=0" means `group_pools[group].current == 0` (§2).
- **Status expiry inside an encounter (engine-owned; added 2026-07-26, DF07_002 §1.5 MED-4).** The engine
  decrements every round-scoped status at the round boundary and emits the expiry in `CombatRoundDelta` —
  `knocked_out` (`ko_duration_rounds`, AC-8), `defending` (consumed by the next hit), the `slowed` /
  `hasted` / `stunned` AV mutations, and ABL_001 `StatusApply { duration_rounds }`. This is stated because
  **PL_006 V1 has no auto-expire at all** (manual dispel only; the `Scheduled:StatusExpire` scheduler is
  V1+30d), so three docs were assuming an expiry mechanism that did not exist and a 3-round debuff would
  have been permanent. In-combat expiry is COMB-owned and round-scoped — consistent with DF7-A8, which
  already puts these same flags on the resolution-time side of the boundary. The PL_006 scheduler remains
  the owner for out-of-combat, fiction-time expiry (ABL_001 §7.3's conversion).
- **Seed (Q8):** `(reality_id, turn_id, actor_id, action_idx, role)` with `role ∈ {damage, crit, hit,
  position, **loot**}`; `action_idx` monotonic per `combat_session.next_action_idx`. Hidden V1;
  `combat_seed_visible` dev-mode V1+.
  > **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 (b) — role `bind` added** (COMB_004 §16 Binding Contest, with
  > COMB_006 PvP). The severance path may carry variance (tier resistance, partial success); putting it in
  > the seed family keeps binding loss replay-exact, which matters more here than anywhere else in the
  > family — under full-permadeath PvP (PVP-A4) a non-reproducible binding loss is an unrecoverable,
  > unauditable one. Roles are now `{damage, crit, hit, position, loot, bind}`.
  >
  > **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 — role `loot` added** (COMB_004 SPO-A2). Reward rolls join the
  > same seed family, so drops replay byte-identically alongside damage. **No other role was added:**
  > COMB_003 threat is deterministic and seedless (THR-A2), and COMB_005 population seeds off
  > `blake3(reality_id, channel_id, decl_index, epoch)` — the TMP_001/CSC_001 generation family, not this
  > per-action one, because population is a property of a *place and a time*, not of an action.

---

## §5 — Tactical-grid integration (retires §11.1/§11.2)

Positioning is **literal**, per [`COMB_002`](COMB_002_tactical_grid.md): a square grid (CSC_001 16×16 for
cell combats / deterministic arena for wilderness), move-then/and-act budgets, Chebyshev range +
corner-line LoS, obstacles from fixtures/terrain. **Front/Back row damage modifiers are retired** —
melee needs adjacency, ranged needs range+LoS, so "back-row safety" is emergent. NPC positioning =
LLM-chosen **bounded stance** (TG-A4), engine-resolved tile. All spatial math is engine-owned (TG-A1).

---

## §6 — Encounter, sides, mortality, anti-grief

- **Encounter SM (Q2):** `Idle —Strike on Hostile→ CombatActive —win/lose/flee→ Resolved → Idle`; 1
  PL_001 turn = 1 round. **Triggers:** PC Strike on non-Allied · Hostile NPC Strike on PC · **COMB_005 §5
  aggro engagement**. Rejects Strike on Allied/Neutral-civilian.
  > **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 — trigger 3 is V1 active** (COMB_005, resolves AUD-F9). It read
  > *"(V1+30d) Lex ambush"* — a stub for a general problem. It is now the COMB_005 §5 engagement predicate
  > (radius + LoS + FAC stance + safety band, engine-only per SPN-A5); Lex ambush becomes one
  > `HostilityRule` case rather than the whole mechanism. Formation, arena choice and the COMB_003 threat
  > handoff are COMB_005 §6.
- **Sides (Q5):** FAC_001-derived auto-bucketing into `sides: Vec<Side>` cap=2; encounter-local alliance.
  **Targeting within a side is COMB_003's** — threat accrual, hysteresis, and the top-K bounded candidate
  list handed to an LlmDriver (THR-A1/A4). Sides say *who is an enemy*; threat says *which one*.
- **Mortality / KO (Q3):** HP=0 → PL_006 `knocked_out` (revivable; `ko_duration_rounds` V1=5) → on-expire
  WA_006 Dying, per reality `combat_mortality_config` + per-actor `mortality_role` (Standard/Bypass).
  > **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 — loot rolls at finalisation, never at KO** (COMB_004 SPO-A1).
  > Because KO is *revivable* for 5 rounds, generating spoils at HP=0 would let a party loot a body and
  > then revive it — minting items from a reversible state. `roll_spoils` fires exactly once, at WA_006
  > mortality finalisation (or at group-pool zero for Untracked bulk groups), guarded for idempotency by
  > SPO-V4. KO also clears the actor's COMB_003 threat rows, so a downed body stops drawing fire.
- **Disparity cap (Q4):** reality `combat_disparity_cap` (5 sub-fields incl. `apply_to_pve_in_safe_zone`,
  V1 default true) + WA_001 Lex axiom + PF_001 `combat_safety` compose to cap damage (flat 50%/blow) in
  safe zones — anti-grief.
- **Stat hiding (Q6):** self/party exact; hostile = HP bar % + 5-tier vague label (LLM narration coherence).

---

## §7 — Boundary surface (this feature owns)

- **Aggregate:** `combat_session` (ephemeral) + `tactical_grid` (COMB_002; ephemeral).
- **EVT-T4:** `CombatSessionBorn`, `CombatSessionResolved`. **EVT-T3:** `CombatRoundDelta`. **EVT-T8:**
  `Forge:CancelCombat` (admin escape hatch).
- **`combat.*` rule_id namespace** (V1): `action_invalid_in_state` · `strike_target_allied` ·
  `strike_target_neutral_civilian` · `out_of_range` · `los_blocked` · `move_exceeds_budget` ·
  `tile_occupied` · `skill_unknown` · `skill_insufficient_stamina` · `flee_failed` (+ V1+ reservations).
- **COMB-V validators** (V1): COMB-V1 intent-valid-in-CombatActive · V2 target-side-eligible · V3
  range/LoS (TG) · V4 move-budget (TG) · V5 stamina · V6 disparity-cap (Lex compose) · V7 seed-determinism
  assertion.
- **RealityManifest extensions** (§13): `combat_disparity_cap` · `combat_mortality_config` ·
  `initiative_system` · `side_default_setup` · `combat_seed_visible` (V1+).
- **`COMB-*` stable-ID prefix** (promoted from reserved 2026-06-20).

### §7.1 — Family surface added 2026-07-26 (registered by the siblings, listed here for one-stop review)

| Surface | Owner | Note |
|---|---|---|
| `THR-*` prefix · `threat.*` rejects (6) · `ThreatConfig` manifest field | COMB_003 | **no aggregate** — `threat_table` is a `combat_session` field (§2) |
| `SPO-*` prefix · `spoils.*` rejects (8) · `loot_tables` manifest field · `Forge:EditLootTable` | COMB_004 | one ephemeral `spoils_claim` — the family's only new structure |
| `SPN-*` prefix · `spawn.*` rejects (8) · `hostile_spawns` on `PlaceDecl` + `TerrainSpawnDecl` · `Forge:EditSpawnDecl` | COMB_005 | **no aggregate** — population is derived (SPN-A2) |
| `ABL-*` prefix · `ability.*` rejects (12) · `abilities` manifest field | ABL_001 | **no aggregate** — known-set derived, cooldowns in `combat_session` |

**Net new aggregates across the whole closure: zero.** Everything either derives, or lives inside the
already-ephemeral `combat_session`, or reuses an owner that exists — which is why the `combat.*` reject
namespace and the `combat_session` shape are the only COMB_001 surfaces that changed at all.

---

## §8 — Acceptance criteria (AC-COMB-1..12)

Per concept §16; **AC-COMB-3 rewritten for the tactical grid**:

1. Strike determinism (same seed+stats → same damage on replay).
2. HSR AV ordering + 3 status AV mutations.
3. **(rewritten)** Tactical-grid positioning: melee requires adjacency, ranged requires range+LoS;
   move-budget enforced; obstacle/occupied tiles block; engine-resolved NPC stance (TG-A4). *(Replaces the
   retired Front/Back-row modifier AC.)*
4. FAC-derived side bucketing (`sides` cap=2; encounter-local alliance).
5. Major NPC LlmDriver structured-action validation + fallback Defend; 3 tiers + IDF_003 archetype.
6. Minor NPC ScriptDriver reaction lookup (zero LLM).
7. Untracked EngineDriver bulk resolve (group HP pool; single mean-speed AV entry).
8. KO → Dying per reality config; `knocked_out` 5-round lifecycle.
9. Status applies AFTER damage (law-chain order invariant); bleed DoT.
10. A6 canon-drift on narration contradicting ResolutionResult; 5-tier vague-label discipline.
11. Newbie-zone ambush anti-grief (Q4 PvE-in-safe-zone cap path; PF_001 validator — **now enforced at
    schema stage by COMB_005 SPN-V4**, see §9 item 8).
12. Boss `Bypass` + PC `Standard` mortality asymmetry in time-dilated chamber (per-actor `mortality_role`).

### §8.1 — Added at CANDIDATE-LOCK (AC-COMB-13..18)

13. **End-to-end encounter** — a PC walks into a forest tile with a declared wolf spawn: COMB_005
    materialises the group and fires engagement, COMB_001 forms the session on a COMB_002 wilderness arena,
    COMB_003 seeds threat, rounds resolve, WA_006 finalises, COMB_004 awards spoils and progression. **No
    step requires a doc that does not exist** — this is the criterion the DRAFT could not meet.
14. **Ability through the chain** — a `Skill` whose `Damage` op declares `PowerTerm { StrikePower ×1.8 }`
    produces damage via §4 steps 1–4 including hit roll and crit, **not** a direct HP write (ABL-A3).
15. **Snapshot atomicity across the family** — a mid-round equipment change, progression tick or status
    application does not alter that round's damage; it applies at the next round boundary via the DF7
    `StatEpoch` refresh recorded in `CombatRoundDelta`.
16. **Full replay equality** — the same encounter replays byte-identically in damage, target choices
    (THR-V6), spoils (SPO-V6) and population (SPN-V7). Any one of the four failing localises the defect to
    exactly one sibling.
17. **Agent containment** — across a full encounter an LlmDriver cannot: emit a number (COMB-A1), a tile
    (TG-A1), a target outside the top-K list (THR-A4), an ability outside its filtered set (ABL-A6), a drop
    (SPO-A3), or an encounter (SPN-A5). Each violation has its own reject and its own fallback.
18. **Zero-declaration reality** — a manifest declaring no `stat_slots`, `item_defs`, `abilities`,
    `loot_tables` or `hostile_spawns` still plays: unarmed strikes at DF7 defaults, PC-initiated combat
    only, no drops, no error. Composability is preserved at every layer.

---

## §9 — Closure-pass-extensions (10; applied as dated notes 2026-06-20)

Declared per concept §14.11. Applied as **dated additive notes** on each target (full schema lands when
each feature is next opened — the track's behavioral-closure pattern):

1. **PROG_001 §9** — REVERSE Strike formula (LLM-proposes → engine-computes 4-step chain).
2. **PL_005 Strike** — drop `damage_amount`; combat-mode intent restriction (`combat.action_invalid_in_state`).
3. **PL_006** — register `slowed`/`hasted`/`stunned` (AV mutations) + `knocked_out` (KO→Dying).
4. **NPC_002** — combat-mode AssemblePrompt (3 tiers) + structured ActionDecl = the **LlmDriver** combat impl.
5. **AIT_001** — `minor_behavior_scripts.combat_reaction_table` = the **ScriptDriver** combat impl + `combat_role` dispatch.
6. **WA_006** — KO-intermediate semantic (doc note; no schema change).
7. **WA_001** — Lex axiom `combat_damage_cap_in_safe_zone` (PvP + PvE paths, Q4).
8. **PF_001** — `combat_safety: CombatSafetyLevel` on PlaceDecl + NewbieZone high-tier-spawn validator.
   ✅ **RESOLVED 2026-07-26** — the validator declared here and never built is **COMB_005 SPN-V4** (§8
   there). Enforced at **schema stage**, so a reality with a high-tier spawn in a Newbie zone cannot load;
   `PlaceDecl` also gains `hostile_spawns: Vec<HostileSpawnDecl>`.
9. **ACT_001** — `mortality_role` on CanonicalActorDecl + `combat_role` on actor_chorus_metadata.
10. **RealityManifest** — combat config fields (§7).

### §9.1 — Closure status at CANDIDATE-LOCK (2026-07-26)

| # | Target | Status |
|---|---|---|
| 1 · 2 · 3 | PROG_001 §9 · PL_005 Strike · PL_006 statuses | ✅ applied 2026-06-20 (DRAFT cycle) |
| 8 | PF_001 NewbieZone validator | ✅ **resolved this cycle** — COMB_005 SPN-V4 |
| 4 · 5 | NPC_002 combat AssemblePrompt · AIT_001 `combat_reaction_table` | ⏳ declared — both now have concrete payload specs to implement against (COMB_003 §6.2 candidate list; ABL_001 §8.2 driver table; THR-V2 / ABL-V5 schema gates) |
| 6 · 7 · 9 · 10 | WA_006 KO semantic · WA_001 Lex axiom · ACT_001 fields · RealityManifest | ⏳ declared — behavioural-closure deferral, unchanged by this cycle |

**New closure items raised by the family** (each recorded in its own doc, listed here so the combat
surface is reviewable in one place): COMB_004 §12 (`ItemOrigin::Loot` → V1 active; WA_006 finalisation
hook; `Forge:EditLootTable`) · COMB_005 §11 (`PlaceDecl.hostile_spawns`; `TerrainSpawnDecl`;
`Generated:UntrackedNpcSpawn` payload; `Forge:EditSpawnDecl`) · ABL_001 §10 (`UseEffectDecl` ⊂ `EffectOp`
merge — **proposed, requires PL_007 owner agreement, not applied unilaterally**).

## §10 — Deferred (V1+) · open questions

**Deferred V1+:** retaliation, elevation, soft cover, AoE, 2-tile units (per COMB_002 §11); DF7
element/resistance promotion; condition-core PL_006 enrichment; mid-encounter reinforcements and summons
(SPN-D4 / ABL-D7 — both blocked on `combat_session.sides` being fixed at Born, now stated as a rule in
COMB_005 §6.1 rather than an implicit consequence).

### §10.1 — Open questions resolved (2026-07-26 edge-case pass)

**COMB-Q1 — wilderness-arena size tuning. RESOLVED: 16×16 is locked as the default; the residue is a
balance parameter, not an open design question.** The size is already author-configurable (COMB_002 TG-D2)
and 16×16 is chosen for CSC_001 parity, which is what lets cell and wilderness combat share one substrate
with no second geometry path. "Is 16×16 the *right* size" cannot be answered from a document — it needs
play data — and holding a design question open for a tunable constant conflates the two. **Reclassified as
a tuning parameter** (`arena_size`, already in the manifest) and closed as a question.

**COMB-Q2 — multi-side (3+). RESOLVED for V1: unreachable by construction, and V1+ has a clean seam.**
The ambiguity was never the schema (`sides: Vec<Side>` always allowed it) but *what automatic engagement
does when a third faction arrives*. COMB_005 §6.1 now answers it exhaustively: **engagement never
manufactures a side** — a second hostile group joins the existing hostile side under encounter-local
alliance, an already-engaged actor's new aggressors join their existing session, and anything genuinely
three-sided is deferred. So V1 has no undefined behaviour, and V1+ multi-side becomes a pure *relaxation*
of one rule rather than a redesign. **Closed as a V1 question; retained as a V1+ feature.**

**COMB-Q3 — PvP. ✅ CLOSED 2026-07-26 → [`COMB_006_pvp_and_stakes.md`](COMB_006_pvp_and_stakes.md).**
This entry previously read *"remains open, and deliberately so"*. That was **wrong on the facts**, and the
deep dive that followed found why: PvP was never an open design question. **`PC-D2` locked *"PvP enabled
within a session"* on 2026-04-23**, deferring only the *consent model* to DF4/DF5 — where DF5 deferred it
again (DF5-D3 → V2) and DF4 remains CONCEPT-only. It was a **built decision with no mechanism**, and it
read as an open question only because no doc owned it.

- **The home was already assigned.** [`02_world_authoring/_index.md`](../02_world_authoring/_index.md)
  reserved `WA_NNN_pvp_consent` and wrote that *"the others have stronger affinity to their consumer
  (**PvP→combat**) — when those consumer features open, their author may choose to put the override in
  their own folder."* Combat opened; COMB_006 is that folder; the WA reservation is retired.
- **The prediction above held.** Every item this entry listed as missing is exactly what COMB_006 supplies
  (consent channels, defeat policy, item rules via COMB_004 §16, the disparity-cap waiver, REP/FAC
  consequence) — and the *"a consenting duel must be able to bypass the disparity cap"* line became
  **PVP-Q4**, which turned out to be the load-bearing rule of the whole design (§6 there).
- **The V1 posture is unchanged.** PvP remains **unreachable by default** — `pvp_policy` defaults to
  `None` (PVP-A2), so COMB_005 §5's predicate still never fires PC-on-PC in a reality that has not opted
  in. What changed is that opting in is now *possible and specified*, rather than undefined.

## §11 — Cross-references

- Concept + full derivation — [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md)
- Family — [`COMB_002`](COMB_002_tactical_grid.md) · [`COMB_003`](COMB_003_threat_and_targeting.md) · [`COMB_004`](COMB_004_loot_and_spoils.md) · [`COMB_005`](COMB_005_encounter_spawning.md) · [`COMB_006`](COMB_006_pvp_and_stakes.md) · [`ABL_001`](../19_ability/ABL_001_ability_foundation.md)
- Consumed substrate — [`DF07_001`](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) · [`PL_007`](../04_play_loop/PL_007_item.md) · [`PL_007b`](../04_play_loop/PL_007b_inventory.md)
- Agent drivers — [`../../11_agent_decision_standard.md`](../../11_agent_decision_standard.md) (AGT-A3)
- Instanced scene — [`../../08_realtime_movement_authority.md`](../../08_realtime_movement_authority.md) (RTM-Q4)
- Authority — [`../../07_event_model/`](../../07_event_model/) (DP-A6, EVT-V*) · initiative/damage seed (Q7/Q8)
- Audit — [`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md) AUD-F5/F6/F9/F10
- Closure-pass targets — PROG_001 · PL_005 · PL_006 · NPC_002 · AIT_001 · WA_006 · WA_001 · PF_001 · ACT_001
