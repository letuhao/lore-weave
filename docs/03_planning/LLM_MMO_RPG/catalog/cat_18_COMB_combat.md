<!-- CHUNK-META
source: design-track manual seed 2026-07-26
chunk: cat_18_COMB_combat.md
namespace: COMB-*, TG-*, THR-*, SPO-*, SPN-*, PVP-*
generated_by: hand-authored (combat-family catalog seed at family closure)
-->

## COMB — Combat (domain-scale Tier 6; six docs, one family)

> Catalog for `features/18_combat/`. Created **2026-07-26** at family closure — the ownership matrix had
> carried *"cat_18_COMB_combat.md (NOT YET CREATED — defer to DRAFT-stable cycle)"* since 2026-06-20.
>
> **Not a foundation tier.** Foundation closed at PROG_001 (6/6). COMB consumes 6 V1 foundations + IDF +
> FF + FAC + REP + ACT + AIT + TDIL + PROG + RES + PL_006 + DF07 + PL_007. **Opt-in per reality** — a
> modern slice-of-life reality may have no combat at all.
>
> | Sub-prefix | Owner | What |
> |---|---|---|
> | `COMB-A*` / `COMB-D*` / `COMB-Q*` / `COMB-V*` | COMB_001 | spine axioms · deferrals · questions · validators |
> | `TG-A*` / `TG-D*` | COMB_002 | tactical grid |
> | `THR-*` | COMB_003 | threat & targeting |
> | `SPO-*` | COMB_004 | loot & spoils (incl. §16 Binding Contest) |
> | `SPN-*` | COMB_005 | encounter spawning |
> | `PVP-*` | COMB_006 | PvP & stakes |
>
> Sibling namespace: **`ABL-*`** ([`cat_19_ABL_ability.md`](cat_19_ABL_ability.md)) — homed outside
> `18_combat` because PL_005 `Use` calls it too.

