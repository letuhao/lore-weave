# IDF_001 — Race Foundation (CONCEPT)

> **Conversational name:** "Race" (RAC). Tier 5 Actor Substrate Foundation feature owning the per-reality `race` closed-set enum + per-actor `race_assignment` aggregate. Cross-actor uniformity: same enum + aggregate referenced by future PCS_001 (PC) + NPC_003 (NPC). Foundation discipline mirrors EF_001's ActorId pattern — own the closed-set once, consume from many.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** CONCEPT 2026-04-26 (Phase 0 — awaiting user Q-decision approval before DRAFT promotion)
> **Stable IDs:** `RAC-A*` axioms · `RAC-D*` deferrals · `RAC-Q*` open questions (per ID catalog convention; registered in `_boundaries/02_extension_contracts.md` Stable-ID prefix table on DRAFT promotion)
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md) (sibling pattern); [WA_001 Lex AxiomDecl](../02_world_authoring/WA_001_lex.md) (race-gate hook at V1 Stage 4); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (display name type).
> **Defers to:** PCS_001 (PC race assignment via existing aggregate); NPC_003 mortality (race-affected lifespan / mortality_kind override); V1+ combat (race-affected ability access).

---

## §1 Concept summary

Every actor (PC + NPC) has exactly ONE race assignment per reality. Race is **birth-fixed and immutable V1** (V1+ may add reincarnation / soul-transmigration as racial transition events).

**V1 must-ship:**
- Closed-set `RaceId` per reality (5-7 races typical; reality-specific)
- Per-actor `race_assignment` aggregate (T2/Reality scope)
- `RaceDecl` declarative metadata: display_name (I18nBundle), default_lifespan_years, size_category, default_mortality_kind_override, allowed_lex_axiom_tags (V1+ Lex extension)
- Lex axiom gate hook: `AxiomDecl.requires_race: Option<Vec<RaceId>>` (V1+ at WA_001 closure pass; placeholder V1)
- RealityManifest extension `races: Vec<RaceDecl>` REQUIRED V1
- Reality presets ship 3 example race-sets:
  - **Wuxia/Tiên Hiệp** (5 races): Human (Phàm nhân) / Cultivator (Tu sĩ) / Demon (Yêu) / Ghost (Quỷ) / Beast (Thú yêu)
  - **Modern**: Human (1 race; degenerate case)
  - **Sci-fi** (3 races): Human / AlienX / AlienY (placeholder)

**V1+ deferred:**
- Race traits affecting combat (RAC-D1)
- Race-conflict opinion modifier (RAC-D2)
- Mixed-race lineage / hybrid races (RAC-D3)
- Reincarnation race transition (RAC-D4)
- Race transformation events (V2+ — e.g., Human → Demon via cultivation deviation)

---

## §2 Domain concepts (proposed)

| Concept | Maps to | Notes |
|---|---|---|
| **RaceId** | Stable-ID newtype `String` (e.g., `race_cultivator`, `race_human_modern`, `race_alien_x`) | Opaque language-neutral; per-reality scope. NOT an enum — closed-set per reality declared in RealityManifest. |
| **RaceDecl** | Author-declared per-reality entry | Declarative metadata: display_name (I18nBundle) + default_lifespan_years (u16; ~80 for Human, ~600 for Cultivator V1) + size_category (Small / Medium / Large / Huge) + default_mortality_kind_override (Option<MortalityKind> per WA_006 — e.g., Ghost → already-dead state) + allowed_lex_axiom_tags (Vec<String> for V1+ Lex gate). |
| **race_assignment** | T2 / Reality aggregate; per-(reality, actor_id) row | Generic for PC + NPC. Birth-fixed V1 — single immutable RaceId field + rationale field for audit. |
| **SizeCategory** | Closed enum: `Small / Medium / Large / Huge` | V1 closed set. Consumed by V1+ combat (size-vs-size modifier). |

**Cross-feature consumers:**
- Lex axiom (WA_001) — `requires_race` gate at Stage 4 lex_check
- Mortality (WA_006) — `default_mortality_kind_override` resolves race-default death mode
- NPC_002 priority (V1+) — race-conflict modifier in opinion drift (RAC-D2)
- PCS_001 (V1+) — PC creation form selects RaceId from reality's allowed set
- NPC_001 / NPC_003 — NPC creation declares RaceId

---

## §3 Aggregate inventory (proposed)

### 3.1 `race_assignment` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "race_assignment", tier = "T2", scope = "reality")]
pub struct RaceAssignment {
    pub reality_id: RealityId,
    pub actor_id: ActorId,            // EF_001 §5.1 source-of-truth
    pub race_id: RaceId,              // birth-fixed V1
    pub assigned_at_turn: u64,        // for audit (CanonicalSeed at reality bootstrap; RuntimeSpawn at PC creation)
    pub assigned_reason: AssignmentReason,
    pub schema_version: u32,
}

