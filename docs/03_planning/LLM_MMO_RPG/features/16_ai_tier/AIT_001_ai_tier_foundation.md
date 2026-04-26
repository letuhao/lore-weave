# AIT_001 — AI Tier Foundation

> **Category:** AIT — AI Tier (architecture-scale companion to PROG_001 + NPC_001; defines 3-tier NPC architecture for billion-NPC scaling)
> **Catalog reference:** [`catalog/cat_16_AIT_ai_tier.md`](../../catalog/cat_16_AIT_ai_tier.md) (owns `AIT-*` stable-ID namespace)
> **Status:** DRAFT 2026-04-27 — All 12 critical scope questions LOCKED via 4-batch deep-dive 2026-04-26..27 (Q1+Q2 / Q4+Q5+Q11 / Q6+Q12 / Q7+Q8+Q9; Q3 + Q10 implicit). Companion: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q12 LOCKED matrix §16).
>
> **CLOSURE-PASS-EXTENSION 2026-04-27 (TDIL_001 DRAFT promotion):** §7.5 Tracked NPC lazy materialization formula REVISED from per-day replay to O(1) elapsed-time computation per TDIL-A3 + TDIL-A7. Mechanical revision: when a Tracked NPC's progression is materialized after N turns of cross-realm absence (e.g., mortal PC observes heaven NPC after Tây Du Ký 365× elapsed time), computation is `delta = base_rate × elapsed_time × multiplier` ONE-SHOT — NOT a 365-iteration loop. The Schrödinger pattern (PCs eager + Tracked NPCs lazy) is preserved; the materialization cost is now constant regardless of elapsed magnitude. Cross-realm observation O(1) per TDIL-A7 enables billion-NPC scale without per-day replay overhead. NO semantic change to user-facing behavior — all V1 acceptance scenarios AC-AIT-1..12 preserved. Affected sections: §7.5 lazy materialization formula (replay loop → O(1) computation), §7.5 cross-realm observation (TDIL-A7 reference). Untracked NPC ephemeral generation per cell density tables unaffected (no progression to materialize). Per AIT-PROG cross-feature alignment (PROG-D19), Tracked NPC eager auto-collect → lazy migration V1+30d benefits from unified per-turn semantic. See [TDIL_001 §7.4 Cross-realm observation O(1)](../17_time_dilation/TDIL_001_time_dilation_foundation.md#74-cross-realm-observation-o1) for materialization formula and [TDIL_001 §6.4 closure-pass coordination](../17_time_dilation/TDIL_001_time_dilation_foundation.md#64-closure-pass-coordination) for cascade rationale.
> **i18n compliance:** Conforms to RES_001 §2 cross-cutting pattern — all stable IDs English `snake_case` / `PascalCase`; user-facing strings `I18nBundle`.
> **V1 testable acceptance:** 12 scenarios AC-AIT-1..12 (§16).
> **NOT a 7th foundation:** Foundation tier remains 6/6 (closed at PROG_001). AIT_001 is **architecture-scale Tier 5+ Actor Substrate scaling feature** that consumes PROG_001's reserved `tracking_tier` field + NPC_001's NpcId namespace.

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

User-stated requirement (CONCEPT_NOTES §1):

> "1 thế giới rộng lớn với hàng tỷ NPC, làm sao mô phỏng?"

Billion-NPC simulation needs tier-based existence. Eager Generator iteration over all NPCs is infeasible at scale. AIT_001 splits NPCs into 3 storage/behavior tiers + leverages quantum-observation principle (already locked in PROG_001 Q4 REVISED) for lazy materialization.

Without AIT_001:
- PROG_001's `tracking_tier: Option<NpcTrackingTier>` field is dead reservation
- NPC_001 NpcId namespace assumes uniform addressability — no scaling discipline
- LLM context budget unbounded — token cost explodes at scale
- RES_001 NPC eager auto-collect Generator stays architecturally inconsistent (PROG-D19 unresolved)
- Untracked NPC procedural generation undefined

AIT_001 owns these scaling decisions.

### V1 minimum scope (per Q1-Q12 LOCKED in CONCEPT_NOTES §16)

- **2-variant `NpcTrackingTier` enum** (Q1): `Major` / `Minor`. Untracked = absence of `actor_progression` aggregate (semantic).
- **PC distinguished**: `tracking_tier=None` on actor_progression (always tracked, eager Generator).
- **Author-required tier on `CanonicalActorDecl`** (Q2a) at NPC_001 closure pass.
- **Untracked never declared** (Q2b) — purely ephemeral; on-demand cell-entry generation.
- **Forge admin promotion V1** (Q2c): `Forge:PromoteUntrackedToTracked` AdminAction.
- **Deterministic Untracked NpcId** (Q2f): `blake3(reality_id || cell_id || fiction_day || slot_index)`.
- **TierCapacityCaps** (Q2h) RealityManifest field with engine defaults Major≤20 / Minor≤100.
- **Hybrid 2-stage Untracked generation** (Q4): Stage 1 template+RNG + Stage 2 LLM-flavor lazy.
- **UntrackedTemplateDecl** (Q4b) per PlaceType with role list.
- **Cell-entry generation timing** (Q5a) with daily rotation (Q5d).
- **Cell-leave + session-end discard** (Q6a-b); 5-variant UntrackedDiscardReason enum.
- **2 NEW EVT-T5 sub-types** (Q5e + Q6e): `Generated:UntrackedNpcSpawn` + `Generated:UntrackedNpcDiscarded`.
- **NpcId stable at promotion** (Q11a): persona crystallization into NPC_001 npc core.
- **MinorBehaviorScript pattern** (Q7b) per actor_class — DialogueTemplate + ScheduledActionDecl + ReactionDecl.
- **NPC_002 Chorus tier filter** (Q7e): Major full / Minor low-priority / Untracked excluded.
- **DensityDecl V1 fixed count** (Q8a) per PlaceType with 12-cap (Q8c) + engine defaults (Q8b).
- **Tier × InteractionKind matrix** (Q9a) enforced via NEW **AIT-V1 TierActionValidator** at PL_005 pre-validation.
- **Untracked target-only** (Q9b) — Examine returns Stage 1 + Stage 2 cached flavor.
- **PromptDetail enum + TierRosterCaps** (Q12a-d): PC/Major FullPersona / Minor Condensed / Untracked Summary; defaults 5 Full + 8 Condensed + 12 Summary.
- **Aggregate overflow format** (Q12e): "...and N other patrons" line.
- **5 RealityManifest extensions** (all OPTIONAL V1).
- **8 V1 rule_ids** in `ai_tier.*` namespace.
- **NEW EVT-T3 cascade-trigger**: `TrackingTierTransition`.

### V1 NOT shipping (deferred per Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| Auto-promotion via significance threshold | V1+30d (AIT-D1) | Q2d V1 Forge-only |
| Demotion Tracked → Untracked | V1+30d (AIT-D2) | Q2e V1 disabled |
| Legendary tier (DF Legends mode) | V2 (AIT-D3) | Q1b V1+ extensibility |
| Faction tier collective | V3 (AIT-D4) | Q1b V3 |
| Dynamic capacity adjustment | V2+ (AIT-D5) | Q2h V1 static caps |
| Causal-ref pin for Untracked persistence | V1+30d (AIT-D6) | Q6c V1 simple discard |
| LLM-propose-promotion | V1+30d (AIT-D7) | Q2d V1 Forge-only |
| On-demand generation beyond cell-entry | V1+30d (AIT-D8) | Q5a V1 cell-entry |
| Multi-day Untracked persistence | V1+30d (AIT-D9) | Q5d V1 daily rotation |
| Stage 2 cache cross-session | V2 (AIT-D10) | Q4e V1 session-only |
| Untracked-to-Untracked interactions | V2 (AIT-D11) | Q9 V1 PC-initiator only |
| Author per-NPC persona-detail bump | V1+30d (AIT-D12) | Q12f V1 tier-default |
| Dynamic roster caps | V2 (AIT-D13) | Q12d V1 static |
| Adaptive PromptDetail | V2 (AIT-D14) | Q12 V1 fixed mapping |
| Summary localization variants | V1+30d (AIT-D15) | Q12 V1 single I18nBundle |
| PC fallback when abandoned | V1+30d (AIT-D16) | Q7c V1 turn-slot system |
| Time-of-day density variance | V1+30d (AIT-D17) | Q8d V1 fixed |
| Minor scripted attacks | V1+30d (AIT-D18) | Q9d V1 non-combatant |
| Untracked as instrument | V1+30d (AIT-D19) | Q9c V1 target-only |
| Forge:EditMinorBehaviorScript runtime | V1+30d (AIT-D20) | Q7b V1 RealityManifest declaration only |
| KilledByCombat discard reason | V1+30d (AIT-D21) | Q9 V1 uses CellLeave proxy |

