# 02 — Extension Contracts for Shared Schemas

> **Status:** seed 2026-04-25.
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.

---

## Why this file exists

Some schemas are SHARED across many features:
- `TurnEvent` payload — extended by PL_002, NPC_002, WA_006, ...
- `RealityManifest` — extended by PL_001, WA_001, WA_002, WA_006, NPC_001, ...
- Capability JWT claims — extended by WA_003, PLT_001, PLT_002, WA_006, ...
- `EVT-T8 AdminAction` sub-shapes — extended by WA_003, PLT_001, PLT_002, WA_006, ...

Without a contract, these schemas drift:
- Two features add the same field name with different semantics
- A feature removes a field another feature depends on
- Schema versioning becomes ambiguous

This file locks the EXTENSION RULES per shared schema. Each section below is a contract.

---

## §1 — `TurnEvent` envelope

### Owner

[**PL_001 Continuum**](../features/04_play_loop/PL_001_continuum.md) §3.5.

### Current shape (TurnEventSchema = 1, 2026-04-25)

```rust
pub struct TurnEvent {
    // ─── Continuum-owned core (MUST exist) ───
    pub actor: ActorId,
    pub intent: TurnIntent,                       // Speak | Action | MetaCommand | FastForward | Narration
    pub fiction_duration_proposed: FictionDuration,
    pub narrator_text: Option<String>,            // post-validation; None on Rejected
    pub canon_drift_flags: Vec<DriftFlag>,
    pub outcome: TurnOutcome,                     // Accepted | Rejected { reason: RejectReason }
    pub idempotency_key: Uuid,                    // client-issued
    pub causal_refs: Vec<CausalRef>,              // EVT-A6 typed causal-refs

    // ─── Feature-extended (additive per I14) ───
    pub command_kind: Option<CommandKind>,        // PL_002 owns CommandKind enum closed set
    pub command_args: Option<serde_json::Value>,  // PL_002 owns per-command schemas
    pub reaction_intent: Option<ReactionIntent>,  // NPC_002 owns ReactionIntent enum
    pub aside_target: Option<ActorId>,            // NPC_002
    pub action_kind: Option<ActionKind>,          // NPC_002 owns ActionKind enum + GestureKind
    // ... future feature fields
}

pub enum TurnIntent {  // Continuum-owned closed set
    Speak,
    Action,
    MetaCommand,
    FastForward,
    Narration,
}

pub enum TurnOutcome {  // Continuum-owned closed set
    Accepted,
    Rejected { reason: RejectReason },
}

pub struct RejectReason {  // Continuum-owned envelope shape
    pub rule_id: String,                          // namespaced — see §1.4 below
    pub user_message: I18nBundle,                 // RES_001 DRAFT 2026-04-26 — multi-language user-facing
                                                  // text per i18n contract (RES_001 §2.3). English `default`
                                                  // required; per-locale `translations: HashMap<LangCode, String>`.
                                                  // Existing features' Vietnamese hardcoded reject copy
                                                  // backfills into `default` (English) as cross-cutting audit
                                                  // (deferred — low-priority cosmetic). PL_001 closure pass
                                                  // folds in (additive per I14).
    pub detail: serde_json::Value,                // feature-defined per rule_id namespace
}

// I18nBundle — engine-wide cross-cutting type introduced by RES_001 §2 (2026-04-26).
// Used by any feature for user-facing display strings.
pub struct I18nBundle {
    pub default: String,                          // English-required fallback
    pub translations: HashMap<LangCode, String>,  // ISO-639-1 lowercase ("vi", "zh", ...)
                                                  // ("en" forbidden — use `default` field)
}
pub type LangCode = String;
```

### Extension rules

1. **Additive only.** Features MAY add new optional `Option<T>` fields. Features MUST NOT modify existing field types or remove fields. Per foundation I14.
2. **Schema version on bump.** When a feature ADDS a field, the feature's design doc declares "TurnEventSchema v1 → v2: added field `foo: Option<Foo>`". The version number is monotonic; envelope owner (Continuum) approves the bump.
3. **Continuum owns core.** Fields in the "Continuum-owned core" block above are part of the envelope; only Continuum may modify them. Other features extend the additive section.
4. **Closed enums (TurnIntent, TurnOutcome) are Continuum's.** Adding a new TurnIntent variant requires a Continuum design-change. Features cannot add intents.
5. **Feature-defined enums (CommandKind, ReactionIntent, ActionKind, ...) are owned by their respective features.** Each enum's closed set is locked in the owning feature's doc; additive evolution per I14.
6. **No co-occurrence rules baked into the envelope.** "If `command_kind=Sleep` then `intent=FastForward`" is a SEMANTIC rule, not a schema rule. Validators enforce semantic rules; envelope just declares fields.

### When a feature wants to add a field

1. Lock-claim `_LOCK.md` of `_boundaries/`
2. Update §1 of this file: add the new field with owner attribution
3. Update [`01_feature_ownership_matrix.md`](01_feature_ownership_matrix.md) "Schema / envelope ownership" row
4. Bump `TurnEventSchema` if required (Continuum approval — typically auto for additive optional fields)
5. Append `99_changelog.md` row
6. Lock-release
7. The feature's own design doc cites this file's contract

### §1.4 RejectReason rule_id namespace ownership

Each feature owns a prefix in the `rule_id` string namespace:

| Prefix | Owner |
|---|---|
| `lex.*` | WA_001 Lex |
| `heresy.*` | WA_002 Heresy |
| `mortality.*` | WA_006 Mortality (provisional; WA_006 over-extended) |
| `world_rule.*` | cross-cutting (any feature can use; documented in feature's design) |
| `oracle.*` | 05_llm_safety A3 |
| `canon_drift.*` | 05_llm_safety A6 |
| `capability.*` | DP-K9 / 05_llm_safety A6 |
| `parse.*` | PL_002 Grammar |
| `chorus.*` | NPC_002 Chorus |
| `forge.*` | WA_003 Forge |
| `charter.*` | PLT_001 Charter |
| `succession.*` | PLT_002 Succession |
| `interaction.*` | PL_005 Interaction (added 2026-04-26 DRAFT; expanded 2026-04-26 PL folder closure to 5 V1 rule_ids — target_unreachable / tool_unavailable / tool_invalid / target_invalid / intent_unsupported; +1 V1+ reservation: cross_cell_disallowed. Note: `target_dead` is owned by `entity.lifecycle_dead` per Stage 3.5.a entity_affordance namespace allocation, NOT `interaction.*`.) |
| `status.*` | PL_006 Status Effects (added 2026-04-26 DRAFT; expanded 2026-04-26 PL folder closure to 3 V1 rule_ids — unknown_flag / dispel_not_present / invalid_magnitude; +3 V1+ reservations: flag_forbidden_in_reality / scheduled_expire_collision / stack_policy_violation. Note: `status.target_dead` is owned by `entity.lifecycle_dead` per Stage 3.5.a entity_affordance namespace allocation, NOT `status.*` — same ownership pattern as `interaction.*`. V1 most rejects are schema-level; user-facing reject only via Stage 3.5.a entity.lifecycle_dead.) |
| `entity.*` | EF_001 Entity Foundation (added 2026-04-26 DRAFT; expanded 2026-04-26 closure pass to 10 V1 rule_ids — entity_destroyed / entity_removed / entity_suspended / affordance_missing / invalid_entity_type / invalid_lifecycle_transition / unknown_entity / **duplicate_binding** / **entity_type_mismatch** / **lifecycle_log_immutable**; +2 V1+ reservations: cyclic_holder_graph / cross_reality_reference) |
| `place.*` | PF_001 Place Foundation (added 2026-04-26 DRAFT; expanded 2026-04-26 Phase 3 cleanup to 12 V1 rule_ids — missing_decl / duplicate_place / invalid_structural_transition / unknown_place / connection_target_unknown / connection_locked / connection_private / connection_hidden / no_reverse_connection / fixture_seed_uid_collision / invalid_place_type_for_channel_tier / **self_referential_connection**; +4 V1+ reservations: scheduled_decay_collision / cross_reality_connection / procedural_generation_rejected / **connection_gate_unresolved**) |
| `map.*` | MAP_001 Map Foundation (added 2026-04-26 DRAFT; expanded 2026-04-26 Phase 3 cleanup to 13 V1 rule_ids — missing_layout_decl / duplicate_layout / position_out_of_bounds / connection_target_unknown / cross_tier_connection_disallowed / invalid_tier_metadata / asset_ref_unresolved / asset_review_pending / connection_distance_invalid / self_referential_connection / **tier_field_mismatch** / **connection_duration_invalid** / **asset_pipeline_not_active_v1**; +3 V1+ reservations: cross_reality_layout / layout_too_dense / connection_method_unsupported) |
| `csc.*` | CSC_001 Cell Scene Composition (added 2026-04-26 DRAFT; expanded 2026-04-26 Phase 3 cleanup to 9 V1 rule_ids — skeleton_not_found / invalid_zone_assignment / zone_overlap / actor_on_non_walkable / item_on_non_placeable / entity_missing_from_assignment / layer3_retry_exhausted / placetype_no_skeleton_v1 / **zone_empty_fallback_used**; +4 V1+ reservations: skeleton_invalid / procedural_density_too_high / narration_unsafe_content / **layer3_occupant_set_changed**) |
| `resource.*` | RES_001 Resource Foundation (added 2026-04-26 DRAFT; 12 V1 rule_ids — balance.insufficient / balance.invalid_owner / balance.negative_amount_forbidden / vital.below_zero / vital.body_bound_transfer_forbidden / trade.npc_insufficient_funds / trade.npc_insufficient_goods / trade.pc_insufficient_funds / trade.pc_insufficient_goods / trade.invalid_price / harvest.empty_cell / harvest.not_owner_or_orphan; +3 V1+ reservations: balance.cap_exceeded / trade.bargaining_failed / item.instance_not_found) |
| `race.*` | IDF_001 Race Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate); 5 V1 rule_ids — unknown_race_id / assignment_immutable / lex_axiom_forbidden (V1+ reserved; V1 schema-present but always None axiom requires_race) / size_category_invalid / lifespan_invalid; +4 V1+ reservations: cross_reality_mismatch / transformation_invalid / reincarnation_invalid_target / cyclic_lineage_v1plus. V1 user-facing rejects: unknown_race_id + assignment_immutable only (size + lifespan are schema-level canonical seed validation, unreachable in normal operation). i18n: V1 ships `user_message: I18nBundle` per RES_001 §2 contract from day 1. |
| `language.*` | IDF_002 Language Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate); 4 V1 rule_ids — unknown_language_id / speaker_proficiency_insufficient / listener_proficiency_insufficient (V1+ active; V1 warning only per LNG-Q6 LOCKED) / proficiency_axis_invalid; +2 V1+ reservations: dialect_mismatch / code_switch_unsupported. V1 user-facing rejects: unknown_language_id + speaker_proficiency_insufficient. SPIKE_01 turn 5 literacy slip canonical reproducibility gate — A6 canon-drift detector consumes proficiency at Stage 8 V1+. **LanguageId distinct from RES_001 LangCode** (in-fiction vs engine UI; runtime newtype assert V1; LNG-D8 compile-time V1+). i18n: V1 ships I18nBundle from day 1. |
| `personality.*` | IDF_003 Personality Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate); 3 V1 rule_ids — unknown_archetype_id / assignment_immutable / opinion_modifier_invalid; +2 V1+ reservations: archetype_evolution_invalid_path / overlay_conflict. V1 user-facing rejects: unknown_archetype_id + assignment_immutable only (opinion_modifier_invalid schema-level). 12 V1 archetypes per POST-SURVEY-Q1 LOCKED (Stoic/Hothead/Cunning/Innocent/Pious/Cynic/Worldly/Idealist + Loyal/Aloof/Ambitious/Compassionate). Resolves PL_005b §2.1 speaker_voice orphan ref + PL_005c INT-INT-D5 per-personality opinion modifier. i18n: V1 ships I18nBundle from day 1. |
| `origin.*` | IDF_004 Origin Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate); 4 V1 rule_ids — unknown_native_language / unknown_birthplace / assignment_immutable / unknown_ideology_ref; +2 V1+ reservations: lineage_graph_invalid (V1+ FF_001) / pack_not_in_registry (V1+ origin packs). V1 user-facing rejects: assignment_immutable only (others schema-level canonical seed validation). V1 minimal stub 4 fields (birthplace + lineage_id opaque + native_language + default_ideology_refs) per ORG-Q1 LOCKED. **V1+ FF_001 Family Foundation HIGH priority post-IDF closure** per POST-SURVEY-Q4 + ORG-D12. i18n: V1 ships I18nBundle from day 1. |
| `ideology.*` | IDF_005 Ideology Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate); 3 V1 rule_ids — unknown_ideology_id / duplicate_stance_entry / lex_axiom_forbidden (V1+ active; V1 reserved); +5 V1+ reservations: tenet_violation (V1+ IDL-D1) / sect_membership_required (V1+ FAC_001 IDL-D2) / conflict_auto_drop_required / invalid_fervor_transition / conversion_cost_unmet (V1+ IDL-D11). **ONLY mutable IDF aggregate V1.** Multi-stance V1 per IDL-Q2 (Wuxia syncretism). Atheist = empty Vec. **Free V1 conversion per IDL-Q13 LOCKED (POST-SURVEY-Q3)** — cost mechanic V1+ IDL-D11. i18n: V1 ships I18nBundle from day 1. |
| `family.*` | FF_001 Family Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate post-IDF priority per IDF_004 ORG-D12); 8 V1 rule_ids — unknown_actor_ref / unknown_dynasty_id / bidirectional_sync_violation / cyclic_relation / duplicate_relation / relation_kind_mismatch / deceased_target / synthetic_actor_forbidden; +4 V1+ reservations: cross_reality_mismatch (V2+ Heresy per Q7) / cyclic_lineage_traversal (V1+ traversal API FF-D2) / dynasty_extinction (V1+ cleanup) / adoption_consent_violation (V1+ V2+ consent system). V1 user-facing reject: deceased_target only (Marriage/Adoption attempts on deceased); others schema-level canonical seed validation. **Boundary discipline:** FF_001 = biological + adoption only; V1+ FAC_001 owns sect/master-disciple/sworn (per Q4 LOCKED). i18n: V1 ships I18nBundle from day 1. |
| `progression.*` | PROG_001 Progression Foundation (added 2026-04-26 DRAFT — 6th V1 foundation; multi-genre dynamic progression substrate; closes V1 foundation tier); 7 V1 rule_ids — training.kind_unknown / training.rule_invalid / breakthrough.condition_unmet / breakthrough.invalid_tier / cap.exceeded / combat.formula_invalid / combat.stat_term_unknown; +6 V1+ reservations: atrophy.no_practice (PROG-D5) / deviation.cultivation_failed (PROG-D2 走火入魔) / training.prereq_unmet (Q3j V1+30d) / combat.proposed_out_of_range (Q7e V1+30d) / combat.element_resistance_invalid (V1+ DF7 PROG-D24) / combat.critical_threshold_invalid (V1+ PROG-D25). V1 user-facing rejects: cap.exceeded (HardCap) + breakthrough.condition_unmet (Forge-triggered fail). All Q1-Q7 LOCKED via 6-batch deep-dive 2026-04-26. **Hybrid observation-driven NPC model (Q4 REVISED)**: PCs eager + Tracked NPCs lazy + Untracked = no aggregate (future AI Tier feature). chaos-backend reference: actor-core Subsystem→Contribution V1+30d lift (PROG-D6); damage law chain V1+ DF7-equivalent (PROG-D24). DF7 PC Stats placeholder SUPERSEDED. i18n: V1 ships I18nBundle from day 1 per RES_001 §2 cross-cutting contract. |
| `faction.*` | FAC_001 Faction Foundation (added 2026-04-26 DRAFT — Tier 5 Actor Substrate post-IDF + post-FF_001 priority); 8 V1 rule_ids — unknown_faction_id / unknown_role_id / multi_membership_forbidden_v1 (per Q2 REVISION cap=1) / master_cross_sect_forbidden / master_authority_violation / cyclic_master_chain / ideology_binding_violation (RESOLVES IDF_005 IDL-D2) / synthetic_actor_forbidden; +4 V1+ reservations: cross_reality_mismatch (V2+ Heresy per Q8) / lex_axiom_forbidden (V1+ when first faction-gated axiom ships per Q9) / sworn_bond_unsupported_v1 (V1+ FAC-D10 enrichment activation per Q7 REVISION) / member_role_count_exceeded (V1+ when RoleDecl.max_actors_in_role enrichment ships). V1 user-facing rejects: multi_membership_forbidden_v1 + ideology_binding_violation only (others schema-level canonical seed validation). **3 Q-REVISIONS:** Q2 Vec+cap=1 / Q4 numeric-only V1 / Q7 defer sworn V1+. **RESOLVES:** IDF_005 IDL-D2 (sect membership ideology binding) + FF_001 FF-D7 (master-disciple). **Boundary discipline:** FAC_001 = sect/order/clan-retinue/guild + master-disciple + V1+ sworn brotherhood; FF_001 = biological/adoption only (separated). i18n: V1 ships I18nBundle from day 1. |
| `reputation.*` | REP_001 Reputation Foundation (added 2026-04-27 DRAFT — Tier 5 Actor Substrate post-FAC_001 priority); 6 V1 rule_ids — unknown_actor_id / unknown_faction_id / score_out_of_range (clamp to [-1000, +1000]) / synthetic_actor_forbidden / cross_reality_mismatch (V2+ Heresy per Q8) / duplicate_row (multi-row per (actor, faction) pair); +4 V1+ reservations: runtime_delta_unsupported_v1 (V1+ when Q5 V1+ runtime gameplay ships) / cascade_unsupported_v1 (V1+ Q6 cascade per REP-D2) / decay_unsupported_v1 (V1+ Q7 decay per REP-D3) / tier_threshold_violation (V1+ when author-declared per-faction tiers ship per REP-D4). V1 user-facing rejects: score_out_of_range only (others schema-level canonical seed validation). **1 Q-REVISION:** Q4 Always Neutral (0) V1; V1+ hybrid (membership-derived) alongside Q6 cascade. **RESOLVES:** FAC_001 FAC-D7 (per-(actor, faction) reputation projection). **3-layer separation discipline per Q10 LOCKED:** REP_001 actor_faction_reputation (per-(actor, faction) bounded standing) ≠ RES_001 SocialCurrency::Reputation (per-actor unbounded global "danh tiếng" sum) ≠ NPC_001 npc_pc_relationship_projection (per-(NPC, PC) personal opinion). 8-tier engine-fixed ReputationTier (Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted) with asymmetric thresholds + Wuxia I18n display labels. i18n: V1 ships I18nBundle from day 1. |
| `ai_tier.*` | AIT_001 AI Tier Foundation (added 2026-04-27 DRAFT — architecture-scale; NOT foundation tier — 3-tier NPC architecture for billion-NPC scaling); 8 V1 rule_ids — canonical_tier_required / capacity_exceeded / density_exceeded / template_invalid / action_forbidden_for_tier / untracked_cannot_initiate / promotion_target_not_observed / untracked_role_unknown; +4 V1+ reservations: scripted_attack_invalid (AIT-D18) / tier_promotion_rejected (AIT-D1 V1+30d significance threshold) / demotion_forbidden (AIT-D2 V1+30d) / causal_ref_pin_violation (AIT-D6 V1+30d). V1 user-facing rejects: capacity_exceeded + action_forbidden_for_tier + untracked_cannot_initiate + promotion_target_not_observed (others schema-level canonical seed validation). All 12 Qs LOCKED via 4-batch deep-dive 2026-04-26..27 (Q1+Q2 / Q4+Q5+Q11 / Q6+Q12 / Q7+Q8+Q9; Q3 + Q10 implicit). **Quantum-observation NPC model**: PCs eager + Tracked NPCs lazy + Untracked = no aggregate (Schrödinger pattern; activates PROG_001 §3.1 reserved tracking_tier field). 3-tier hierarchy: PC + Major (LLM-driven; cap≤20) + Minor (rule-based scripted; cap≤100) + Untracked (ephemeral; deterministic blake3 NpcId; daily rotation). chaos-backend reference: Stellaris pops vs named characters pattern. PROG-D19 cross-feature alignment with RES_001 NPC eager auto-collect → lazy migration V1+30d. i18n: V1 ships I18nBundle from day 1. |