pub enum AssignmentReason {
    CanonicalSeed,                    // RealityBootstrapper assigned at world-build
    PcCreation,                       // PC creation form
    NpcSpawn,                         // NPC spawned via Forge / Generator
    AdminOverride { reason: String }, // Admin force-assigned
    // V1+ Reincarnation, RaceTransformation
}
```

- T2 + RealityScoped: per-actor across reality lifetime
- One row per `(reality_id, actor_id)` (assertion: every actor MUST have a race row)
- Birth-fixed V1; V1+ may add transition events with audit log

### 3.2 `RaceDecl` (RealityManifest declarative entry — not a runtime aggregate)

```rust
pub struct RaceDecl {
    pub race_id: RaceId,
    pub display_name: I18nBundle,                            // RES_001 §2.3
    pub default_lifespan_years: u16,                         // 80 / 600 / etc.
    pub size_category: SizeCategory,
    pub default_mortality_kind_override: Option<MortalityKind>, // WA_006 ref
    pub allowed_lex_axiom_tags: Vec<String>,                 // V1+ Lex gate (e.g., ["qigong", "blood_arts"])
    pub canon_ref: Option<GlossaryEntityId>,                 // optional canonical reference
}
```

---

## §4 Tier+scope (DP-R2 — proposed)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `race_assignment` | T2 | T2 | Reality | ~1 per turn (UI badge + Lex gate at Stage 4) | Once at actor birth (rarely-mutating; V1 immutable) | Per-actor across reality lifetime; eventual consistency on cross-session reads OK; V1 immutable — no T3 urgency. |

---

## §5 Cross-feature integration (proposed)

### 5.1 Lex axiom gate (V1+ at WA_001 closure)

`AxiomDecl` extended with `requires_race: Option<Vec<RaceId>>`. When set, Stage 4 lex_check reads agent's `race_assignment.race_id` and rejects if not in list.

```rust
// WA_001 extension (proposed; lock-claim required at WA_001 closure pass)
pub struct AxiomDecl {
    // ... existing fields ...
    pub requires_race: Option<Vec<RaceId>>,    // NEW V1+ from IDF_001
    pub requires_ideology: Option<Vec<IdeologyId>>, // NEW V1+ from IDF_005
}
```

V1 schema: optional fields present but V1 always None (no race-gated axioms shipped V1). V1+ first race-gated axiom (e.g., qigong restricted to Cultivator race) demonstrates the gate.

### 5.2 Mortality default override

WA_006 `mortality_config` reads race's `default_mortality_kind_override`. Example: race=Ghost → MortalityKind=AlreadyDead (Ghost actor never enters Alive state); race=Cultivator → MortalityKind=Permadeath (no respawn — cultivator death is final).

### 5.3 Reject UX (race.* namespace)

Proposed V1 rule_ids in `race.*`:
1. `race.unknown_race_id` — RaceId not declared in reality's RealityManifest.races
2. `race.assignment_immutable` — V1 attempt to mutate race_assignment.race_id rejected (V1+ reincarnation lifts this)
3. `race.lex_axiom_forbidden` — Stage 4 lex_check rejects axiom for actor's race (V1+ when first race-gated axiom ships)

V1+ reservations: `race.cross_reality_mismatch` (V2+); `race.transformation_invalid` (V2+).

---

## §6 RealityManifest extension (proposed)

```rust
pub struct RealityManifest {
    // ... existing fields ...
    pub races: Vec<RaceDecl>,         // NEW V1 from IDF_001
}
```

- REQUIRED V1 (every reality MUST declare ≥1 race; even Modern with just Human)
- Closed-set per-reality
- Race assignments at canonical bootstrap REFERENCE this list

**Example RealityManifest excerpt (Wuxia preset):**

```rust
RealityManifest {
    races: vec![
        RaceDecl {
            race_id: "race_human_phamnhan".to_string(),
            display_name: I18nBundle {
                default: "Mortal".to_string(),
                translations: HashMap::from([("vi", "Phàm nhân"), ("zh", "凡人")]),
            },
            default_lifespan_years: 80,
            size_category: SizeCategory::Medium,
            default_mortality_kind_override: None,  // uses reality default
            allowed_lex_axiom_tags: vec![],          // mortals have no special axioms V1
            canon_ref: None,
        },
        RaceDecl {
            race_id: "race_cultivator_tusi".to_string(),
            display_name: I18nBundle {
                default: "Cultivator".to_string(),
                translations: HashMap::from([("vi", "Tu sĩ"), ("zh", "修士")]),
            },
            default_lifespan_years: 600,
            size_category: SizeCategory::Medium,
            default_mortality_kind_override: Some(MortalityKind::Permadeath),
            allowed_lex_axiom_tags: vec!["qigong".to_string(), "spirit_sense".to_string()],
            canon_ref: Some("entity_cultivator_canonical".into()),
        },
        // ... 3 more races (Demon / Ghost / Beast)
    ],
    // ... other fields ...
}
```

---

## §7 V1 acceptance criteria (preliminary — final on DRAFT)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-RAC-1** | Reality declares Wuxia 5-race preset; PC LM01 created with race=Cultivator | race_assignment row committed for LM01 with race_id="race_cultivator_tusi"; UI displays Tu sĩ badge; lifespan=600yr |
| **AC-RAC-2** | NPC tieu_thuy declared at canonical seed with race=Phàm nhân | race_assignment row committed for tieu_thuy with race_id="race_human_phamnhan"; lifespan=80yr |
| **AC-RAC-3** | PC attempts race assignment with unknown RaceId | rejected with `race.unknown_race_id` |
| **AC-RAC-4** | PC attempts mutation of existing race_assignment.race_id | rejected with `race.assignment_immutable` (V1; V1+ reincarnation lifts) |
| **AC-RAC-5** | Reality WA_006 mortality_config reads race=Ghost actor | resolves to MortalityKind=AlreadyDead per race override |
| **AC-RAC-6** (V1+) | Lex axiom requires_race=[Cultivator] gates qigong; Phàm nhân tries qigong | rejected with `race.lex_axiom_forbidden` at Stage 4 |
| **AC-RAC-7** | I18nBundle resolves Tu sĩ in Vietnamese UI; Cultivator in English UI | display_name.translations["vi"] = "Tu sĩ"; default = "Cultivator" |

---

## §8 Open questions (CONCEPT — user confirm before DRAFT)

| ID | Question | Default proposal |
|---|---|---|
| **RAC-Q1** | Race assignment — birth-fixed V1 (current proposal) vs allow Admin override V1? | **Birth-fixed V1** with `AdminOverride` reason variant for forensic-only edits (V1 ships AdminOverride path; not user-facing) |
| **RAC-Q2** | RaceId namespace — opaque string per reality (current) vs global enum across realities? | **Opaque string per reality** — different realities have different races; no cross-reality enum collision |
| **RAC-Q3** | Default lifespan — single u16 years (current) vs distribution (mean + stddev)? | **Single u16 V1** — distribution is V1+ enrichment (RAC-D5); deterministic per-actor lifespan only when needed for scheduler V1+30d |
| **RAC-Q4** | SizeCategory — 4 variants (Small/Medium/Large/Huge) vs 5 (add Tiny) vs 6 (add Tiny + Gargantuan)? | **4 variants V1** (Small/Medium/Large/Huge); V1+ extends additively |
| **RAC-Q5** | `allowed_lex_axiom_tags` — list of strings (current) vs typed `Vec<AxiomTag>` enum? | **List of strings V1** — axiom tags evolve with WA_001; typed enum couples too tightly. V1+ may type. |
| **RAC-Q6** | RealityManifest `races` REQUIRED (every reality declares ≥1 race) vs OPTIONAL (default to "Human" implicit)? | **REQUIRED V1** — explicit always; mirrors PF_001 places REQUIRED pattern |
| **RAC-Q7** | Cross-reality PC migration — V1 strict (PC bound to one reality) vs V2+ (race remap on migration)? | **V1 strict per WA_002 Heresy contamination boundary**; V2+ migration adds remap policy |
| **RAC-Q8** | Race-conflict opinion modifier scope — defer to V1+ (current) or include V1 minimal table? | **Defer V1+** (RAC-D2) — V1 personality-driven opinion drift sufficient; race-modifier is overlay |
| **RAC-Q9** | `default_mortality_kind_override` — applied at canonical bootstrap (current) vs per-event lookup at runtime? | **Per-event lookup at runtime** — race may be admin-edited; runtime lookup ensures correctness |
| **RAC-Q10** | Reality preset ship V1 — 3 presets (Wuxia/Modern/Sci-fi) vs only 1 (Wuxia for SPIKE_01)? | **3 presets** but only Wuxia validated by integration test V1 (Modern + Sci-fi schema-tested only) |

---

## §9 Deferrals (V1+ landing point)

| ID | Item | Defer to |
|---|---|---|
| **RAC-D1** | Race traits affecting combat (Cultivator HP modifier; Demon damage modifier; Beast natural weapons) | V1+ combat feature |
| **RAC-D2** | Race-conflict opinion modifier (Cultivator vs Demon = -10 opinion baseline) | V1+ NPC personality enrichment |
| **RAC-D3** | Mixed-race lineage / hybrid races (half-Demon, half-Human) | V1+ origin/lineage feature (IDF_004) |
| **RAC-D4** | Reincarnation race transition (Cultivator dies → reborn as Human child) | V1+ scheduler + V1+30d auto-respawn flow |
| **RAC-D5** | Lifespan distribution (mean + stddev for variance) | V1+ when scheduler needs deterministic per-actor lifespan |
| **RAC-D6** | Cross-reality race remap policy | V2+ Heresy migration |
| **RAC-D7** | RaceTransformation event sub-type (Human → Demon via deviation) | V2+ |
| **RAC-D8** | Race-driven appearance defaults (height range / typical features) | V1+ IDF_005 Appearance feature OR cosmetic V1+ |
| **RAC-D9** | Race-driven name pattern (Cultivator daoist names vs Phàm nhân village names) | V1+ IDF_004 Origin enrichment |
| **RAC-D10** | Race lifespan vs mortality interaction (Cultivator 600yr but death-by-Strike treated equally) | V1+ combat + WA_006 cross-design |

---

## §10 Cross-references

**Foundation tier:**
- [`EF_001`](../00_entity/EF_001_entity_foundation.md) §5.1 — ActorId source-of-truth
- [`PF_001`](../00_place/PF_001_place_foundation.md) §3.1 — RealityManifest extension pattern
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) §2.3 — I18nBundle for display_name

**Sibling IDF:**
- [`IDF_002 Language`](IDF_002_language_concept.md) — race may have native language hint (V1+ optional ref)
- [`IDF_003 Personality`](IDF_003_personality_concept.md) — independent
- [`IDF_004 Origin`](IDF_004_origin_concept.md) — origin pack may suggest default race (V1+)
- [`IDF_005 Ideology`](IDF_005_ideology_concept.md) — race + ideology jointly gate Lex axioms

**Consumers:**
- Future PCS_001 — PC creation form selects RaceId
- Future NPC_003 mortality — NPC race-affected lifespan / mortality
- WA_001 Lex (V1+ closure pass) — `AxiomDecl.requires_race` field
- WA_006 Mortality — `default_mortality_kind_override` lookup
- NPC_002 (V1+) — race-conflict opinion modifier (RAC-D2)

**Boundaries:**
- `_boundaries/01_feature_ownership_matrix.md` (DRAFT registers `race_assignment` aggregate)
- `_boundaries/02_extension_contracts.md` §1.4 (DRAFT registers `race.*` namespace + 3 V1 rules)
- `_boundaries/02_extension_contracts.md` §2 RealityManifest (DRAFT registers `races` extension)

---

## §11 CONCEPT → DRAFT promotion checklist

When user approves Q1-Q10:
- [ ] Lock-claim `_boundaries/_LOCK.md`
- [ ] Rename file: `IDF_001_race_concept.md` → `IDF_001_race.md`
- [ ] Promote header status CONCEPT → DRAFT
- [ ] Lock all Q1-Q10 decisions; remove §8 (replace with §8 Pattern choices)
- [ ] Add full §1-§19 spec mirroring [EF_001](../00_entity/EF_001_entity_foundation.md):
  - §2 Domain concepts (locked)
  - §2.5 Event-model mapping
  - §3 Aggregate inventory
  - §4 Tier+scope
  - §5 DP primitives
  - §6 Capability JWT
  - §7 Subscribe pattern
  - §8 Pattern choices (replaces CONCEPT §8 Open questions)
  - §9 Failure UX (race.* namespace V1 rules)
  - §10 Cross-service handoff
  - §11-§14 Sequences (canonical seed / PC creation / mortality lookup / Lex gate)
  - §15 Acceptance criteria (AC-RAC-1..7 V1; AC-RAC-V1+1..N deferred)
  - §16 LOCK criterion split (DRAFT→CANDIDATE-LOCK vs CANDIDATE-LOCK→LOCK)
  - §17 Deferrals RAC-D1..D10
  - §18 Cross-references
  - §19 Implementation readiness checklist
- [ ] Register `race_assignment` aggregate in matrix
- [ ] Register `race.*` namespace in extension contracts §1.4 (3 V1 rules)
- [ ] Register `races: Vec<RaceDecl>` in RealityManifest §2 extension
- [ ] Register Stable-ID prefix `RAC-*` in extension contracts
- [ ] Append `99_changelog.md` row
- [ ] Lock-release (or hold for next IDF feature DRAFT)