---

## §2 — i18n Contract Reference

AIT_001 conforms to RES_001 §2 i18n contract:
- **Stable IDs** English `snake_case` / `PascalCase`: `NpcTrackingTier::Major`, `Generated:UntrackedNpcSpawn`, `ai_tier.action_forbidden_for_tier`
- **User-facing strings** I18nBundle: `UntrackedRoleDecl.display_name_template`, `UntrackedRoleDecl.appearance_hints`, `DialogueTemplate.response`, `RejectReason.user_message`

Author-content example (Vietnamese xianxia tavern Untracked roles):
```rust
UntrackedRoleDecl {
    role_id: "wandering_swordsman".into(),
    display_name_template: I18nBundle {
        default: "{name} the Wandering Swordsman".to_string(),
        translations: hashmap! {
            "vi".to_string() => "{name} hành tẩu".to_string(),
            "zh".to_string() => "{name}剑客".to_string(),
        },
    },
    appearance_hints: I18nBundle::en("A cultivator with sword at hip, eyes alert")
        .with_vi("Một tu sĩ ôm kiếm bên hông, ánh mắt cảnh giác")
        .with_zh("腰挂长剑的修士,目光警惕"),
    // ...
}
```

---

## §3 — `NpcTrackingTier` Enum (Q1 LOCKED)

### §3.1 2-variant enum

```rust
pub enum NpcTrackingTier {
    Major,    // V1 active — LLM-driven; full PC-like agency; max ≤20 default
    Minor,    // V1 active — Rule-based scripted; max ≤100 default
    // Untracked = absence of ActorProgression aggregate (PROG_001 §3.1 storage model semantic)
    // V1+ reserved: Legendary (V2 DF Legends mode); Faction (V3 collective tier)
}
```

### §3.2 Tier semantic table

| Tier | actor_progression aggregate | tracking_tier value | Decision authority | LLM presence | Capacity cap default |
|---|---|---|---|---|---|
| **PC** | YES (eager Generator) | `None` | Player (or fallback LLM V1+) | Only on fallback | n/a (unlimited PC count per player) |
| **Major** | YES (lazy materialization) | `Some(Major)` | LLM (NPC_002 Chorus) | Full per turn | 20 per reality |
| **Minor** | YES (lazy materialization) | `Some(Minor)` | Rule-based scripted dispatcher | Narrates outcomes only | 100 per reality |
| **Untracked** | NO aggregate | n/a | None (narrative-only) | Scene narration + Stage 2 first-interaction | Unlimited (per-cell density Q8) |

### §3.3 Why "Untracked = no aggregate" semantic

Per Q1c LOCKED — type-system enforced via PROG_001 §3.1 storage model. Avoids "phantom Untracked with aggregate" bug. Pattern: any actor without `actor_progression` row is either (a) PC pre-creation, (b) Untracked NPC, or (c) cleaned-up archived actor. Engine differentiates via NpcId namespace + entity lifecycle state (EF_001).

---

## §4 — Tier Assignment Rules (Q2 LOCKED)

### §4.1 Canonical NPC tier (Q2a)

NPC_001 closure pass adds REQUIRED field to CanonicalActorDecl:

```rust
// NPC_001 §canonical_actor extension (Q2a):
pub struct CanonicalActorDecl {
    // ... existing NPC_001 fields ...
    pub tracking_tier: NpcTrackingTier,    // V1 REQUIRED — author must explicitly choose Major or Minor
}
```

NO default behavior. Forces authors to think tier-by-NPC. Prevents accidental Major-tier overuse (LLM cost explosion).

Validator at RealityManifest bootstrap rejects canonical_actor_decl without tracking_tier with `ai_tier.canonical_tier_required`.

### §4.2 Untracked NPC source (Q2b)

Untracked NPCs are **NEVER in canonical_actor_decl**. Purely ephemeral; on-demand cell-entry generation per §5 Untracked generation pipeline.

### §4.3 Forge promotion path V1 (Q2c)

```rust
pub enum ForgeEditAction {
    // ... existing variants ...
    
    /// Q2c LOCKED — Forge admin promotion V1.
    /// Effect: ephemeral NpcId becomes persistent (Q11a stable);
    /// Stage 1 stats + Stage 2 LLM-flavor cache crystallize into NPC_001 npc core aggregate;
    /// ActorProgression aggregate created with current Stage 1 stats as initial_value;
    /// emit TrackingTierTransition cascade-trigger.
    PromoteUntrackedToTracked {
        ephemeral_npc_id: NpcId,                 // session-ephemeral; deterministic blake3
        cell_id: ChannelId,                      // observation cell at promotion moment
        new_tier: NpcTrackingTier,               // Major or Minor (validates against TierCapacityCaps)
    },
}
```

### §4.4 Auto-promotion V1 (Q2d) — DEFERRED

V1: NO auto-promotion. V1+30d (AIT-D1) significance threshold heuristic (PC interactions count / named-mention count / token exchange volume).

V1+30d (AIT-D7): LLM-propose-promotion with author-confirm UI.

### §4.5 Demotion V1 (Q2e) — DISABLED

Tracked is permanent V1. V1+30d (AIT-D2) `Forge:DemoteTrackedToUntracked` for narrative use cases (deceased NPC simplified to memorial; sect dissolved members).

### §4.6 Untracked NpcId scoping (Q2f)

```rust
fn untracked_npc_id_for(
    reality_id: RealityId,
    cell_id: ChannelId,
    fiction_day: u64,
    slot_index: u8,
) -> NpcId {
    NpcId(blake3_hash(reality_id, cell_id, fiction_day, slot_index))
}
```

Determinism per EVT-A9: replay regenerates same NpcId for same `(reality, cell, day, slot)`. Untracked NPCs have stable identity within session.

### §4.7 Untracked NpcId reclaim (Q2g)

V1: discard at cell-leave + session-end (per Q6 §6 details). V1+30d (AIT-D6) causal-ref pin override.

### §4.8 TierCapacityCaps (Q2h)

```rust
pub struct RealityManifest {
    // ... existing ...
    
    pub tier_capacity_caps: Option<TierCapacityCaps>,    // None = engine defaults
}

pub struct TierCapacityCaps {
    pub max_major_tracked: u32,    // V1 default 20
    pub max_minor_tracked: u32,    // V1 default 100
    // Untracked unlimited per reality (per-cell density Q8 caps individual cells)
}
```

Validator at RealityManifest bootstrap rejects if canonical_actor_decl Tracked NPCs exceed caps with `ai_tier.capacity_exceeded`. Forge promotion respects caps (rejects if would exceed).

---

## §5 — Untracked NPC Generation Pipeline (Q4+Q5+Q11 LOCKED)

### §5.1 Hybrid 2-stage architecture (Q4a)

**Stage 1 — Template + RNG (deterministic, cheap, at cell-entry)**:
- Triggered by PC entity_binding location change INTO cell
- Generates NpcId + actor_class + name (from name_pool) + stat sample (from stat_ranges) + appearance_hints reference
- All deterministic per Q2f blake3 seed
- Cached in session ephemeral store (no aggregate)
- Cost: minimal (no LLM call)