Continuum DOES NOT enumerate every variant. Each feature's design doc owns its prefix's rule_ids and the corresponding Vietnamese reject copy. **i18n update 2026-04-26 (RES_001 DRAFT):** Going forward, new feature designs SHOULD use `RejectReason.user_message: I18nBundle` (English `default` field required + per-locale `translations` HashMap) per RES_001 §2 i18n contract. Existing features' Vietnamese hardcoded reject copy is functional V1 (cross-cutting i18n audit deferred — low priority cosmetic).

---

## §2 — `RealityManifest`

### Owner

⚠ **Currently unowned.** Continuum was first to declare its part (PL_001 §16) but the manifest is now extended by 5+ features.

**Proposal:** create a new infrastructure feature `IF_001_reality_manifest.md` (under `features/01_infrastructure/` if/when that folder is created) that owns the manifest envelope. Until then, this file (`02_extension_contracts.md` §2) IS the contract.

### Current shape (RealityManifestSchema = 1, 2026-04-25)

```rust
pub struct RealityManifest {
    // ─── Identity (always required) ───
    pub reality_id: RealityId,
    pub book_canon_ref: BookCanonRef,
    pub schema_version: u32,

    // ─── Continuum-owned (PL_001 §16) ───
    pub starting_fiction_time: FictionTimeTuple,
    pub root_channel_tree: RootChannelDecl,        // continent → country → district → town hierarchy
    pub canonical_actors: Vec<CanonicalActorDecl>,

    // ─── NPC_001 Cast extension to CanonicalActorDecl ───
    // CanonicalActorDecl gains: category, core_beliefs_ref, flexible_state_init,
    //                          knowledge_tags, greeting_obligation, priority_tier_hint

    // ─── WA_001 Lex extension ───
    pub lex_config: Option<LexConfigDecl>,         // None = use Permissive default

    // ─── WA_002 Heresy extension ───
    pub contamination_allowances: Vec<ContaminationAllowanceDecl>,

    // ─── WA_006 Mortality extension (provisional) ───
    pub mortality_config: Option<MortalityConfigDecl>,

    // ─── PF_001 Place Foundation extension (added 2026-04-26 DRAFT) ───
    // REQUIRED V1: every cell-tier channel from root_channel_tree MUST have a corresponding
    // PlaceDecl; cells without decl reject bootstrap with `place.missing_decl`.
    // Higher-tier channels (continent/country/district/town) MUST NOT have place rows V1.
    pub places: Vec<PlaceDecl>,                    // see PF_001 §9 for PlaceDecl shape

    // ─── MAP_001 Map Foundation extension (added 2026-04-26 DRAFT) ───
    // REQUIRED V1: every channel (continent/country/district/town/cell) from root_channel_tree
    // MUST have a corresponding MapLayoutDecl; channels without decl reject bootstrap with
    // `map.missing_layout_decl`. Cell-tier MapLayoutDecl has tier_metadata=None + connections=[]
    // (PF_001 supplies cell semantic + cell ConnectionDecl); non-cell MapLayoutDecl has full schema.
    pub map_layout: Vec<MapLayoutDecl>,            // see MAP_001 §9 for MapLayoutDecl shape
    pub travel_defaults: TravelDefaults,           // V1 cell-to-cell fallback duration; see MAP_001 §8 + §9

    // ─── CSC_001 Cell Scene Composition extension (added 2026-04-26 DRAFT) ───
    // OPTIONAL V1: per-cell author override of skeleton template. Empty default means engine
    // selects via §4.3 algorithm (PlaceType compat + hash(cell_id) % len). When present, override
    // takes priority. Unknown SkeletonId in override falls back to default_generic_room (logs
    // `csc.skeleton_not_found`). See CSC_001 §10.1.
    pub scene_skeleton_overrides: HashMap<ChannelId, SkeletonId>,

    // ─── RES_001 Resource Foundation extensions (added 2026-04-26 DRAFT) ───
    // ALL OPTIONAL V1 — engine defaults apply when omitted (per RES_001 §3.5 + §9.2).
    // Empty/None = single-currency default + universal vital max + no producers + no maintenance.

    /// Author-declared resource kinds. Empty → engine V1 defaults (Copper currency + Food/Water
    /// consumables + Wood/Iron/Stone materials + Reputation social currency + Hp/Stamina vitals).
    pub resource_kinds: Vec<ResourceKindDecl>,

    /// Author-declared currencies (Q10). Empty → single default Copper (rate=1).
    /// Multi-tier example (Vietnamese xianxia): [copper(rate=1), silver(rate=100), gold(rate=10000)].
    /// Each CurrencyDecl carries `display_name: I18nBundle` per RES_001 §2 i18n contract.
    pub currencies: Vec<CurrencyDecl>,

    /// Author-declared vital profiles per actor-class (Q3e). Empty → engine defaults (PC: 100/100
    /// Hp/Stamina with TimeBased/RestBased regen; NPC peasant: 50/50). PCS_001 + NPC_001 may
    /// declare per-actor-class overrides referencing this vector.
    pub vital_profiles: Vec<VitalProfileDecl>,

    /// Cell production rates per PlaceType (Q4d). Empty → no cells produce. Each ProducerProfile
    /// declares: `place_type` + `outputs: Vec<ProductionOutput>` + `stockpile_cap`.
    pub producers: Vec<ProducerProfile>,

    /// Trade pricing per kind (Q12a global V1). Empty → no trade allowed (V1+30d adds per-cell
    /// variance). Each PriceDecl: `{ kind, base_buy_price, base_sell_price, primary_currency }`
    /// with invariant base_buy_price >= base_sell_price (NPC profit margin = sink #3).
    pub prices: Vec<PriceDecl>,

    /// Cell stockpile cap per PlaceType (Q2c production constraint). Empty → engine default 1000
    /// units per cell. Production halts when stockpile reaches cap.
    pub cell_storage_caps: HashMap<PlaceTypeRef, u64>,

    /// Cell maintenance cost per PlaceType (Q2c sink #2). Empty/None per type → no maintenance
    /// required. Daily maintenance Generator deducts from owner inventory; insufficient → cell
    /// production halts.
    pub cell_maintenance_profiles: HashMap<PlaceTypeRef, MaintenanceCost>,

    /// Initial resource distribution at reality bootstrap. Empty → all entities start with empty
    /// inventories (NPCs spawn with 0 of everything). Authors typically seed NPCs with starter gold
    /// + food.
    pub initial_resource_distribution: Vec<InitialDistributionDecl>,

    /// Initial Reputation distribution (SocialCurrency Q1c V1). Empty → all actors start at 0.
    /// HashMap<ActorRef, i64> — value can be negative (notorious) or positive (renowned).
    pub social_initial_distribution: HashMap<ActorRef, i64>,

    // ─── NPC_003 NPC Desires LIGHT extensions (added 2026-04-26 DRAFT) ───
    // OPTIONAL V1 — sandbox-mitigation Path A. NPC desires are author-declared narrative scaffolding
    // (NO state machine; NO objective tracking; NO rewards — just LLM-context goal hints).
    // Empty default → NPCs have no declared desires; LLM falls back to core_beliefs / flexible_state.

    /// Per-NPC initial desires. Indexed by NpcId. Each NPC ≤ 5 desires (validator-enforced).
    /// NpcDesireDecl: { desire_id, kind: I18nBundle, intensity: u8 (1-10), satisfied: bool, references: Vec<EntityRef> }.
    /// LLM AssemblePrompt persona context renders top-N intensity-sorted desires per active locale.
    pub npc_desires: HashMap<NpcId, Vec<NpcDesireDecl>>,

    /// AssemblePrompt N — top-N highest-intensity desires included in NPC persona context.
    /// Default: 3 (matches PL_001 §17 prompt-budget discipline). Author-tunable per reality.
    pub desires_prompt_top_n: u8,

    // ─── IDF_001 Race Foundation extension (added 2026-04-26 DRAFT — Tier 5 Actor Substrate) ───
    // REQUIRED V1: every reality MUST declare ≥1 race in races (Modern reality with single
    // Human race still explicit). RaceDecl shape per IDF_001 §3.2: { race_id, display_name (I18nBundle),
    // default_lifespan_years (u16), size_category (6-variant Tiny/Small/Medium/Large/Huge/Gargantuan),
    // default_mortality_kind_override (Option<MortalityKind>), allowed_lex_axiom_tags (Vec<String>
    // for V1+ Lex gate; V1 always populated but never consumed), canon_ref (Option<GlossaryEntityId>) }.
    // Cross-reality RaceId collision allowed (different realities have different race semantics for
    // same string). Wuxia preset ships 5 races (Phàm nhân/Cultivator/Demon/Ghost/Beast); Modern 1
    // (Human); Sci-fi 3 (Human/AlienX/AlienY).
    pub races: Vec<RaceDecl>,                      // see IDF_001 §3.2 for RaceDecl shape

    // ─── IDF_002 Language Foundation extension (added 2026-04-26 DRAFT — Tier 5 Actor Substrate) ───
    // REQUIRED V1: every reality MUST declare ≥1 language. LanguageDecl shape per IDF_002 §3.2:
    // { language_id, display_name (I18nBundle), writing_system (5-variant: None/Logographic/
    // Alphabetic/Syllabary/Custom{name}), default_in_origin_packs (Vec<OriginPackId> V1+ IDF_004
    // ref; empty V1), canon_ref (Option<GlossaryEntityId>) }. LanguageId distinct from
    // RES_001 LangCode (in-fiction vs engine UI ISO-639-1; runtime newtype assert V1). Wuxia
    // preset 4 languages (Quan thoại / Cổ ngữ / Tiếng địa phương / Đạo ngôn); Modern 3 (Tiếng
    // Việt / Tiếng Anh / Tiếng Trung); Sci-fi 3 (Common Tongue / AlienXLanguage / AlienYLanguage).
    pub languages: Vec<LanguageDecl>,              // see IDF_002 §3.2 for LanguageDecl shape

    // ─── IDF_003 Personality Foundation extension (added 2026-04-26 DRAFT — Tier 5 Actor Substrate) ───
    // REQUIRED V1: 12 universal archetypes per POST-SURVEY-Q1 LOCKED. PersonalityArchetypeDecl
    // shape per IDF_003 §3.2: { archetype_id, display_name (I18nBundle), voice_register (5-variant),
    // opinion_modifier_table (HashMap<PersonalityArchetypeId, i8> -10..=+10; 12×12=144 entries
    // required per PRS-Q9 LOCKED), speech_pattern_hints (Vec<String> for V1+ NPC_002 LLM prompt),
    // canon_ref }. 12 V1 archetypes universal across all reality presets (Wuxia/Modern/Sci-fi):
    // Stoic / Hothead / Cunning / Innocent / Pious / Cynic / Worldly / Idealist + Loyal / Aloof /
    // Ambitious / Compassionate. Resolves PL_005b §2.1 speaker_voice orphan ref + PL_005c INT-INT-D5.
    pub personality_archetypes: Vec<PersonalityArchetypeDecl>,    // see IDF_003 §3.2

    // ─── IDF_004 Origin Foundation extension (added 2026-04-26 DRAFT — Tier 5 Actor Substrate) ───
    // OPTIONAL V1: empty registry V1 (origin packs are content; populated V1+ when first reality
    // ships cultural pack content). V1 actor_origin.origin_pack_id stays None typical.
    // OriginPackDecl shape per IDF_004 §3.2: { origin_pack_id, display_name (I18nBundle),
    // default_birthplace_channel, default_native_language, default_ideology_refs, naming_convention
    // (V1+ ORG-D3), values_list (V1+ ORG-D2), canon_ref }.
    pub origin_packs: Vec<OriginPackDecl>,         // see IDF_004 §3.2; OPTIONAL V1 (empty Vec valid)

    // ─── IDF_005 Ideology Foundation extension (added 2026-04-26 DRAFT — Tier 5 Actor Substrate) ───
    // REQUIRED V1: every reality declares ≥1 ideology (atheist-only is still a declared landscape).
    // IdeologyDecl shape per IDF_005 §3.2: { ideology_id, display_name (I18nBundle),
    // parent_ideology_id (V1+ hierarchy schema slot per IDL-Q4), lex_axiom_tags (Vec<String> for
    // V1+ Lex gate per IDL-Q5), canon_ref }. Wuxia preset 5 ideologies (Đạo / Phật / Nho /
    // pure-martial / animism); Modern 3 (secular_humanism / theist / atheist); Sci-fi 3
    // (post_religious / corporate_ethics / cosmic_nihilism). Multi-stance per actor V1 per IDL-Q2
    // LOCKED — actor_ideology_stance.stances Vec supports wuxia syncretism.
    pub ideologies: Vec<IdeologyDecl>,             // see IDF_005 §3.2

    // ─── FF_001 Family Foundation extensions (added 2026-04-26 DRAFT — Tier 5 Actor Substrate post-IDF) ───
    // REQUIRED V1: every reality declares canonical_dynasties + canonical_family_relations (sparse
    // storage allowed; empty Vec valid for sandbox / family-less reality). Per Q5 LOCKED + EVT-A10:
    // NO separate family_event_log aggregate; events in channel stream as EVT-T3/T4 sub-types.
    //
    // DynastyDecl shape per FF_001 §3.2 + 00_CONCEPT_NOTES §7:
    // { dynasty_id, display_name (I18nBundle), founder_actor_id (Option), canon_ref }.
    // V1+ enrichment additive (parent_dynasty_id for cadet branches; traditions; perks).
    pub canonical_dynasties: Vec<DynastyDecl>,     // see FF_001 §3.2; sparse — only declared dynasties

    // FamilyRelationDecl shape per FF_001 §1 + 00_CONCEPT_NOTES §7:
    // { actor_id, parent_actor_ids: Vec<(ActorId, RelationKind)>, sibling_actor_ids: Vec<ActorId>,
    //   spouse_actor_ids: Vec<ActorId>, children_actor_ids: Vec<(ActorId, RelationKind)>,
    //   dynasty_id: Option<DynastyId>, is_deceased: bool }.
    // 6-variant RelationKind enum: BiologicalParent / AdoptedParent / Spouse / BiologicalChild /
    // AdoptedChild / Sibling per Q6 LOCKED.
    // Bidirectional sync validated at canonical seed (Lão Ngũ.children includes Tiểu Thúy AND
    // Tiểu Thúy.parents includes Lão Ngũ). Cyclic relations rejected. Duplicate refs rejected.
    pub canonical_family_relations: Vec<FamilyRelationDecl>, // see FF_001 §1; sparse — declared per actor

    // ─── FAC_001 Faction Foundation extensions (added 2026-04-26 DRAFT — Tier 5 Actor Substrate post-IDF + post-FF_001) ───
    // REQUIRED V1: every reality declares canonical_factions + canonical_faction_memberships (sparse
    // storage allowed; empty Vec valid for sandbox / faction-less reality). RESOLVES IDF_005 IDL-D2
    // (sect membership ideology binding) + FF_001 FF-D7 (master-disciple sect lineage).
    //
    // FactionDecl shape per FAC_001 §3.1: { faction_id, display_name (I18nBundle), faction_kind
    // (6-variant: Sect/Order/Clan/Guild/Coalition/Other), roles: Vec<RoleDecl> author-declared per
    // Q3 LOCKED, requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>> validated against
    // actor_ideology_stance at canonical seed, default_relations: HashMap<FactionId, RelationStance>
    // (3-variant Hostile/Neutral/Allied; static V1 per Q5 LOCKED), founder_actor_id (Option),
    // current_head_actor_id (Option), canon_ref }. RoleDecl: { role_id, display_name (I18nBundle),
    // authority_level: u8 (0-100 for ordering) }.
    // Wuxia preset 5 sects (Đông Hải Đạo Cốc / Tây Sơn Phật Tự / Ma Tông / Trung Nguyên Võ Hiệp /
    // Tán Tu Đồng Minh); Modern preset 1-2 factions (police / civilian); Sci-fi 1-2 corporate houses.
    pub canonical_factions: Vec<FactionDecl>,      // see FAC_001 §3.1; sparse — only declared factions

    // FactionMembershipDecl shape per FAC_001 §1: { actor_id, faction_id, role_id, rank_within_role:
    // u16 (numeric V1 per Q4 REVISION), master_actor_id: Option<ActorId> (RESOLVES FF-D7) }.
    // V1 cap=1 validator per Q2 REVISION (each actor has 0-1 membership V1; V1+ relax cap = NO
    // schema migration). Bidirectional sync: faction.current_head_actor_id ↔ membership with role
    // authority_level=100 (sect_master). Master-disciple chain validated (same faction + authority
    // higher + no cycle). Synthetic actors forbidden V1 per Q10 LOCKED.
    pub canonical_faction_memberships: Vec<FactionMembershipDecl>, // see FAC_001 §1; sparse — declared per actor

    // ─── REP_001 Reputation Foundation extensions (added 2026-04-27 DRAFT — Tier 5 Actor Substrate post-FAC_001 priority) ───
    // OPTIONAL V1 — sparse opt-in (empty Vec valid for sandbox / no-canonical-rep reality).
    // Resolves FAC_001 FAC-D7 (per-(actor, faction) reputation projection separate aggregate).
    //
    // 3-layer separation discipline per Q10 LOCKED:
    //   L1 NPC_001 npc_pc_relationship_projection = per-(NPC, PC) personal opinion
    //   L2 RES_001 SocialCurrency::Reputation     = per-actor unbounded global "danh tiếng" sum
    //   L3 REP_001 actor_faction_reputation       = per-(actor, faction) bounded standing per faction
    //
    // ActorFactionReputationDecl shape per REP_001 §3.1: { actor_id, faction_id,
    //   score: i16 (bounded [-1000, +1000] per Q3 LOCKED; clamps; engine-fixed asymmetric thresholds
    //   map to 8-tier ReputationTier display layer: Hated -1000..-501 / Hostile -500..-251 /
    //   Unfriendly -250..-101 / Neutral -100..+100 / Friendly +101..+250 / Honored +251..+500 /
    //   Revered +501..+900 / Exalted +901..+1000), canon_ref: Option<GlossaryEntityId> }.
    //
    // Default Neutral (0) for missing rows V1 per Q4 REVISION (LOCKED); V1+ hybrid (membership-derived
    // via REP-D16) alongside Q6 cascade enrichment.
    // Synthetic actors forbidden V1 per Q9 LOCKED. Cross-reality forbidden V1 per Q8 LOCKED.
    // V1 events: ReputationBorn (canonical seed) + Forge:SetReputation + Forge:ResetReputation only;
    // runtime gameplay delta + cascade + decay all V1+ (REP-D1 + REP-D2 + REP-D3 ship together as
    // V1+ runtime reputation milestone).
    //
    // Wuxia preset ~3 declared rep rows V1 (Du sĩ Đông Hải +250 Friendly / Du sĩ Ma Tông -100 Hostile /
    // Du sĩ Tây Sơn +25 Neutral). Modern preset typically 5-10 rows (per detective/PC × major factions).
    // Sci-fi preset typically 3-5 rows (per Great House standing).
    pub canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>, // see REP_001 §3.1; sparse — declared per (actor, faction)

    // ─── PROG_001 Progression Foundation extensions (added 2026-04-26 DRAFT — 6th V1 foundation feature) ───
    // ALL OPTIONAL V1 — empty default = NO progression in reality (sandbox/freeplay valid V1).
    // (Different from RES_001 which ships engine defaults — PROG schema inherently genre-specific;
    //  modern game ≠ tu tiên ≠ D&D — no universal default.)

    /// Author-declared progression kinds per reality (Q1+Q2+Q3+Q7 LOCKED).
    /// Each ProgressionKindDecl: { kind_id, display_name (I18nBundle), description, progression_type
    /// (Attribute/Skill/Stage), body_or_soul (Body/Soul/Both for xuyên không), curve (Linear/Log/Stage),
    /// cap_rule (SoftCap/HardCap/TierBased/Unbounded), training_rules: Vec<TrainingRuleDecl>,
    /// initial_value, initial_tier, derives_from: Option<DerivationDecl> }.
    /// Validity matrix Q2j: Linear/Log allow SoftCap/HardCap/Unbounded; Stage REQUIRES TierBased.
    pub progression_kinds: Vec<ProgressionKindDecl>,

    /// Per-actor-class default initial values (overrides ProgressionKindDecl.initial_value per class).
    /// E.g., "warrior" actor-class STR=15 default; "scholar" INT=15 default.
    pub progression_class_defaults: HashMap<ActorClassRef, Vec<ClassDefaultDecl>>,

    /// Per-actor override (rare V1; common V1+ for protagonist NPCs).
    pub progression_actor_overrides: HashMap<ActorRef, Vec<ActorOverrideDecl>>,

    /// Strike damage formula per reality (Q7 LOCKED). None V1 = default formula (LLM proposes
    /// 1..=defender_hp/2 with no stat reading). Hybrid combat: LLM proposes damage_amount in PL_005
    /// Strike payload; engine validator computes bounds from offense/defense stat sums; clamps silently.
    /// Full chaos-backend law chain V1+ DF7-equivalent (PROG-D24).
    pub strike_formula: Option<StrikeFormulaDecl>,

    // ─── AIT_001 AI Tier Foundation extensions (added 2026-04-27 DRAFT — architecture-scale; NOT foundation tier) ───
    // ALL OPTIONAL V1 — empty default = no tier-aware NPC simulation (sandbox/freeplay valid V1).
    // Activates PROG_001 §3.1 reserved `tracking_tier: Option<NpcTrackingTier>` field on actor_progression aggregate.

    /// Tier capacity caps per reality (Q2h LOCKED). None = engine defaults Major≤20 / Minor≤100; Untracked unlimited.
    /// AIT-V2 TierCapacityValidator at RealityManifest bootstrap rejects if canonical_actor_decl Tracked exceeds caps.
    pub tier_capacity_caps: Option<TierCapacityCaps>,

    /// Untracked NPC templates per PlaceType (Q4b LOCKED). Empty = NO Untracked generation in those PlaceTypes.
    /// Each UntrackedTemplateDecl: place_type + roles: Vec<UntrackedRoleDecl> with role_id + display_name_template
    /// (I18nBundle with {name} substitution) + actor_class + name_pool + stat_ranges (PROG_001 ProgressionInstance min/max)
    /// + appearance_hints (I18nBundle) + default_dialogue_register (Formal/Casual/Rough/Refined).
    pub untracked_templates: Vec<UntrackedTemplateDecl>,

    /// Per-PlaceType Untracked density (Q8 LOCKED). HashMap<PlaceTypeRef, DensityDecl { count: u8 }>.
    /// V1 max 12 per cell (Q8c cap aligns with tier_roster_caps.max_summary). Empty = engine defaults
    /// (tavern=4 / residence=2 / marketplace=8 / temple=2 / workshop=1 / cave=0 / road=0 / wilderness=0
    /// / official_hall=3 / crossroads=2). Time-of-day variance V1+30d (AIT-D17).
    pub cell_untracked_density: HashMap<PlaceTypeRef, DensityDecl>,

    /// Tier-aware AssemblePrompt budget caps (Q12d LOCKED). None = engine defaults 5 FullPersona +
    /// 8 CondensedPersona + 12 SummaryLine; OverflowFormat::Aggregate ("...and N other patrons").
    pub tier_roster_caps: Option<TierRosterCaps>,

    /// Minor NPC behavior scripts per actor_class (Q7b LOCKED). Empty = Minor NPCs silently fall back
    /// to no canned response (LLM narrator may improvise). Each MinorBehaviorScript: actor_class +
    /// canned_dialogue_templates: Vec<DialogueTemplate> + scheduled_actions: Vec<ScheduledActionDecl>
    /// (V1: StartTraining only; V1+30d AIT-D18 expansion) + reaction_table: Vec<ReactionDecl>.
    pub minor_behavior_scripts: Vec<MinorBehaviorScript>,

    // ─── Future feature extensions ───
}
```

