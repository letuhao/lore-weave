# COMB_001 — Combat Foundation (DRAFT)

> **Status:** **DRAFT 2026-06-20** — promoted from [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (Q1–Q9 ALL
> LOCKED 2026-04-27; concept notes remain the full derivation + market survey + chaos-backend reference).
> This DRAFT formalizes the locked combat model into the feature-doc structure, **integrates the
> tactical grid** ([`COMB_002_tactical_grid.md`](COMB_002_tactical_grid.md), TG-A1..A4 / decision AUD-F1)
> retiring the concept-notes §11.1/§11.2 abstract arena + Front/Back rows, and **expresses the 3-layer
> AI as Agent Decision Standard drivers** ([`../../11_agent_decision_standard.md`](../../11_agent_decision_standard.md)).
> **Owns** the `COMB-*` namespace, the `combat_session` aggregate, the `combat.*` reject namespace, and
> the combat EVT sub-types. Carries the 10 cross-feature closure-pass-extensions (§14).
> **Determinism + LLM-zero-math + LLM-zero-space are inviolable** (TDIL-A9 / §4 / TG-A1).

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
}
```
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
| `Strike` | `{ target }` | melee adjacency or ranged range+LoS (TG); damage via §4 law-chain (engine-sourced, **no `damage_amount`**) |
| `Defend` | — | applies `defending` (PL_006; 50% next-hit reduction) |
| `Skill` | `{ skill_id, target? }` | PROG_001 skill; stamina cost; range/LoS per skill |
| `UseItem` | `{ item_id, target? }` | consumes RES_001 inventory item |
| `Flee` | — | speed-vs-fastest-hostile roll; success → exits encounter |

---

## §4 — Deterministic engine (engine-owned)

- **Damage law-chain (4-step, LOCKED, concept §5.1):** `base = max(1, atk.strike_power − def.armor)` →
  `× elem_mult` (V1 1.0) → `× (1 − resist)` (V1 0) → `× roll(0.85–1.15) × crit_mult`; **status applies
  AFTER damage**. V1 collapse: `floor(max(1, sp − armor) × roll × crit)`. Chain *order* is locked for V1+
  DF7 promotion.
- **Hit/dodge:** `hit_chance = clamp(0.5 + acc − dodge, 0.05, 0.95)`; miss → damage 0 + MissEvent.
- **Initiative (HSR action value, Q7):** `av = 10000/speed`; lowest acts; reset on act; status mutates AV
  (`slowed +20%`, `hasted −20%`, `stunned +100%`); initiator first-turn AV ×0.75.
- **Win/lose:** all hostiles HP=0 → Victory; all friendlies HP=0 → Defeat → WA_006 mortality; all-Flee →
  Disengaged/Routed.
- **Seed (Q8):** `(reality_id, turn_id, actor_id, action_idx, role)` with `role ∈ {damage, crit, hit,
  position}`; `action_idx` monotonic per `combat_session.next_action_idx`. Hidden V1; `combat_seed_visible`
  dev-mode V1+.

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
  PL_001 turn = 1 round. **Triggers:** PC Strike on non-Allied · Hostile NPC Strike on PC · (V1+30d) Lex
  ambush. Rejects Strike on Allied/Neutral-civilian.
- **Sides (Q5):** FAC_001-derived auto-bucketing into `sides: Vec<Side>` cap=2; encounter-local alliance.
- **Mortality / KO (Q3):** HP=0 → PL_006 `knocked_out` (revivable; `ko_duration_rounds` V1=5) → on-expire
  WA_006 Dying, per reality `combat_mortality_config` + per-actor `mortality_role` (Standard/Bypass).
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
11. Newbie-zone ambush anti-grief (Q4 PvE-in-safe-zone cap path; PF_001 validator).
12. Boss `Bypass` + PC `Standard` mortality asymmetry in time-dilated chamber (per-actor `mortality_role`).

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
9. **ACT_001** — `mortality_role` on CanonicalActorDecl + `combat_role` on actor_chorus_metadata.
10. **RealityManifest** — combat config fields (§7).

## §10 — Deferred (V1+) · open questions

V1+: retaliation, elevation, soft cover, AoE, 2-tile units (per COMB_002 §11); DF7 element/resistance
promotion; condition-core PL_006 enrichment. Open: COMB-Q1 wilderness-arena size tuning; COMB-Q2
multi-side (3+) V1+ (Q5 schema already `Vec<Side>`).

## §11 — Cross-references

- Concept + full derivation — [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md)
- Tactical grid — [`COMB_002_tactical_grid.md`](COMB_002_tactical_grid.md) (TG-A1..A4, AUD-F1)
- Agent drivers — [`../../11_agent_decision_standard.md`](../../11_agent_decision_standard.md) (AGT-A3)
- Instanced scene — [`../../08_realtime_movement_authority.md`](../../08_realtime_movement_authority.md) (RTM-Q4)
- Authority — [`../../07_event_model/`](../../07_event_model/) (DP-A6, EVT-V*) · initiative/damage seed (Q7/Q8)
- Closure-pass targets — PROG_001 · PL_005 · PL_006 · NPC_002 · AIT_001 · WA_006 · WA_001 · PF_001 · ACT_001