**Stage 2 — LLM-flavor (lazy, on first PL_005 interaction)**:
- Triggered when PC initiates first PL_005 InteractionKind targeting Untracked
- LLM generates dialogue style + backstory hints + flavor description using Stage 1 output as scaffolding
- Cached per session (cleared at cell-leave / session-end with NPC)
- Cost: 1 LLM call per Untracked per session (capped — most Untracked never reach Stage 2 since PC doesn't interact)

### §5.2 UntrackedTemplateDecl (Q4b)

```rust
pub struct UntrackedTemplateDecl {
    pub place_type: PlaceTypeRef,                    // applies to all cells of this PlaceType
    pub roles: Vec<UntrackedRoleDecl>,
}

pub struct UntrackedRoleDecl {
    pub role_id: String,                             // diagnostic stable e.g., "tavern_patron" / "wandering_swordsman"
    pub display_name_template: I18nBundle,           // {name} substituted from name_pool
    pub actor_class: ActorClassRef,                  // links to NPC_001 actor_class taxonomy
    pub name_pool: Vec<String>,                      // RNG picks from this (deterministic per slot_index)
    pub stat_ranges: Vec<StatRangeDecl>,             // PROG_001 ProgressionInstance min/max per kind_id
    pub appearance_hints: I18nBundle,                // narrative hints for Stage 2 LLM
    pub default_dialogue_register: DialogueRegister, // Formal/Casual/Rough/Refined
}

pub struct StatRangeDecl {
    pub kind_id: ProgressionKindId,                  // matches RealityManifest progression_kinds
    pub min: u64,
    pub max: u64,
}

pub enum DialogueRegister {
    Formal,
    Casual,
    Rough,
    Refined,
}
```

### §5.3 Generation timing (Q5a-d)

```pseudo
on PC_enters_cell(pc, cell, current_fiction_ts):
  let current_fiction_day = floor(current_fiction_ts / fiction_day);
  
  // Q8 read density per cell type
  let density = reality.cell_untracked_density.get(cell.place_type)
    .unwrap_or(engine_default_density(cell.place_type));
  
  // Q4 read template
  let template = reality.untracked_templates
    .find(t => t.place_type == cell.place_type);
  if template is None: return;  // no Untracked for this PlaceType
  
  // Q5b batch generation
  for slot_index in 0..density.count:
    let role = template.roles[slot_index % template.roles.len()];
    
    // Q2f Q4c deterministic
    let npc_id = NpcId(blake3_hash(reality_id, cell.id, current_fiction_day, slot_index));
    
    // Deterministic name
    let name_index = blake3_index(reality_id, cell.id, current_fiction_day, slot_index, "name") % role.name_pool.len();
    let name = role.name_pool[name_index];
    
    // Deterministic stat sampling
    let stats: HashMap<ProgressionKindId, u64> = role.stat_ranges.iter()
      .map(|range| {
        let value = range.min + 
          blake3_in_range(reality_id, cell.id, current_fiction_day, slot_index, range.kind_id) 
          % (range.max - range.min + 1);
        (range.kind_id.clone(), value)
      })
      .collect();
    
    // Cache Stage 1 in session ephemeral store
    session.untracked_cache.insert(npc_id, UntrackedRuntimeState {
      role: role.role_id.clone(),
      cell_id: cell.id,
      slot_index,
      display_name: role.display_name_template.with_substitution("name", &name),
      actor_class: role.actor_class.clone(),
      stats,
      appearance_hints: role.appearance_hints.clone(),
      default_dialogue_register: role.default_dialogue_register,
      llm_flavor_cache: None,                        // Stage 2 not yet triggered
    });
    
    // Q5e emit spawn event
    emit Generated:UntrackedNpcSpawn {
      reality_id, cell_id: cell.id, fiction_day: current_fiction_day,
      slot_index, npc_id, role_id: role.role_id.clone(),
    };
```

### §5.4 Re-entry behavior (Q5c-d)

- **Same fiction-day re-entry**: same blake3 seed → identical NpcIds + stats + names. Cache may already have entries; re-entry is no-op for spawn (don't re-emit if cache valid).
- **New fiction-day re-entry**: different seed → DIFFERENT Untracked. Natural crowd rotation. Old day's Untracked already discarded at cell-leave.

### §5.5 Stage 2 LLM-flavor synthesis (Q4d-e + Q5f)

```pseudo
on PL_005_interaction_targets_untracked(pc, npc_id, kind):
  let runtime = session.untracked_cache.get(npc_id)?;
  
  if runtime.llm_flavor_cache is None:
    // Q4d Stage 2 LLM trigger (one-time per Untracked per session)
    let flavor = synthesize_stage2_llm_flavor(LlmPromptCtx {
      role: runtime.role,
      display_name: runtime.display_name.render(active_locale),
      actor_class: runtime.actor_class,
      stats_summary: stats_summary(runtime.stats),
      appearance_hints: runtime.appearance_hints,
      dialogue_register: runtime.default_dialogue_register,
      cell_context: cell_metadata(runtime.cell_id),
      pc_action: kind,
    });
    runtime.llm_flavor_cache = Some(flavor);
    session.untracked_cache.update(npc_id, runtime);
  
  // Continue with normal PL_005 cascade
  // Q9 tier check via AIT-V1 validator runs first (rejects if Untracked initiator)
  // For PC initiator → proceed; LLM uses runtime.llm_flavor_cache for narration
```

### §5.6 Q11 Promotion preserves NpcId

```pseudo
on Forge:PromoteUntrackedToTracked(ephemeral_npc_id, cell_id, new_tier):
  let runtime = session.untracked_cache.get(ephemeral_npc_id)?;
  
  // Q2h validate cap
  if new_tier == Major:
    if count_major_tracked() >= reality.tier_capacity_caps.max_major_tracked:
      return reject("ai_tier.capacity_exceeded", { tier: Major });
  if new_tier == Minor:
    if count_minor_tracked() >= reality.tier_capacity_caps.max_minor_tracked:
      return reject("ai_tier.capacity_exceeded", { tier: Minor });
  
  // Q11b — synthesize Stage 2 if not cached
  if runtime.llm_flavor_cache is None:
    runtime.llm_flavor_cache = Some(synthesize_stage2_llm_flavor(/* ... */));
  
  // Q11a — NpcId STABLE (ephemeral becomes persistent)
  let npc_core = NpcCore {
    npc_id: ephemeral_npc_id.clone(),                // STABLE
    canonical_traits: from_runtime(runtime),
    // ... other NPC_001 fields ...
    tracking_tier: new_tier,
  };
  storage.npc_core.insert(npc_core);
  
  // Q11e — atomic at turn-boundary; ActorProgression with Stage 1 stats as initial_value
  let actor_progression = ActorProgression {
    reality_id, actor_ref: ActorRef::Npc(ephemeral_npc_id.clone()),
    values: runtime.stats.iter().map(|(kind, value)| ProgressionInstance {
      kind_id: kind.clone(), raw_value: *value, current_tier: None,
      last_trained_at_fiction_ts: current_ts,
      last_observed_at_fiction_ts: current_ts,
      training_log_window: VecDeque::new(),
    }).collect(),
    last_modified_at_turn: current_turn,
    schema_version: 1,
    tracking_tier: Some(new_tier),
  };
  storage.actor_progression.insert(actor_progression);
  
  // Remove from session ephemeral cache (Q11 transitions out of ephemeral state)
  session.untracked_cache.remove(ephemeral_npc_id);
  
  // Emit promotion-side discard event (Q6e PromotedToTracked reason)
  emit Generated:UntrackedNpcDiscarded {
    reality_id, cell_id: runtime.cell_id, fiction_day: <derived>,
    slot_index: runtime.slot_index, npc_id: ephemeral_npc_id.clone(),
    reason: UntrackedDiscardReason::PromotedToTracked,
  };
  
  // Emit tier transition event (NEW EVT-T3 cascade-trigger)
  emit TrackingTierTransition {
    actor_ref: ActorRef::Npc(ephemeral_npc_id),
    from_tier: None,                                  // None = was Untracked
    to_tier: Some(new_tier),
    triggered_at_fiction_ts: current_ts,
  };
  
  // forge_audit_log records edit (WA_003 existing path)
```

---

## §6 — Discard Policy V1 (Q6 LOCKED)

### §6.1 Discard reasons enum

```rust
pub enum UntrackedDiscardReason {
    CellLeave,                                       // V1 — Q6a EF_001 entity_binding location change away
    SessionEnd,                                      // V1 — Q6b PL_001 session lifecycle ended
    PromotedToTracked,                               // V1 — Q11 crystallization (ephemeral → persistent)
    StaleTimeout,                                    // V1+30d AIT-D8 — time-based stale
    CausalRefExpired,                                // V1+30d AIT-D6 — pin lost
    KilledByCombat,                                  // V1+30d AIT-D21 — proper death event
}
```

### §6.2 Cell-leave discard (Q6a)

```pseudo
on PC_entity_binding_location_change(pc, from_cell, to_cell):
  if from_cell != to_cell:
    let untracked_in_old_cell = session.untracked_cache
      .npcs_in_cell(from_cell);
    
    for npc_id in untracked_in_old_cell:
      let runtime = session.untracked_cache.get(npc_id)?;
      session.untracked_cache.remove(npc_id);
      
      emit Generated:UntrackedNpcDiscarded {
        reality_id, cell_id: from_cell,
        fiction_day: <current>, slot_index: runtime.slot_index, npc_id,
        reason: CellLeave,
      };
```

### §6.3 Session-end discard (Q6b)

PL_001 session lifecycle triggers:
- PC disconnect (network drop / app close)
- Sleep major (8h+ fiction-time fast-forward command)
- Explicit `/end` MetaCommand
- 24h idle timeout (no PC turn-events for 24h real-time)

```pseudo
on session_end(pc, end_reason):
  for npc_id in session.untracked_cache.all_npcs():
    let runtime = session.untracked_cache.get(npc_id)?;
    session.untracked_cache.remove(npc_id);
    
    emit Generated:UntrackedNpcDiscarded {
      reality_id, cell_id: runtime.cell_id,
      fiction_day: <last>, slot_index: runtime.slot_index, npc_id,
      reason: SessionEnd,
    };
```

### §6.4 V1 simplifications (Q6c-d)

- **NO causal-ref pin V1** — discard regardless of references; V1+30d AIT-D6 adds pin tracking
- **NO time-based discard V1** — daily rotation Q5d covers ephemeral feel; V1+30d AIT-D8 adds stale detection

### §6.5 Discard event (Q6e)

NEW EVT-T5 sub-type `Generated:UntrackedNpcDiscarded` mirrors `Generated:UntrackedNpcSpawn` for audit symmetry. Replay reproduces both events deterministically.

---

## §7 — Behavior Model per Tier (Q7 LOCKED)

### §7.1 Capability matrix

| Capability | PC | Major | Minor | Untracked |
|---|---|---|---|---|
| **Decision authority** | Player (or fallback LLM) | LLM (NPC_002 Chorus) | Rule-based scripted | None (narrative-only) |
| **LLM presence** | Only on fallback | Full per turn | Outcome narration only | Scene mention + Stage 2 first-interaction |
| **Action initiation** | Full PL_005 | Full PL_005 | Subset (Speak canned + Use training + passive Examine) | NONE |
| **Action target** | Full | Full | Full (Reaction triggered) | Full (Examine returns Stage 1+2 cache) |
| **Training** | Full Q3 sources | Full Q3 sources | Time-source via ScheduledActionDecl only | NONE |
| **NPC_002 Chorus participation** | n/a (PC) | Full priority | Lowest priority | EXCLUDED |
| **AssemblePrompt detail** | FullPersona | FullPersona | CondensedPersona | SummaryLine |

### §7.2 MinorBehaviorScript pattern (Q7b)

Author declares per actor_class — all Minor NPCs of that class share behavior script:

```rust
pub struct MinorBehaviorScript {
    pub actor_class: ActorClassRef,
    pub canned_dialogue_templates: Vec<DialogueTemplate>,
    pub scheduled_actions: Vec<ScheduledActionDecl>,
    pub reaction_table: Vec<ReactionDecl>,
}

pub struct DialogueTemplate {
    pub trigger_pattern: TriggerPattern,             // matches PC PL_005 action
    pub response: I18nBundle,                        // canned response (no LLM dialogue gen)
}

pub enum TriggerPattern {
    PcSpeaksToActor { keywords: Vec<String> },       // PC says hello → match
    PcEntersCell,                                    // PC entry → greeting
    PcStrikesActor,                                  // PC attacks → reaction
    PcGivesItem { item_kinds: Vec<ResourceKind> },   // PC gives item → thanks
}

pub struct ScheduledActionDecl {
    pub fiction_time_window: FictionTimeWindow,      // e.g., "every fiction-day 06:00-08:00"
    pub action: ScriptedAction,
}

pub enum ScriptedAction {
    StartTraining { kind_id: ProgressionKindId, duration_hours: u8 },  // Q3 Time-source training
    OpenShop,                                        // V1+30d (AIT-D18 expansion)
    Sleep,                                           // V1+30d
    Patrol { cells: Vec<ChannelId> },                // V1+30d (Minor scripted movement)
}

pub struct ReactionDecl {
    pub trigger_event: EventPattern,
    pub reaction: ScriptedReaction,
}

pub enum EventPattern {
    StruckByPC,
    GivenItemByPC { kind: ResourceKind },
    PcDeparts,
}

pub enum ScriptedReaction {
    SpeakCanned { template_id: String },             // pulls from canned_dialogue_templates
    Flee,                                            // V1+30d AIT-D18 active V1+
    Stand,                                           // V1+30d
}
```

V1: ONLY `StartTraining` ScheduledAction + `SpeakCanned` ScriptedReaction active. Other variants reserved V1+30d.

### §7.3 NPC_002 Chorus tier filter (Q7e)

Chorus closure pass folds in tier check:

```pseudo
fn npc_chorus_priority(npc_ref: ActorRef) -> Option<Priority>:
  let actor_progression = storage.actor_progression.get(npc_ref);
  match actor_progression.tracking_tier:
    None => Priority::Pc,                            // PC always highest
    Some(Major) => calculate_full_chorus_priority(npc_ref),  // 4-tier priority per NPC_002 §6
    Some(Minor) => Priority::MinorBaseline,          // V1: fixed low priority
    // Untracked has no actor_progression, so this code path not reached
```

Untracked NPCs are NEVER in Chorus (no actor_progression aggregate; semantic exclusion).

---

## §8 — Per-Cell-Type Untracked Density (Q8 LOCKED)

### §8.1 DensityDecl V1 shape

```rust
pub struct DensityDecl {
    pub count: u8,                                   // V1 fixed; max 12 (Q8c cap)
    // V1+30d (AIT-D17): time_of_day_modifiers: Option<Vec<TimeOfDayModifier>>
}
```

### §8.2 Engine defaults per PlaceType (Q8b)

| PlaceType | Default density | Rationale |
|---|---|---|
| `tavern` | 4 | medium crowd; patrons + server |
| `residence` | 2 | family or solo dwelling |
| `marketplace` | 8 | crowded by definition |
| `temple` | 2 | small group of worshippers / monks |
| `workshop` | 1 | usually 1 NPC working |
| `cave` | 0 | empty by default; author may override |
| `road` | 0 | generally empty between settlements |
| `wilderness` | 0 | empty by default |
| `official_hall` | 3 | clerks + visitors |
| `crossroads` | 2 | small crowd; travelers |

If author doesn't declare PlaceType in `cell_untracked_density`, engine uses these defaults.

### §8.3 RealityManifest extension

```rust
pub struct RealityManifest {
    // ... existing ...
    
    pub cell_untracked_density: HashMap<PlaceTypeRef, DensityDecl>,    // Q8 — author override per PlaceType
}
```

### §8.4 V1 cap enforcement (Q8c)

Validator at RealityManifest bootstrap rejects DensityDecl with `count > 12` with `ai_tier.density_exceeded`. Aligns with Q12d Untracked summary cap (12 per scene).

---

## §9 — Action Availability per Tier (Q9 LOCKED)

### §9.1 Action × Tier matrix (Q9a)

| Tier | Speak | Strike | Give | Examine | Use |
|---|---|---|---|---|---|
| **PC** | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ✅ Full |
| **Major** | ✅ Full (LLM-driven) | ✅ Full | ✅ Full | ✅ Full | ✅ Full |
| **Minor** | ✅ Canned (DialogueTemplate) | ❌ V1 | ❌ V1 | ✅ Passive (target only) | ✅ Training only V1 (StartTraining ScheduledAction) |
| **Untracked** | ❌ (mentioned only) | ❌ | ❌ | ✅ Passive only (target; returns Stage 1 + Stage 2 flavor) | ❌ |

### §9.2 Untracked target behavior (Q9b)

When Tracked actor (PC or Major NPC) executes PL_005 with Untracked as target:
- **Speak target**: Triggers Stage 2 LLM-flavor synthesis if not cached. LLM narrates Untracked's response.
- **Strike target**: Standard PROG_001 Q7 hybrid combat. Untracked's stats from Stage 1 sample. HP=0 → discard with `KilledByCombat` reason (V1+30d AIT-D21 proper); V1 uses `CellLeave` proxy.
- **Give target**: Silent accept (no narrative effect on Untracked V1; LLM may narrate "the patron accepts the coin").
- **Examine target**: Returns Stage 1 + Stage 2 cached flavor. First-time Examine triggers Stage 2 synthesis.
- **Use target**: Untracked as target of Use kind is unusual; V1 silently accept (no progression for Untracked).

### §9.3 AIT-V1 TierActionValidator (Q9e)

NEW validator at PL_005 cascade pre-validation. Slot ordering: AFTER PL_005 Stage 0 schema + capability check; BEFORE PROG_001 Q3 training cascade.

```pseudo
fn ait_v1_tier_action_validator(turn_event: TurnEvent) -> Option<RejectReason>:
  let actor_tier = resolve_tier(turn_event.actor);  // PC / Major / Minor / Untracked
  let interaction_kind = turn_event.interaction_kind;
  
  match (actor_tier, interaction_kind):
    (PC | Major, _) => None,                        // full range allowed
    
    (Minor, Speak { match: Canned }) => None,        // canned dialogue OK
    (Minor, Use { sub_intent: Training }) => None,   // scripted training OK
    (Minor, Examine { target_only: true }) => None,  // passive only
    (Minor, Speak { match: NonCanned }) | 
    (Minor, Strike { .. }) | 
    (Minor, Give { .. }) | 
    (Minor, Use { sub_intent: NonTraining }) => 
        Some(reject("ai_tier.action_forbidden_for_tier", { actor_tier: Minor, kind: ... })),
    
    (Untracked, _) => 
        Some(reject("ai_tier.untracked_cannot_initiate", { ephemeral_npc_id: turn_event.actor })),
  
  // Untracked as TARGET allowed (separate code path; not blocked by validator)
```

### §9.4 PL_005 closure pass impact

PL_005 closure pass adds tier check BEFORE PROG_001 Q3 cascade. Order:
1. PL_005 schema validation
2. PL_005 capability check (DP-K9)
3. **AIT-V1 TierActionValidator** (NEW)
4. PL_005 OutputDecl validators
5. PROG_001 Q3 training cascade post-validation (only if AIT-V1 passes)

---

## §10 — LLM Context Budget per Tier (Q12 LOCKED)

### §10.1 PromptDetail enum

```rust
pub enum PromptDetail {
    FullPersona,                                     // ~300-500 tokens — canonical_traits + flexible_state + opinions + desires + progression
    CondensedPersona,                                // ~80-150 tokens — display_name + actor_class + 1-2 opinions/desires + tier-relevant progression
    SummaryLine,                                     // ~20-40 tokens — display_name + actor_class + appearance_hints (1 sentence)
    Hidden,                                          // 0 tokens — not in roster
}
```

### §10.2 V1 default mapping (Q12a)

| Tier | PromptDetail V1 default |
|---|---|
| PC | `FullPersona` |
| Major | `FullPersona` |
| Minor | `CondensedPersona` |
| Untracked | `SummaryLine` |

### §10.3 TierRosterCaps (Q12d)

```rust
pub struct TierRosterCaps {
    pub max_full_persona: u8,                        // V1 default 5 (PC + Major shared)
    pub max_condensed: u8,                           // V1 default 8 (Minor)
    pub max_summary: u8,                             // V1 default 12 (Untracked)
    pub overflow_format: OverflowFormat,
}

pub enum OverflowFormat {
    Truncate,
    Aggregate,                                       // V1 default — "...and N other patrons"
}

pub struct RealityManifest {
    // ... existing ...
    
    pub tier_roster_caps: Option<TierRosterCaps>,    // None = engine defaults
}
```

### §10.4 AssemblePrompt composition (Q12c)

```pseudo
fn assemble_actor_context_section(scene_actors: Vec<ActorRef>, budget_caps: TierRosterCaps) -> String {
  // Tier-priority sort
  let pcs: Vec<_> = scene_actors.iter().filter(|a| a.is_pc()).collect();
  let majors: Vec<_> = scene_actors.iter().filter(|a| a.has_tier(Major)).sorted_by_chorus_priority();
  let minors: Vec<_> = scene_actors.iter().filter(|a| a.has_tier(Minor)).sorted_by_chorus_priority();
  let untrackeds: Vec<_> = scene_actors.iter().filter(|a| a.is_untracked()).collect();
  
  let mut roster: Vec<(ActorRef, PromptDetail)> = vec![];
  let mut full_used = 0;
  let mut condensed_used = 0;
  let mut summary_used = 0;
  
  // PC always FullPersona
  for pc in pcs {
    if full_used < budget_caps.max_full_persona:
      roster.push((pc, PromptDetail::FullPersona));
      full_used += 1;
  }
  
  // Majors: FullPersona until cap; overflow → Condensed
  for major in majors {
    if full_used < budget_caps.max_full_persona:
      roster.push((major, PromptDetail::FullPersona));
      full_used += 1;
    else:
      if condensed_used < budget_caps.max_condensed:
        roster.push((major, PromptDetail::CondensedPersona));
        condensed_used += 1;
  }
  
  // Minors: Condensed until cap; overflow → Summary
  for minor in minors {
    if condensed_used < budget_caps.max_condensed:
      roster.push((minor, PromptDetail::CondensedPersona));
      condensed_used += 1;
    else:
      if summary_used < budget_caps.max_summary:
        roster.push((minor, PromptDetail::SummaryLine));
        summary_used += 1;
  }
  
  // Untracked: Summary until cap
  let untracked_overflow_count = 0;
  for untracked in untrackeds {
    if summary_used < budget_caps.max_summary:
      roster.push((untracked, PromptDetail::SummaryLine));
      summary_used += 1;
    else:
      untracked_overflow_count += 1;
  }
  
  // Render roster
  let mut output = String::new();
  for (actor, detail) in roster:
    output.push_str(&render_actor(actor, detail));
  
  // Aggregate overflow line (Q12e)
  if untracked_overflow_count > 0 && budget_caps.overflow_format == OverflowFormat::Aggregate:
    output.push_str(&format!("\n... and {} other patrons go about their business.", untracked_overflow_count));
  
  output
}
```

### §10.5 Per-tier render

```pseudo
fn render_actor(actor: ActorRef, detail: PromptDetail) -> String:
  match (actor.tier, detail):
    (Untracked, SummaryLine) => {
      let runtime = session.untracked_cache.get(actor.npc_id)?;
      format!("- {}: {} ({})", 
        runtime.display_name.render(active_locale),
        runtime.actor_class,
        runtime.appearance_hints.render(active_locale))
    },
    (Minor, CondensedPersona) => {
      let core = storage.npc_core.get(actor.npc_id)?;
      let progression = storage.actor_progression.get(actor.actor_ref)?;
      format!("- {}: {} ({}). {}", 
        core.display_name.render(active_locale),
        core.actor_class,
        format_progression_summary(progression, /* tier-relevant only */),
        format_top_desires(core.desires, 1))
    },
    (Major | Pc, FullPersona) => {
      // Full persona render per NPC_001 / PCS_001 patterns
      format_full_persona(actor)
    },
    _ => unreachable!(),
```

---

## §11 — RealityManifest Extensions

### §11.1 Fields added by AIT_001

Registered in `_boundaries/02_extension_contracts.md` §2:

```rust
pub struct RealityManifest {
    // ... existing fields per Continuum / NPC_001 / WA / PF / MAP / CSC / RES / NPC_003 / IDF / FF / FAC / PROG ...
    
    // ─── AIT_001 extensions (added 2026-04-27 DRAFT) ───
    
    /// Tier capacity caps per reality (Q2h). None = engine defaults Major≤20 / Minor≤100.
    pub tier_capacity_caps: Option<TierCapacityCaps>,
    
    /// Untracked NPC templates per PlaceType (Q4b). Empty = no Untracked generation in those PlaceTypes.
    pub untracked_templates: Vec<UntrackedTemplateDecl>,
    
    /// Per-PlaceType Untracked density (Q8). HashMap value caps at 12 per Q8c. Empty = engine defaults.
    pub cell_untracked_density: HashMap<PlaceTypeRef, DensityDecl>,
    
    /// Tier-aware AssemblePrompt budget caps (Q12d). None = engine defaults 5 Full / 8 Condensed / 12 Summary.
    pub tier_roster_caps: Option<TierRosterCaps>,
    
    /// Minor NPC behavior scripts per actor_class (Q7b). Empty = Minors silently fall back to no canned response.
    pub minor_behavior_scripts: Vec<MinorBehaviorScript>,
}
```

### §11.2 Default values (engine fallback)

If author provides empty arrays / None:
- `tier_capacity_caps: None` → engine defaults Major≤20 / Minor≤100
- `untracked_templates: []` → NO Untracked generation any PlaceType (cells appear empty of background NPCs unless author declares templates)
- `cell_untracked_density: {}` → engine defaults per §8.2 (tavern=4 / etc.)
- `tier_roster_caps: None` → engine defaults 5 Full / 8 Condensed / 12 Summary / Aggregate overflow
- `minor_behavior_scripts: []` → Minors silently fall back to no canned response (Speak target receives empty I18nBundle response — LLM narrator may improvise)

### §11.3 Per-reality opt-in

Authors can omit AIT fields entirely (sandbox/freeplay realities); AIT V1 is opt-in per reality. Per `_boundaries/02_extension_contracts.md` §2 rule 4 — composability.

---

## §12 — Generator Bindings

### §12.1 V1 Generators

AIT_001 owns 2 V1 EVT-T5 sub-types:

| Sub-type | Trigger | Description |
|---|---|---|
| `Generated:UntrackedNpcSpawn` | EVT-G2 cell-entry observation event | Stage 1 deterministic generation per slot at PC entry to cell |
| `Generated:UntrackedNpcDiscarded` | Cell-leave / session-end / promotion | Untracked NPC removed from session cache; reason enum captures cause |

### §12.2 Coordinator sequencing

UntrackedNpcSpawn runs at observation event time (NOT day-boundary). Different trigger source from RES_001 / PROG_001 day-boundary Generators. No sequencing conflict.

UntrackedNpcDiscarded runs at trigger event time (cell-leave / session-end / promotion). Independent.

### §12.3 Determinism per EVT-A9

UntrackedNpcSpawn deterministic per `blake3(reality_id || cell_id || fiction_day || slot_index)` (Q2f / Q4c). Replay regenerates same NpcIds + stats.

UntrackedNpcDiscarded deterministic per discard trigger event causality.

### §12.4 NEW EVT-T3 cascade-trigger

```rust
pub struct TrackingTierTransition {
    pub actor_ref: ActorRef,
    pub from_tier: Option<NpcTrackingTier>,           // None = was Untracked
    pub to_tier: Option<NpcTrackingTier>,             // None = becoming Untracked (V1+30d demotion)
    pub triggered_at_fiction_ts: i64,
}
```

V1 emitted on Forge promotion only (Untracked → Tracked). V1+30d emitted on demotion (AIT-D2).

Cascade-trigger pattern (mirrors PF_001 PlaceDestroyed): downstream consumers subscribe explicitly.

V1 consumers: NPC_001 npc core writes; NPC_002 Chorus priority recalc; AssemblePrompt cache invalidation.

---

## §13 — Validator Chain

### §13.1 AIT_001 validator slots

| Slot | Validator | Owner | Order |
|---|---|---|---|
| ... | (existing PL_001 / PL_005 / PL_006 / WA_006 / EF_001 / PF_001 / RES_001 / PROG_001 validators) | | |
| `AIT-V1` | `TierActionValidator` | AIT_001 | After PL_005 capability check, BEFORE PROG_001 Q3 training cascade |
| `AIT-V2` | `TierCapacityValidator` | AIT_001 | At RealityManifest bootstrap + Forge:PromoteUntrackedToTracked |
| `AIT-V3` | `DensityValidator` | AIT_001 | At RealityManifest bootstrap (validate DensityDecl.count ≤ 12) |
| `AIT-V4` | `UntrackedTemplateValidator` | AIT_001 | At RealityManifest bootstrap (validate UntrackedTemplateDecl coherence) |

### §13.2 Validator behaviors

**AIT-V1 TierActionValidator** (Q9e): per §9.3 pseudocode. Rejects Minor non-allowed kinds + Untracked initiator.

**AIT-V2 TierCapacityValidator** (Q2h): At bootstrap counts canonical_actor_decl Tracked NPCs per tier; rejects if exceeds tier_capacity_caps. At Forge promotion checks cap before commit; rejects with `ai_tier.capacity_exceeded`.

**AIT-V3 DensityValidator** (Q8c): For each `cell_untracked_density` entry, asserts `count ≤ 12`. Rejects with `ai_tier.density_exceeded`.

**AIT-V4 UntrackedTemplateValidator**: For each UntrackedTemplateDecl:
- `place_type` exists in PF_001 PlaceType registry
- Each `role.name_pool` non-empty
- Each `role.stat_ranges.kind_id` exists in reality.progression_kinds
- Each `role.actor_class` exists in NPC_001 actor_class registry
- Reject with `ai_tier.template_invalid` if any check fails

---

## §14 — Cascade Integration with Other Features

### §14.1 PROG_001 Progression Foundation

`tracking_tier: Option<NpcTrackingTier>` field activated at AIT_001 DRAFT (was reserved `None` V1 default in PROG_001 §3.1). PROG_001 reads tier for:
- Eager (PC: None) vs Lazy (NPC: Some) Generator iteration in `Scheduled:CultivationTick` (Q4 REVISED)
- Materialization computation triggers on observation events

AIT_001 emits `Generated:UntrackedNpcSpawn` events; PROG_001 silently skips Untracked (no aggregate to mutate).

### §14.2 NPC_001 Cast

NPC_001 closure pass adds:
- REQUIRED `tracking_tier: NpcTrackingTier` field on CanonicalActorDecl (Q2a)
- §6 persona assembly reads tier-aware PromptDetail (PC/Major FullPersona / Minor Condensed / Untracked Summary per Q12a)
- NpcId namespace allows ephemeral blake3-derived IDs alongside canonical author-declared IDs (Q2f / Q11a)

### §14.3 NPC_002 Chorus

NPC_002 closure pass adds tier filter (Q7e) to priority calculation:
- Major: full priority
- Minor: lowest priority (Priority::MinorBaseline V1 fixed)
- Untracked: EXCLUDED from chorus_batch_state participants

### §14.4 NPC_003 Desires

Independent — desires are narrative, not tier-related. Major NPCs have desires (per NPC_003 §2). Minor NPCs may have desires (canned). Untracked do NOT have desires (no aggregate).

### §14.5 PL_005 Interaction

PL_005 closure pass adds:
- AIT-V1 TierActionValidator slot reference at pre-validation (Q9e-f)
- Untracked target handling (§9.2): Examine triggers Stage 2 synthesis; Strike applies Q7 PROG_001 combat formula with Stage 1 stats
- Stage 2 LLM-flavor synthesis hook on first interaction

### §14.6 PL_001 Continuum

PL_001 §session lifecycle hooks:
- PC entity_binding location change → AIT cell-leave discard (§6.2)
- Session end (disconnect / sleep major / /end / 24h idle) → AIT session-end discard (§6.3)

scene_state membership reflects tier (Untracked as ephemeral participants).

### §14.7 PL_006 Status Effects

Independent — status flags apply per-actor regardless of tier. Untracked NPC can receive Wounded magnitude on Strike (V1 simplification: status events for Untracked are emitted but discarded along with NPC at cell-leave; no persistence).

### §14.8 RES_001 Resource Foundation

**Alignment concern (PROG-D19 V1+30d)**: RES_001 NPC owner auto-collect Generator (`Scheduled:NPCAutoCollect` daily for ALL NPCs) is architecturally inconsistent with quantum-observation principle. V1 keeps RES_001 eager (already CANDIDATE-LOCK); V1+30d closure pass migrates to lazy materialization respecting tier (Major lazy / Minor lazy / Untracked excluded).

V1 simplification: RES_001 NPC eager auto-collect runs for Tracked NPCs only (filter by `tracking_tier.is_some()`). Untracked don't have resource_inventory so silently skipped already.

### §14.9 EF_001 Entity Foundation

PC entity_binding location change cascades AIT cell-leave discard (§6.2). EF_001 cascade rules apply:
- Actor destroyed (death finalized via WA_006) → if Tracked NPC: actor_progression aggregate becomes orphan; if Untracked NPC: cache entry already discarded (cell-leave)

### §14.10 PF_001 Place Foundation

`cell_untracked_density: HashMap<PlaceTypeRef, DensityDecl>` references PF_001 PlaceType registry (10 V1 variants). UntrackedTemplateDecl.place_type same.

### §14.11 CSC_001 Cell Scene Composition

CSC_001 Layer 3 LLM zone-assignment receives Untracked NPCs as occupants alongside Tracked. Stage 1 actor_class + appearance_hints + display_name feed CSC_001 narration prompt context (per RES_001 §2 i18n).

### §14.12 WA_003 Forge

WA_003 closure pass adds 1 NEW AdminAction (already noted in PROG_001 boundary):
- `Forge:PromoteUntrackedToTracked { ephemeral_npc_id, cell_id, new_tier }` (Q2c)

V1+30d adds:
- `Forge:DemoteTrackedToUntracked` (AIT-D2)
- `Forge:EditMinorBehaviorScript` (AIT-D20)

### §14.13 IDF_001..005 Identity Foundation

IDF actor substrate aggregates (race_assignment / actor_language_proficiency / actor_personality / actor_origin / actor_ideology_stance) are independent of tier — they apply per-actor regardless. For Untracked NPCs (no aggregates), engine generates ephemeral identity facets via similar Stage 1 template approach if needed (V1+30d AIT-D22 reserved).

### §14.14 FF_001 Family Foundation

family_node + dynasty are independent of tier. Major NPCs likely have family_node entries; Minor may; Untracked do NOT (no aggregate).

### §14.15 FAC_001 Faction Foundation

faction + actor_faction_membership are independent of tier. Major NPCs may belong to factions; Minor may (per author declaration); Untracked do NOT (no membership stored).

### §14.16 07_event_model

07_event_model registers:
- 2 NEW EVT-T5 sub-types (`Generated:UntrackedNpcSpawn` + `Generated:UntrackedNpcDiscarded`)
- 1 NEW EVT-T3 cascade-trigger sub-shape (`TrackingTierTransition`)
- 1 NEW EVT-T8 AdminAction sub-shape (`Forge:PromoteUntrackedToTracked`)

EVT-G6 Coordinator: AIT_001 Generators trigger at observation events (cell-entry / cell-leave / session-end / promotion); independent timing from RES_001 + PROG_001 day-boundary chain.

### §14.17 Future PCS_001 PC Substrate

When PCS_001 lands DRAFT post-AIT_001:
- PCS_001 brief reads AIT_001 §3 NpcTrackingTier enum
- PC's actor_progression has `tracking_tier=None` (PCs implicitly always tracked)
- PCS_001 §S8 xuyên không body-substitution preserves PC status (PC remains PC; not subject to AIT tier transitions)

### §14.18 Future CULT_001 / FAC_001 / REP_001

V1+ priorities per IDF roadmap. AIT_001 ships orthogonal — these features layer on top (cultivation methods on Major NPCs / faction membership on Tracked / reputation per (actor, faction) on Tracked).

---

## §15 — RejectReason rule_id Catalog

### §15.1 `ai_tier.*` namespace V1 (registered in `_boundaries/02_extension_contracts.md` §1.4)

V1 rule_ids (8 total):

| rule_id | Trigger | Vietnamese display (i18n bundle default field) |
|---|---|---|
| `ai_tier.canonical_tier_required` | RealityManifest bootstrap: canonical_actor_decl missing tracking_tier | "Canonical NPC must declare tracking_tier" |
| `ai_tier.capacity_exceeded` | Tracked NPC count would exceed tier_capacity_caps | "Đã vượt số lượng NPC theo dõi tối đa" |
| `ai_tier.density_exceeded` | DensityDecl.count > 12 (Q8c) | "Mật độ NPC trong ô vượt giới hạn" |
| `ai_tier.template_invalid` | UntrackedTemplateDecl validation fail (place_type unknown / name_pool empty / stat_ranges kind_id unknown / actor_class unknown) | "Mẫu NPC không hợp lệ" |
| `ai_tier.action_forbidden_for_tier` | Minor attempts non-allowed PL_005 kind | "Hành động không phù hợp với cấp NPC" |
| `ai_tier.untracked_cannot_initiate` | Untracked NpcId attempts to initiate event | "NPC không theo dõi không thể khởi tạo hành động" |
| `ai_tier.promotion_target_not_observed` | Forge:PromoteUntrackedToTracked references ephemeral_npc_id not in session.untracked_cache | "Không thể thăng cấp NPC chưa được quan sát" |
| `ai_tier.untracked_role_unknown` | UntrackedRoleDecl role_id duplicate or invalid | "Vai trò NPC không xác định" |

### §15.2 V1+ reservations

- `ai_tier.scripted_attack_invalid` — V1+30d (AIT-D18)
- `ai_tier.tier_promotion_rejected` — V1+30d (significance threshold AIT-D1)
- `ai_tier.demotion_forbidden` — V1+30d (AIT-D2)
- `ai_tier.causal_ref_pin_violation` — V1+30d (AIT-D6)

---

## §16 — Acceptance Criteria

12 V1-testable scenarios. Each must pass deterministically per EVT-A9 replay.

### AC-AIT-1 — RealityManifest validates tier declarations
- Setup: RealityManifest with canonical_actor_decl missing tracking_tier
- Action: bootstrap reality
- Expected: AIT-V2 validator rejects with `ai_tier.canonical_tier_required`

### AC-AIT-2 — Tier capacity cap enforcement
- Setup: RealityManifest with 25 canonical_actor_decl Major (cap 20)
- Action: bootstrap reality
- Expected: AIT-V2 rejects with `ai_tier.capacity_exceeded { tier: Major, declared: 25, cap: 20 }`

### AC-AIT-3 — Density cap enforcement
- Setup: RealityManifest with `cell_untracked_density: { tavern: DensityDecl { count: 15 } }` (exceeds 12 cap)
- Action: bootstrap reality
- Expected: AIT-V3 rejects with `ai_tier.density_exceeded`

### AC-AIT-4 — Untracked NPC deterministic generation at cell-entry
- Setup: tu tiên reality; tavern PlaceType density=4; UntrackedTemplateDecl with 2 roles (3 patron + 1 wandering_swordsman)
- Action: PC enters tavern at fiction_day=15
- Expected: 4× `Generated:UntrackedNpcSpawn` events emitted with deterministic NpcIds per blake3(reality, tavern, 15, slot 0..3); session.untracked_cache contains 4 entries; replay produces identical NpcIds + stats

### AC-AIT-5 — Same-day re-entry produces same Untracked
- Setup: Continue from AC-AIT-4
- Action: PC leaves tavern, re-enters same fiction_day (no day boundary crossed)
- Expected: 4× `Generated:UntrackedNpcDiscarded { reason: CellLeave }` then 4× `Generated:UntrackedNpcSpawn` with SAME NpcIds (deterministic seed unchanged); session.untracked_cache reconstructed identically

### AC-AIT-6 — New-day re-entry produces different Untracked
- Setup: Continue from AC-AIT-4
- Action: PC sleeps 24h fiction (crosses day boundary to fiction_day=16); re-enters tavern
- Expected: cell-leave discarded day-15 Untracked; cell-entry generates day-16 Untracked with DIFFERENT NpcIds (deterministic seed for day-16); 4 different patrons present

### AC-AIT-7 — Stage 2 LLM-flavor lazy synthesis
- Setup: Continue from AC-AIT-4; PC initiates `/speak to wandering_swordsman` (Untracked)
- Action: PL_005 Speak cascade
- Expected: AIT-V1 validator passes (PC initiator allowed); Untracked has `llm_flavor_cache: None` → Stage 2 synthesis triggers; LLM generates dialogue style + backstory; `llm_flavor_cache: Some(...)` cached; subsequent `/speak` reuses cache (no duplicate LLM call)

### AC-AIT-8 — Forge promotion preserves NpcId
- Setup: Continue from AC-AIT-7; wandering_swordsman has cached Stage 2 flavor
- Action: Author Forge `PromoteUntrackedToTracked { ephemeral_npc_id: <blake3 hash>, cell_id: tavern, new_tier: Major }`
- Expected: AIT-V2 cap check passes (current Major count < 20); persona crystallizes into NPC_001 npc core with SAME NpcId (Q11a stable); ActorProgression aggregate created with Stage 1 stats as initial_value per kind_id; session.untracked_cache removes ephemeral_npc_id; emit `Generated:UntrackedNpcDiscarded { reason: PromotedToTracked }` + `TrackingTierTransition { from: None, to: Some(Major) }`

### AC-AIT-9 — Tier-aware AssemblePrompt budget
- Setup: scene with PC + 1 Major + 1 Minor + 4 Untracked; tier_roster_caps None (engine defaults 5/8/12)
- Action: AssemblePrompt persona section
- Expected: roster contains: PC FullPersona / Major FullPersona (2 of 5 used) / Minor CondensedPersona (1 of 8 used) / 4 Untracked SummaryLine (4 of 12 used); no overflow; total token budget under cap

### AC-AIT-10 — AssemblePrompt aggregate overflow
- Setup: festival cell with 30 Untracked (author-declared density override beyond default)
- Action: AssemblePrompt
- Expected: 12 Untracked SummaryLine roster lines; aggregate overflow line: "...and 18 other festival-goers fill the square."

### AC-AIT-11 — AIT-V1 TierActionValidator rejects Untracked initiator
- Setup: ephemeral_npc_id (Untracked) hypothetically initiates `/speak to PC` (forbidden per Q9 matrix)
- Action: turn-event submitted with actor=ephemeral_npc_id
- Expected: AIT-V1 rejects with `ai_tier.untracked_cannot_initiate`; turn rejected pre-PROG_001 cascade

### AC-AIT-12 — Cell-leave discards Untracked
- Setup: Continue from AC-AIT-7 (4 Untracked + Stage 2 cache for wandering_swordsman)
- Action: PC `/travel` to different cell
- Expected: 4× `Generated:UntrackedNpcDiscarded { reason: CellLeave }`; session.untracked_cache empty; Stage 2 cache cleared with wandering_swordsman entry; new cell observation triggers fresh generation

---

## §17 — V1 Minimum Delivery Summary

AIT_001 V1 ships:

| Component | Count |
|---|---|
| New enum types | NpcTrackingTier (2 variants) / UntrackedDiscardReason (3 V1 + 3 V1+) / PromptDetail (4 variants) / OverflowFormat (2) / DialogueRegister (4) / TriggerPattern (4) / EventPattern (3) / ScriptedReaction (3 V1; 2 V1+) / ScriptedAction (1 V1; 3 V1+) |
| New struct shapes | UntrackedTemplateDecl + UntrackedRoleDecl + StatRangeDecl + DensityDecl + TierCapacityCaps + TierRosterCaps + MinorBehaviorScript + DialogueTemplate + ScheduledActionDecl + ReactionDecl + UntrackedRuntimeState (ephemeral; non-aggregate) |
| New aggregates | 0 (Untracked = no aggregate; tier extension on existing PROG_001 actor_progression) |
| RealityManifest extensions | 5 OPTIONAL fields (tier_capacity_caps + untracked_templates + cell_untracked_density + tier_roster_caps + minor_behavior_scripts) |
| EVT-T5 Generated sub-types | 2 NEW (UntrackedNpcSpawn + UntrackedNpcDiscarded) |
| EVT-T3 Derived cascade-trigger | 1 NEW (TrackingTierTransition) |
| EVT-T8 AdminAction sub-shapes | 1 NEW (Forge:PromoteUntrackedToTracked) |
| Validator slots | AIT-V1 TierActionValidator + AIT-V2 TierCapacityValidator + AIT-V3 DensityValidator + AIT-V4 UntrackedTemplateValidator |
| Rule_ids `ai_tier.*` | 8 V1 + 4 V1+ reservations |
| Acceptance scenarios | 12 (AC-AIT-1..12) |
| Deferrals catalog | 21 (AIT-D1..D21) |

V1 enables:
- ✅ **Billion-NPC scaling** via 3-tier architecture (PC + Major + Minor + Untracked)
- ✅ **Quantum-observation lazy materialization** for Tracked NPCs (PROG_001 Q4 REVISED activated)
- ✅ **Deterministic Untracked generation** at cell-entry (replay-safe per EVT-A9)
- ✅ **Hybrid LLM cost** — Stage 1 cheap deterministic; Stage 2 lazy on-demand
- ✅ **Daily Untracked rotation** for natural sim feel
- ✅ **Forge admin promotion** for narrative significance preservation
- ✅ **Tier-aware AssemblePrompt budget** for LLM context economy
- ✅ **Per-tier action availability** for behavior model clarity
- ✅ **Author-declared MinorBehaviorScript** for scripted NPC routines

---

## §18 — Deferrals Catalog

Already enumerated in CONCEPT_NOTES §16.11. Summary in §1 V1 NOT shipping table.

---

## §19 — Open Questions (Closure Pass Items)

| ID | Question | Resolution path |
|---|---|---|
| AIT-Q1 | Stage 2 LLM-flavor synthesis prompt structure (token budget per call; specific fields included) | Closure pass with NPC_001 closure (persona assembly integration) |
| AIT-Q2 | UntrackedRuntimeState ephemeral storage location (session memory cache vs Redis Streams ephemeral?) | DP-engineering closure (out of AIT_001 scope; engineering choice) |
| AIT-Q3 | Forge promotion when PC has left cell containing Untracked (last_observed_cell may be stale) | V1: `cell_id` in promotion AdminAction is required; if PC left, Forge action carries last-known cell. V1+30d may add explicit "deferred promotion queue" |
| AIT-Q4 | i18n cross-cutting audit timing | Separate cross-cutting commit post AIT_001 LOCK; tracked in coordination notes |
| AIT-Q5 | Untracked persistence for narrative-pinned NPCs | V1+30d AIT-D6 causal-ref pin — when QST_001 V2 needs it |
| AIT-Q6 | Replay determinism for Stage 2 LLM-flavor (LLM non-deterministic by default) | V1: Stage 2 cache treated as session-ephemeral; replay regenerates with possibly different LLM output (acceptable since flavor is presentation only); V1+30d may add seeded LLM for replay consistency |

---

## §20 — Coordination Notes / Downstream Impacts

### §20.1 Co-locked changes in this commit

Per `_boundaries/_LOCK.md` claim (single combined `[boundaries-lock-claim+release]` commit):

- ✅ `AIT_001_ai_tier_foundation.md` — this DRAFT
- ✅ `_boundaries/01_feature_ownership_matrix.md` — register NpcTrackingTier enum + EVT-T5/T3/T8 sub-types + AIT-* stable-ID prefix
- ✅ `_boundaries/02_extension_contracts.md` §1.4 — `ai_tier.*` rule_id namespace prefix (8 V1 rule_ids)
- ✅ `_boundaries/02_extension_contracts.md` §2 — 5 RealityManifest extension fields
- ✅ `_boundaries/99_changelog.md` — entry
- ✅ `16_ai_tier/_index.md` — DRAFT row
- ✅ `16_ai_tier/00_CONCEPT_NOTES.md` §17 — Status DRAFT promoted
- ✅ `catalog/cat_16_AIT_ai_tier.md` — feature catalog (NEW)

### §20.2 Deferred follow-up commits (downstream features)

| Feature | Update | Priority | Lock cycle |
|---|---|---|---|
| **NPC_001** | Closure pass: REQUIRED `tracking_tier` field on CanonicalActorDecl + tier-aware persona assembly | HIGH | NPC_001 closure |
| **NPC_002 Chorus** | Closure pass: tier filter in priority calculation | HIGH | NPC_002 closure |
| **PL_005** | Closure pass: AIT-V1 TierActionValidator slot reference + Untracked target handling + Stage 2 synthesis hook | HIGH | PL_005 closure |
| **PROG_001** | tracking_tier field documentation update (was reserved; now active) — read-only consumer | MEDIUM | PROG_001 closure pass |
| **WA_003** | Add 1 ForgeEditAction sub-shape (`PromoteUntrackedToTracked`) | HIGH | WA_003 closure |
| **PL_001 Continuum** | Session lifecycle hooks for AIT discard | HIGH | PL_001 closure |
| **EF_001** | entity_binding location change cascade hook for AIT cell-leave discard | MEDIUM | EF_001 closure |
| **CSC_001** | Layer 3 LLM zone-assignment receives Untracked alongside Tracked | LOW | CSC_001 closure |
| **07_event_model** | Register 2 EVT-T5 sub-types + 1 EVT-T3 sub-shape + 1 EVT-T8 sub-shape | HIGH | event-model agent |
| **RES_001** | NPC eager → lazy migration alignment (PROG-D19) | V1+30d | RES_001 closure pass V1+30d |

### §20.3 Future feature coordination

**PCS_001 PC Substrate** (parallel agent commission post AIT_001 DRAFT): brief reads AIT_001 §3 NpcTrackingTier; PCs are `tracking_tier=None` always.

**CULT_001 Cultivation** (V1+ priority): wuxia cultivation method declarations layer on Major NPCs (cultivation requires Tracked tier); Untracked NPCs cannot cultivate (no progression aggregate).

**FAC_001 Faction** (already CANDIDATE-LOCK 2026-04-26..27 per 99_changelog): faction members typically Tracked (Major or Minor); Untracked may have faction-tag for narrative but no formal membership.

**REP_001 Reputation** (V1+ priority per IDF roadmap): per-(actor, faction) reputation projection — applies to Tracked NPCs only (Untracked have no persistent state).

### §20.4 ORG-* namespace alignment concern

(Already noted in PROG_001 §20.4) `15_organization/` was V3 reserved with ORG-*; IDF_004 Origin Foundation also took ORG-*. Conflict; `15_organization/` may need rename. Not AIT_001 scope; flagged for cross-feature coordination at next IDF closure pass review.

---

## §21 — Status

- **Created:** 2026-04-27 by main session post PROG_001 DRAFT closure (commit `9908940`) + FAC_001 closure (4-commit cycle 49a17ed/89f1473/120d5fe/closure)
- **Phase:** DRAFT 2026-04-27
- **Status target:** CANDIDATE-LOCK after Phase 3 review cleanup + closure pass + 10 §20.2 downstream applied
- **Companion docs:**
  - [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q12 LOCKED matrix §16)
- **Lock-coordinated commit:** This commit + 7 sibling boundary file updates under single `[boundaries-lock-claim+release]` prefix