### Extension rules

1. **Additive only** per foundation I14. Same rule as TurnEvent.
2. **Optional fields** for feature-specific declarations (Continuum's three core fields are always required).
3. **Schema version monotonic** — when a field is added, manifest schema bumps; old realities still readable (treat missing fields as `None` / default).
4. **Per-reality opt-in.** A reality MAY omit feature-specific fields; the feature defaults apply (e.g., no `lex_config` → Lex Permissive default; no `mortality_config` → Permadeath default).
5. **Composability.** RealityManifest is composed at book-ingestion time; multiple ingestion-pipeline contributors may add their parts.

### Pending action

Creating `features/01_infrastructure/IF_001_reality_manifest.md` to formally own the envelope is a deferred action. Until that feature ships, this contract IS the truth — features cite "per `_boundaries/02_extension_contracts.md` §2".

---

## §3 — Capability JWT shape

### Owner

DP-K9 owns the base JWT shape (issuer, sub, exp, iat, capabilities, etc.). FORGE-related claims (`forge.role`, `forge.roles`, `forge.roles_version`) are owned by **PLT_001 Charter** §6.3.

### Current shape (subset relevant to Forge)

```json
{
  "iss": "dp-control-plane",
  "sub": "service:world-service",
  "reality_id": "r_<uuid>",
  "session_id": "s_<uuid>",
  "node_id": "<host-id>",
  "capabilities": [
    /* DP-K9 owned per-aggregate read/write capabilities */
  ],
  "produce": ["PlayerTurn", "NPCTurn", "AggregateMutation", "AdminAction"],

  "forge": {
    "roles": { "<reality_id>": "Co-Author | RealityOwner | Admin | ReadOnly" },
    "roles_version": 42
  },

  "exp": 1714000000,
  "iat": 1713999700
}
```

### Extension rules

1. **DP-K9 owns the envelope.** Adding a top-level field requires DP-A* axiom-level change (rare).
2. **`forge.*` namespace** is owned by Charter (PLT_001); other forge-* features (Succession, Mortality) ADD claims under the same namespace via Charter's contract.
3. **`produce: [EVT-T*]` array** is owned by event-model EVT-A4 producer-binding. Feature designs DECLARE which EVT-T* categories their service produces; event-model agent's Phase 2 reconciles the union.

### Borderline with auth-service

The `forge.roles` shape implicitly requires auth-service to know per-user-per-reality role mappings. **Drift watchpoint** (also in CHR-D9 / PLT_001): if auth-service prefers a different model (e.g., per-user platform DB), Charter's design needs alignment. Tracked, not blocking V1.

---

## §4 — `EVT-T8 AdminAction` sub-shapes

### Owner

Top-level event category EVT-T8 owned by **07_event_model agent** (Phase 1 LOCKED). Sub-shapes are FEATURE-DEFINED per the agent's "feature-defined sub-shapes" pattern (mirrors EVT-T1 PlayerTurn sub-shape model).

### Current sub-shapes (2026-04-25)

| Sub-shape | Owner feature |
|---|---|
| `ForgeEdit { editor, action, before, after }` | WA_003 Forge |
| `CharterInvite` | PLT_001 Charter |
| `CharterAccept` | PLT_001 Charter |
| `CharterDecline` | PLT_001 Charter |
| `CharterCancel` | PLT_001 Charter |
| `CharterRevoke` | PLT_001 Charter |
| `CharterResign` | PLT_001 Charter |
| `SuccessionInitiate` | PLT_002 Succession |
| `SuccessionRecipientAccept` | PLT_002 Succession |
| `SuccessionRecipientDecline` | PLT_002 Succession |
| `SuccessionRecipientWithdraw` | PLT_002 Succession |
| `SuccessionAdminApprove` | PLT_002 Succession |
| `SuccessionAdminReject` | PLT_002 Succession |
| `SuccessionOwnerCancel` | PLT_002 Succession |
| `SuccessionFinalize` | PLT_002 Succession |
| `MortalityAdminKill` (provisional) | WA_006 Mortality |

### Extension rules

1. **Feature-defined.** Each feature owns its sub-shape namespace (e.g., Charter owns `Charter*`, Succession owns `Succession*`).
2. **No collision.** Sub-shape discriminators must be globally unique within EVT-T8.
3. **Additive evolution per I14.** Features may add fields to their sub-shapes; cannot modify existing fields without schema bump.

---

## §5 — Future shared schemas

When a new shared schema arises (multiple features need to extend the same struct), open boundary-review:
1. Lock-claim
2. Add a new section to this file
3. Designate envelope owner (typically the FIRST feature that needed it, OR a dedicated infrastructure feature like IF_001)
4. Document extension rules
5. Update `01_feature_ownership_matrix.md`
6. Lock-release

Don't let new shared schemas accumulate without a contract.