**Net new aggregates across the whole family: zero.** Everything is derived, or hosted on the ephemeral
`combat_session`, or reuses an existing owner. Registered as a deliberate negative claim in
[`_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

### The encounter, end to end

```
COMB_005 spawns + engages → COMB_001 forms the session → COMB_003 seeds threat
   → rounds: COMB_001 initiative · COMB_002 movement/range · ABL_001 abilities · DF07 stats · PL_007 items
   → COMB_001 resolves win/lose → WA_006 finalises mortality → COMB_004 rolls spoils (+ Binding Contest)
   [COMB_006 gates whether a PC may be a participant at all]
```

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| COMB-1 | 3-layer architecture (engine math / AI-decide / narrate) — **COMB-A1 LLM-zero-math** | ✅ | V1 | AIT, NPC_002 | [COMB_001 §1](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-2 | `combat_session` ephemeral aggregate (+ stat snapshots, threat, cooldowns, group pools) | ✅ | V1 | DP, TDIL-A9 | [COMB_001 §2](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-3 | Action set — Strike / Defend / Skill / UseItem / Flee + move budget | ✅ | V1 | PL_005, ABL, PL_007 | [COMB_001 §3](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-4 | 4-step damage law-chain — **the sole damage authority** | ✅ | V1 | DF07 | [COMB_001 §4](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-5 | HSR action-value initiative (`av = 10000/speed`) + 3 status AV mutations | ✅ | V1 | DF07, PL_006 | [COMB_001 §4](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-6 | Seeded determinism — roles `{damage, crit, hit, position, loot, bind}` | ✅ | V1 | TDIL-A9 | [COMB_001 §4](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-7 | Encounter SM + FAC-derived sides (cap 2) + KO→Dying mortality | ✅ | V1 | FAC, WA_006 | [COMB_001 §6](../features/18_combat/COMB_001_combat_foundation.md) |
| COMB-8 | Disparity cap (Q4) + stat hiding (Q6, 5-tier vague label) | ✅ | V1 | WA_001, PF_001 | [COMB_001 §6](../features/18_combat/COMB_001_combat_foundation.md) |
| TG-1 | Tactical grid — square 16×16 (CSC parity / wilderness arena) | ✅ | V1 | CSC, TMP | [COMB_002 §2](../features/18_combat/COMB_002_tactical_grid.md) |
| TG-2 | Move + action budgets, either order (FFT/XCOM); A* movement | ✅ | V1 | TMP | [COMB_002 §3–§4](../features/18_combat/COMB_002_tactical_grid.md) |
| TG-3 | Chebyshev range + corner-line LoS; binary cover V1 | ✅ | V1 | — | [COMB_002 §5](../features/18_combat/COMB_002_tactical_grid.md) |
| TG-4 | **TG-A1 LLM-zero-space** + bounded NPC stance (kite/flank/cover) | ✅ | V1 | AGT-A2 | [COMB_002 §1, §6](../features/18_combat/COMB_002_tactical_grid.md) |
| TG-5 | Deterministic wilderness arena generator (first caller: COMB_005) | ✅ | V1 | TMP, CSC | [COMB_002 §7](../features/18_combat/COMB_002_tactical_grid.md) |
| THR-1 | Threat table on `combat_session` — deterministic, seedless accrual | ✅ | V1 | — | [COMB_003 §3](../features/18_combat/COMB_003_threat_and_targeting.md) |
| THR-2 | Per-round decay + **switch-margin hysteresis** (the anti-flicker rule) | ✅ | V1 | — | [COMB_003 §4](../features/18_combat/COMB_003_threat_and_targeting.md) |
| THR-3 | Closed 7-variant `TargetSelector` (replaces the `"lowest_hp_hostile"` string) | ✅ | V1 | AIT | [COMB_003 §5](../features/18_combat/COMB_003_threat_and_targeting.md) |
| THR-4 | **THR-A4** top-K vague-labelled candidate list for LlmDriver (flat token cost) | ✅ | V1 | AGT-A3, DF7-A10 | [COMB_003 §6.2](../features/18_combat/COMB_003_threat_and_targeting.md) |
| THR-5 | Accrual-stage anti-grief guard (THR-A6/Q7) | ✅ | V1 | PF_001 | [COMB_003 §7](../features/18_combat/COMB_003_threat_and_targeting.md) |
| SPO-1 | `LootTableDecl` keyed by `ActorClassRef` (shared with DF07 archetypes + SPN) | ✅ | V1 | DF07 | [COMB_004 §3](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-2 | Independent per-entry seeded rolls (not one weighted pick) | ✅ | V1 | COMB-6 | [COMB_004 §4](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-3 | **SPO-A1** rolls at defeat finalisation, **never at KO** | ✅ | V1 | WA_006 | [COMB_004 §5](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-4 | Spoils pile + `spoils_claim` loot-rights window | ✅ | V1 | PL_007b, EF_001 | [COMB_004 §6–§7](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-5 | Progression award — the reason a fight is worth having | ✅ | V1 | PROG | [COMB_004 §9](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-6 | Epoch-keyed anti-farm (`first_kill_only` + `loot_budget`) | ✅ | V1 | SPN | [COMB_004 §10](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-7 | **The Binding Contest** — `BindTier` on PROG_001's `BodyOrSoul` axis | ✅ | V1+ | PL_007, PROG | [COMB_004 §16](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-8 | Three defeasance paths: sunder · severance · **overwhelm** (Q4 read backwards) | ✅ | V1+ | COMB-8, ABL | [COMB_004 §16.4–§16.6](../features/18_combat/COMB_004_loot_and_spoils.md) |
| SPO-9 | Sunder (bind degradation) | 📦 | V1+ | **blocked: RES-D4** | SPO-D11 — needs PL_007 `durability` activated |
| SPN-1 | `HostileSpawnDecl` on `PlaceDecl` / TMP terrain | ✅ | V1 | PF_001, TMP | [COMB_005 §3](../features/18_combat/COMB_005_encounter_spawning.md) |
| SPN-2 | **Epoch respawn** — `floor((fiction_day + offset) / period)`; no timers, no roster | ✅ | V1 | PL_001, TDIL | [COMB_005 §4](../features/18_combat/COMB_005_encounter_spawning.md) |
| SPN-3 | **SPN-A9** edge-triggered materialisation (also yields anti-camp free) | ✅ | V1 | AIT, RTM | [COMB_005 §4.1](../features/18_combat/COMB_005_encounter_spawning.md) |
| SPN-4 | Aggro/engagement predicate — COMB_001's trigger-3 stub, generalised | ✅ | V1 | FAC, PF_001 | [COMB_005 §5](../features/18_combat/COMB_005_encounter_spawning.md) |
| SPN-5 | Encounter formation + collision rules (engagement never manufactures a side) | ✅ | V1 | COMB-7 | [COMB_005 §6](../features/18_combat/COMB_005_encounter_spawning.md) |
| SPN-6 | Tier promotion on engagement, **soft-fail** at capacity | ✅ | V1 | AIT, AGT-D5 | [COMB_005 §7](../features/18_combat/COMB_005_encounter_spawning.md) |
| SPN-7 | **Danger band / newbie-zone validator at schema stage** (COMB_001 closure item 8) | ✅ | V1 | PF_001 | [COMB_005 §8](../features/18_combat/COMB_005_encounter_spawning.md) |
| PVP-1 | Master gate `pvp_policy` — **defaults Disabled** (WA_006 defaults Permadeath) | ✅ | V1+ | WA_006 | [COMB_006 §2](../features/18_combat/COMB_006_pvp_and_stakes.md) |
| PVP-2 | **Duel** channel — mutual challenge, stakes at challenge time (`Spar` / `LifeAndDeath`) | ✅ | V1+ | DF05 | [COMB_006 §3](../features/18_combat/COMB_006_pvp_and_stakes.md) |
| PVP-3 | **ContestedZone** channel — a PF_001 band where entering *is* consent; no flag timer | ✅ | V1+ | PF_001 | [COMB_006 §4](../features/18_combat/COMB_006_pvp_and_stakes.md) |
| PVP-4 | Disparity-cap waiver — **pairwise**, and the licence for binding overwhelm | ✅ | V1+ | COMB-8, SPO-8 | [COMB_006 §6](../features/18_combat/COMB_006_pvp_and_stakes.md) |
| PVP-5 | Post-incarnation grace (closes permadeath spawn-camping) | ✅ | V1+ | PCS_001 | [COMB_006 §5.1](../features/18_combat/COMB_006_pvp_and_stakes.md) |
| PVP-6 | REP_001 notoriety as the social consequence | ✅ | V1+ | REP, FAC, ACT | [COMB_006 §7](../features/18_combat/COMB_006_pvp_and_stakes.md) |
| PVP-7 | `FactionWar` consent channel | 📦 | V1+ | **blocked: DIPL_001** | PVP-D1 — FAC `RelationStance` is static at seed |
| COMB-9 | Social skirmish (luận đạo / political confrontation) | 📦 | V1+30d | — | COMB-D2 |
| COMB-10 | Multi-side (3+) encounters | 📦 | V1+ | — | COMB-Q2 — `sides: Vec<Side>` already allows it |
| COMB-11 | Retaliation · elevation · soft cover · AoE · 2-tile units | 📦 | V1+ | — | [COMB_002 §11](../features/18_combat/COMB_002_tactical_grid.md) |
| COMB-12 | Multi-cell siege warfare | 📦 | V3+ | — | COMB-D4 |

**Legend:** ✅ designed · 📦 deferred (blocking dependency named where one exists).

### Audit findings closed by this family

| Finding | Closed by |
|---|---|
| **AUD-F1** V1 combat = tactical grid | COMB_002 (2026-06-20) |
| **AUD-F9** combat loop has no ends | COMB_003 (threat) · COMB_004 (loot) · COMB_005 (spawning) |
| **COMB-Q3** PvP | COMB_006 — also **discharges `PC-D2`** (locked 2026-04-23, never built) |

### Cross-references

- Family spine + map — [`COMB_001 §0`](../features/18_combat/COMB_001_combat_foundation.md)
- Folder index — [`features/18_combat/_index.md`](../features/18_combat/_index.md)
- Concept + market survey — [`00_CONCEPT_NOTES.md`](../features/18_combat/00_CONCEPT_NOTES.md)
- Boundary registration — [`_boundaries/99_changelog.md`](../_boundaries/99_changelog.md) (2026-07-26 entry)
- Audit — [`12_module_coverage_audit.md`](../12_module_coverage_audit.md)
