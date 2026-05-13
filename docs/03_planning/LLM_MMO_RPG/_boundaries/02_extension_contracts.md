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
| `actor.*` | ACT_001 Actor Foundation (added 2026-04-27 DRAFT — Tier 5 Actor Substrate; unification refactor replacing NPC_001 R8 anomaly); 8 V1 rule_ids — unknown_actor_id / synthetic_actor_forbidden (per Q4 LOCKED) / cross_reality_mismatch (per Q5 LOCKED universal V2+ Heresy) / kind_specific_field_mismatch (chorus_metadata for non-AI-driven actor V1) / opinion_self_target_forbidden (observer == target enforced per ACT-A5) / duplicate_session_memory (multi-row per (actor, session) pair) / **spawn_cell_unknown** (P2 LOCKED 2026-04-27 — CanonicalActorDecl.spawn_cell ∉ RealityManifest.places) / **glossary_entity_unknown** (P2 LOCKED 2026-04-27 — CanonicalActorDecl.glossary_entity_id ∉ knowledge-service canon); +3 V1+ reservations: bilateral_opinion_unsupported_v1 (V1+ when NPC→NPC + PC→PC events ship per ACT-D2..D4) / ai_control_pc_offline_unsupported_v1 (V1+ AI-controls-PC-offline activation per ACT-D1) / canon_drift_detected (V1+ A6 detector cross-feature integration per ACT-D7).
| `pc.*` | PCS_001 PC Substrate (added 2026-04-27 DRAFT — Tier 5 Actor Substrate post-ACT_001 priority per Q2 LOCKED); 7 V1 rule_ids — unknown_pc_id / synthetic_actor_forbidden (per PCS-A7 LOCKED) / cross_reality_mismatch (per Q8 LOCKED universal V2+ Heresy) / invalid_transmigration_combination (soul/body inconsistency at PcTransmigrationCompleted; renamed from invalid_xuyenkhong_combination per user direction English type names) / user_id_already_bound (one user_id can't bind to multi PCs V1) / mortality_invalid_transition (e.g., Dead → Alive without RespawnComplete trigger; transitions outside V1 active set) / multi_pc_per_reality_forbidden_v1 (per Q9 LOCKED Stage 0 schema validator row count cap=1 V1; V1+ relax via RealityManifest.max_pc_count Optional PCS-D3); +3 V1+ reservations: runtime_login_unsupported_v1 (V1+ PO_001 PCS-D1) / respawn_unsupported_v1 (V1 Stage 0 schema canonical seed validation rejects mortality_config.mode = RespawnAtLocation if V1+ Respawn flow PCS-D2 not active) / body_substitution_unsupported_v1 (V1+ when full xuyên không runtime ships beyond canonical seed PCS-D-N per Q10). V1 user-facing rejects: invalid_transmigration_combination + user_id_already_bound + multi_pc_per_reality_forbidden_v1 (others schema-level canonical seed validation). **1 REFINEMENT** on Q5 (full PcBodyMemory schema with native_skills/motor_skills V1 empty Vec reserved). **1 RENAME** per user direction 2026-04-27: PcXuyenKhongCompleted → PcTransmigrationCompleted; XuyenKhongReason → TransmigrationReason; pc.invalid_xuyenkhong_combination → pc.invalid_transmigration_combination (English type names; Vietnamese term "xuyên không" preserved as parenthetical narrative annotation). **3-layer architectural model post-ACT_001 (PCS-A1)**: L1 identity (ACT_001 actor_core) + L2 kind (ActorId::Pc) + L3 PC-specific (PCS_001 owns); PCS_001 V1 = pure L3 layer post-ACT_001 unification. **RESOLVES**: WA_006 §6 closure pass pc_mortality_state aggregate handoff. i18n: V1 ships I18nBundle from day 1. | V1 user-facing rejects: opinion_self_target_forbidden + unknown_actor_id only (others schema-level canonical seed validation). **2 Q-REVISIONS:** Q3 (NEW C) rename npc_chorus_metadata → actor_chorus_metadata (own under ACT_001; sparse; future-proofs AI-controls-PC-offline V1+) + Q6 user-revised (A) full unify all 3 opportunities NOW (actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory). **RESOLVES:** NPC_001 R8 import anomaly (3 aggregates per-NPC → per-actor unified) + npc_pc_relationship_projection one-directional → bilateral + npc_session_memory NPC-scoped → unified PC pathway V1+. **3-layer architectural model:** L1 Identity (actor_core always present) + L2 Capability/Kind (encoded in ActorId variant; stable) + L3 Control source (dynamic; sparse population). Future-proofs AI-controls-PC-offline V1+ + multi-PC realities V1+ + NPC↔NPC drama V1+. i18n: V1 ships I18nBundle from day 1. |
| `ai_tier.*` | AIT_001 AI Tier Foundation (added 2026-04-27 DRAFT — architecture-scale; NOT foundation tier — 3-tier NPC architecture for billion-NPC scaling); 8 V1 rule_ids — canonical_tier_required / capacity_exceeded / density_exceeded / template_invalid / action_forbidden_for_tier / untracked_cannot_initiate / promotion_target_not_observed / untracked_role_unknown; +4 V1+ reservations: scripted_attack_invalid (AIT-D18) / tier_promotion_rejected (AIT-D1 V1+30d significance threshold) / demotion_forbidden (AIT-D2 V1+30d) / causal_ref_pin_violation (AIT-D6 V1+30d). V1 user-facing rejects: capacity_exceeded + action_forbidden_for_tier + untracked_cannot_initiate + promotion_target_not_observed (others schema-level canonical seed validation). All 12 Qs LOCKED via 4-batch deep-dive 2026-04-26..27 (Q1+Q2 / Q4+Q5+Q11 / Q6+Q12 / Q7+Q8+Q9; Q3 + Q10 implicit). **Quantum-observation NPC model**: PCs eager + Tracked NPCs lazy + Untracked = no aggregate (Schrödinger pattern; activates PROG_001 §3.1 reserved tracking_tier field). 3-tier hierarchy: PC + Major (LLM-driven; cap≤20) + Minor (rule-based scripted; cap≤100) + Untracked (ephemeral; deterministic blake3 NpcId; daily rotation). chaos-backend reference: Stellaris pops vs named characters pattern. PROG-D19 cross-feature alignment with RES_001 NPC eager auto-collect → lazy migration V1+30d. i18n: V1 ships I18nBundle from day 1. |
| `title.*` | TIT_001 Title Foundation (added 2026-04-27 DRAFT — Tier 5 Actor Substrate post-FF_001 + FAC_001 + REP_001; closes the political-rank triangle); 9 V1 rule_ids — declared.unknown / binding.faction_unknown / binding.dynasty_unknown / binding.faction_membership_required (Phase 3 cleanup added 2026-04-27 — actor not in faction at canonical seed/Forge grant) / binding.dynasty_membership_required (Phase 3 cleanup added 2026-04-27 — actor not in FF_001 dynasty lineage) / holding.actor_unknown / holding.multi_hold_violation / holding.exclusive_violation / succession.heir_invalid; +5 V1+ reservations: grant.rep_too_low (V1+ runtime min_reputation_required validator activation alongside REP-D1 runtime delta milestone per TIT-D2) / grant.progression_tier_too_low (V1+ if cultivation-tier gating added; not committed) / lex_axiom.unknown (V1+ requires_title axiom validation via WA_001 closure pass per TIT-D3) / faction_election.invalid_vote (V1+ FactionElect SuccessionRule per TIT-D1 V2 DIPL_001 dependency) / cross_reality_mismatch (V2+ Heresy migration per TIT-D9). V1 user-facing rejects: holding.multi_hold_violation + holding.exclusive_violation + succession.heir_invalid (others schema-level canonical seed validation). All 10 Qs LOCKED via 4-batch deep-dive 2026-04-27 zero revisions: Q1 actor_title_holdings sparse / Q2 Discriminated TitleBinding 3-variant enum (Faction/Dynasty/Standalone) / Q3 3 V1 SuccessionRule (Eldest/Designated/Vacate) + 1 V1+ FactionElect / Q4 V1 schema-reserved min_reputation_required / Q5 per-title MultiHoldPolicy (Exclusive/StackableUnlimited default/StackableMax(N)) / Q6 Both author canonical declaration + Forge admin runtime override / Q7 Immediate cascade WA_006 mortality EVT-T3 / Q8 FAC role grant + LLM narrative_hint + Lex axiom V1 schema-reserved / Q9 per-title VacancySemantic (PersistsNone default/Disabled/Destroyed) / Q10 V1 schema-reserved lex_axiom_unlock_refs. **Schema-stable / activation-deferred V1+ discipline (TIT-A8)**: TIT_001 V1 declares cross-feature gate fields stably (REP min_reputation_required + WA_001 lex_axiom_unlock_refs); activation V1+ via consumer feature milestone (REP-D1 runtime delta + WA_001 closure pass adding 5-companion-fields uniformly: race + ideology + faction + reputation + title). **Per-title author-declared policy (TIT-A5)**: Each TitleDecl carries own MultiHoldPolicy + TitleAuthorityDecl + VacancySemantic. **Cross-aggregate validator TIT-C1**: title-holder death triggers synchronous succession cascade same turn (joins existing C1-C17 cross-aggregate consistency rules from P4 commit). **3-layer separation discipline (TIT-A4)**: TIT_001 actor_title_holdings (per-(actor, title) political/social rank with succession) ≠ FAC_001 actor_faction_membership (per-(actor, faction) operational role) ≠ REP_001 actor_faction_reputation (per-(actor, faction) bounded standing). **RESOLVES**: FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial; runtime gating V1+) + WA_006 sect-leader-death cascade gap (full V1). i18n: V1 ships I18nBundle from day 1. |
| `time_dilation.*` | TDIL_001 Time Dilation Foundation (added 2026-04-27 DRAFT — architecture-scale Tier 5+ Actor Substrate scaling/architecture feature; NOT foundation tier — foundation 6/6 closed at PROG_001; mirror AIT_001 / ACT_001 pattern); 4 V1 rule_ids — rate_out_of_bounds (range V1 [0.001, 1000.0] per TDIL-A1; channel-tier `time_flow_rate` + cell-tier `time_flow_rate_override`) / invalid_initial_clocks (CanonicalActorDecl `initial_clocks` field validation: actor_clock/soul_clock/body_clock all i64 ≥ 0; xuyên không clock-split contract Q11 LOCKED) / mid_turn_channel_cross_forbidden (atomic-per-turn travel TDIL-A5: actor in EXACTLY ONE channel for entire turn; teleport gate V1+ still costs time) / past_clock_edit_forbidden (worldline monotonicity TDIL-A8: Forge edits to past actor_clock/soul_clock/body_clock values FORBIDDEN PERMANENTLY V1+); +6 V1+30d reservations: subjective_rate_invalid (TDIL-D3 per-actor subjective_rate_modifier Option B V1+30d) / dilation_target_invalid (TDIL-D4 time chamber DilationTarget enum BodyOnly/SoulOnly V1+30d) / soul_already_wandering (TDIL-D5 soul wandering V1+30d; soul_clock advances + body_clock paused) / actor_clock_offset_invalid (V1+30d Forge:AdvanceActorClock when activated) / channel_clock_advance_invalid (TDIL-D2 Forge:AdvanceChannelClock V1+30d) / versioned_rate_lookup_failed (V1+ when historical replay supports versioned rates). V1 user-facing rejects: rate_out_of_bounds + mid_turn_channel_cross_forbidden + past_clock_edit_forbidden (invalid_initial_clocks schema-level canonical seed validation). All Q1-Q12 LOCKED via 4-batch deep-dive 2026-04-27 (Q1+Q2+Q3 / Q4+Q5 / Q6+Q7+Q8 / Q9+Q10+Q11+Q12). **4-clock relativity model TDIL-A2**: realm_clock (per channel; existing PL_001 fiction_clock) + actor_clock (proper time τ integrated) + soul_clock (BodyOrSoul::Soul progressions) + body_clock (BodyOrSoul::Body progressions + future aging V2+). **Convention B time_flow_rate semantic TDIL-A1**: proper time per wall time; default 1.0; >1 fast (Dragon Ball chamber); <1 slow (Tây Du Ký heaven 0.0027). **Per-turn O(1) Generator semantic TDIL-A3**: corrects PROG_001/RES_001/AIT_001 day-boundary semantic via mechanical closure-pass; computation = base × elapsed × multiplier (O(1) regardless of magnitude). **Closure-pass cascade**: PROG_001 Q3f day-boundary → turn-boundary; RES_001 Q4 day-boundary → turn-boundary; AIT_001 §7.5 materialization O(1) instead of per-day replay. **PCS_001 §S8 xuyên không clock-split contract**: soul→soul_clock; body→body_clock; actor=0 (twin paradox preserved). **Replay determinism FREE V1 TDIL-A9**: static rates + per-channel turn streams + atomic travel + monotonic clocks. Einstein relativity origin verified physics-correct (concept-notes §3). i18n: V1 ships I18nBundle from day 1. |
| `authoring.*` | GEO_001b CreativeSeed Authoring Flow (added 2026-05-13 DRAFT — write-side sibling of GEO_001; specifies HOW the CreativeSeed value GEO_001 consumes gets produced); **8 V1 rule_ids** — invalid_json (LLM JSON parse fail; transient — retry with error context) / schema_violation (LLM output fails schemars-generated JSON Schema validation; transient — retry) / cap_violation (culture_hints.len ≤ 16 OR canonical_settlements.len ≤ 50 OR position ∈ [0, 1] OR other §3 rules) / content_safety_violation (PII scrubber + §12Y.L5 injection scanner reject on `lore_hooks_per_region.content` or `canonical_settlements.name`) / iteration_cap_exceeded (V1 cap N=10 author-LLM turns) / retry_cap_exceeded (V1 cap N=3 retries per iteration; falls back to author EditManually) / cost_cap_exceeded (S6-D2 inherited per-session cap: $5 paid / $20 premium) / spatial_intent_required (V1+ schema_version=2 validator: each culture_hint + canonical_settlement MUST have at least one of `position_normalized` OR `spatial_preference` Some); +4 V1+ reservations: canon_ref_unresolved (V1+ when knowledge-service ships; KnowledgeServiceExtracted producer validator step 4 fails resolution) / template_version_deprecated (V1+ when world_authoring/v1.tmpl superseded by v2; bumps trigger CI fixture update per S9 governance §12Y.L2) / import_format_unsupported (V1+ when Imported producer activates AzgaarFmgJson V1+ first; later WonderdraftJson + LoreWeaveManifest + Custom) / collaboration_conflict (V2+ multi-author per PLT_001 Charter co-authors). V1 user-facing rejects: cap_violation + iteration_cap_exceeded + retry_cap_exceeded + cost_cap_exceeded + spatial_intent_required (others are transient LLM-retry-resolvable OR schema-level). **Multi-turn iteration loop V1 caps**: iteration_count_max=10 / retry_per_iteration_max=3 / S6 cost cap / 24h session TTL. **No new aggregate**: BFF-held UX state; per-iteration LLM cost in S6 user_cost_ledger; final accepted CreativeSeed durable record via GeographyBorn payload only. **5 producers** (LlmGenerated V1 / AuthorManual V1 / Imported V1+ / KnowledgeServiceExtracted V1+ / Hybrid V1). **SpatialPreference 14-variant enum** introduced V1+ schema_version 2 (additive per I14; LLM-friendlier alternative to raw `(f32, f32)`); CreativeSeed.schema_version 1 → 2 migration path documented. **S9-registered template** at `contracts/prompt/templates/world_authoring/v1.tmpl` with 8-section structure per §12Y.L3 + schema-constrained generation REQUIRED + token budgets per §12Y.L6. i18n: V1 ships I18nBundle from day 1 per RES_001 §2 cross-cutting contract. |
| `geography.*` | GEO_001 World Geometry Foundation (added 2026-05-13 DRAFT — 7th foundation feature; procedural geographic substrate beneath MAP_001 visual layer; fix cycle 2026-05-13 added 3 V1 rule_ids via /review-impl); **13 V1 rule_ids** — duplicate_world_geometry / invalid_channel_tier (per MAP-2 ChannelTier::Continent per HIGH-2 fix) / cell_count_out_of_bounds (cells.len ∈ [1024, 16384]) / invalid_neighbor_degree (Voronoi cells have 3-12 neighbors) / parallel_array_length_mismatch (biomes/climate_zones/river_flux/is_coast parallel to cells) / sea_level_out_of_bounds (threshold ∈ [8192, 57344]) / delta_order_violation (prev_delta_id stale; parallel to TDIL-A8 worldline-monotonicity discipline) / creative_seed_immutable_v1 (post-bootstrap mutation requires V1+ T6 LLM proposal + T8 Forge approval via GEO-D12) / layer_activation_deferred_v1 (writes to political/settlement/route/culture/resource layers reject V1; activate via V1+ POL_001/SET_001/ROUTE_001/V2+ resource generator) / creative_seed_required_when_seeded (RealityManifest geography_seed declared without creative_seed) / **biome_override_water_transition_v1 (HIGH-1 fix — V1 admits only land-↔-land SetBiomeOverride; water↔land V1+ when biome+water-network re-derivation lands per GEO-D13)** / **pipeline_version_mismatch (MED-4 fix — promoted from V1+ reservation to V1 active; world_geometry pinned to its generator_pipeline_version at GeographyBorn; mid-life upgrades FORBIDDEN; new realities adopt latest pipeline_version)** / **cell_id_index_violation (LOW-1 fix — `cells[i].id == GeoCellId(i)` invariant enforced at GeographyBorn + every delta apply touching cells)**; +3 V1+ reservations: cross_reality_reference (V2+ Heresy axis) / delta_kind_v1plus_inactive (V1+ DeltaKind extensions: SetResourceOverride V2+ per MED-6 fix + MergeProvinces/SplitProvince/TransferProvinceToState/SetCultureRegion reject at V1) / resource_layer_activation_pending (V2+ resource distribution generator placeholder per GEO-D10). **Fix cycle changes**: 7 architectural improvements applied via /review-impl 2026-05-13 (HIGH-1 SetBiomeOverride coherence + HIGH-2 ChannelTier ref + HIGH-3 delta_id namespace + MED-1 Forge:EditGeographyDelta registered in §4 EVT-T8 sub-shapes + MED-2 GeographyForkInherited reclassified EVT-T8→EVT-T4 System + MED-3 stage 4 sub-stages 4a/4b/4c for Lake-vs-Ocean connected-components + MED-4 pipeline_version pinned + MED-5 schema_version added + MED-6 SetResourceOverride V1→V1+ + LOW-1 GeoCellId==index invariant + LOW-2 applied_at_fiction_time dropped + LOW-3 RegionalLoreHook/NamingStyleDecl/CanonicalSettlementDecl declared + Settlement.canon_ref added). V1 user-facing rejects: delta_order_violation + creative_seed_immutable_v1 + layer_activation_deferred_v1 + creative_seed_required_when_seeded (others schema-level canonical seed validation). All 7 sub-decisions D1-D7 LOCKED via single deep-dive 2026-05-13 (D1 ChannelScoped continent / D2 single aggregate layered / D3 deterministic-base+delta-overlay / D4 single Voronoi mesh water-tags / D5 cells AND provinces two-tier / D6 explicit FK channel↔map / D7 inherit by reference deltas don't cascade). **8-stage generation pipeline** (V1 implements 1-4 substantively: Voronoi + heightmap + climate + biome+river; V1+ schema-reserves 5-8: political POL_001 / settlement SET_001 / route ROUTE_001 / culture spread). **CreativeSeed LLM-supplied direction** (12 WorldArchetype + 5 WorldScale + hemisphere + coastline + culture_hints + canonical_settlements + naming_styles); feeds procgen as constraints NOT post-hoc decoration. **Deterministic-base + delta-overlay editability** (replay = base + deltas in order; genuinely novel work — no Azgaar-style tool does this V1). **Single Voronoi mesh sea zone tagging** (water cells via Biome::Ocean/Lake/River; V2+ Paradox-style separate sea_zones+straits per GEO-D6 if naval gameplay needs explicit straits). **Multiverse snapshot fork inheritance** (deltas-at-fork-point copied; new child deltas stay local per MV6 + 4-layer canon L3-scope discipline). **Composition with foundation siblings** (MAP_001 V1+ position auto-derivation GEO-D5; PF_001 V1+ procedural place generation PF-D7; CSC_001 V1+ biome→skeleton selection; RES_001 V2+ resource distribution generator GEO-D10; PROG_001 V2+ cultivation-realm biome-conditioned training modifiers via GEO-D7 MagicalAnomaly ClimateZone extension). Algorithmic baseline: Patel dual-mesh (Apache 2.0) + O'Leary erosion (MIT) + Azgaar pipeline (MIT) per 2026-05-13 world-map landscape survey. **Strategy substrate readiness**: V1 schema reserves all strategy layers (provinces/states/settlements/routes/resources); V1+ POL/SET/ROUTE features activate via additive schema discipline; V2+ STRAT_001 consumes locked layers as read-only inputs. RealityManifest extension `continent_geometries: Vec<ContinentGeometryDecl>` OPTIONAL V1 (per §2 contract — single-cell SPIKE_01 realities omit; multi-cell realities REQUIRE per continent channel). i18n: V1 ships I18nBundle from day 1 per RES_001 §2 cross-cutting contract. |

| `onboarding.*` | PO_001 Player Onboarding (added 2026-04-27 DRAFT — first user-visible feature post-foundation closure; FE-first design via wireframes Phase 0 commits 19855a5b + 4c4fd6d7); 7 V1 rule_ids — reality_unauthorized (user lacks access to reality_id) / mode_unsupported (mode ∉ onboarding_config.modes_enabled) / draft_invalid (Mode B/C draft fails per-feature schema validation) / pc_cap_exceeded (cap=1 V1 per PCS-A9; relaxed via PCS-D3 V1+) / canonical_pc_unavailable (Mode A canonical_pc already bound to another user) / spawn_cell_unauthorized (spawn_cell ∉ reality.places) / user_already_has_pc (single-reality V1 cap=1); +5 V1+ reservations: draft_resume_failed (V1+30d PO-D3 auto-save resume) / oauth_provider_invalid (V1+ PO-D1 OAuth) / ai_assistant_unavailable (V1+ chat-service down fallback) / tutorial_step_invalid (V1+30d PO-D10 richer tutorial) / cross_reality_migration_unsupported_v1 (V2+ PO-D6 character export/import via Heresy). V1 user-facing rejects: pc_cap_exceeded + canonical_pc_unavailable + user_already_has_pc + draft_invalid (others schema-level canonical seed validation). All 10 Qs LOCKED via 4-batch deep-dive 2026-04-27 zero revisions: Q1 3 modes V1 (Canonical+Custom+XuyenKhong) / Q2 3-level Custom PC (Basic+Advanced+AI Assistant) / Q3 AI Assistant V1 active (chat-service+knowledge-service) / Q4 email+password V1; OAuth V1+ / Q5 cap=1 V1 per PCS-A9 / Q6 locked-in per session V1 / Q7 all-or-nothing V1; auto-save V1+30d / Q8 desktop-only V1; mobile V1+30d / Q9 immediate spawn cell drop-in / Q10 inline tooltips minimal V1; richer tutorial V1+30d. **3-mode onboarding architecture** (PO-A2 LOCKED): Mode A Canonical (BG3 Origin Character pattern; pick from canonical_pcs) + Mode B Custom (8-step Basic Wizard + Advanced Settings ~46 V1 fields + AI Character Assistant 3-level UX progression per PO-A3) + Mode C XuyenKhong (Disco Elysium amnesia + wuxia transmigration; uses PCS_001 PcBodyMemory). **AI Character Assistant V1 active** (PO-A4): chat-service + LiteLLM + knowledge-service constraint awareness; reality-aware (skips V1+ deferred fields); 6 quick actions. **PC creation cascade orchestration** (PO-A5 + PO-C1): Forge:CompleteOnboarding triggers synchronous 14-feature cascade same turn (PCS_001 + ACT_001 + EF_001 + IDF_001..005 + FF_001 + FAC_001 + REP_001 + TIT_001 + PROG_001 + RES_001 + TDIL_001 + SR11). **Schema-stable / activation-deferred V1+ discipline (PO-A8)**: actor_user_session.onboarding_draft + 2 EVT-T8 sub-shapes (Forge:CreateOnboardingDraft + Forge:UpdateOnboardingDraft) schema-reserved V1; activation V1+30d per PO-D3 (auto-save). **RESOLVES**: PCS-D1 (V1+ runtime login flow PC creation; full V1) + PCS-D10 (V1+ PO_001 Player Onboarding integration; full V1). i18n: V1 ships I18nBundle from day 1. |
| `session.*` | DF05_001 Session/Group Chat Foundation (added 2026-04-27 DRAFT — V1-blocking biggest unknown RESOLVED; multi-session-per-cell sparse architecture per user direction billion-NPC AIT scaling concern + real-life conversation parallel); 14 V1 rule_ids (Phase 3 cleanup added participant_already_joined defensive write-time validator) — duplicate_session_id / participant_cap_exceeded (DF5-A8 8-cap inclusive PC anchor) / cell_session_overload (DF5-A8 50 active sessions per cell) / actor_not_eligible_untracked (DF5-A6 + AIT-A8 capability matrix Untracked exclusion) / actor_busy_in_other_session (DF5-A5 one Active session per actor) / participant_already_joined (composite key duplicate write defensive) / npc_refused (Q4-D1 Hated/Hostile reputation tier reject; Q4-D2 personal opinion overrides faction; Q4-D3 LLM-flavored refusal + template fallback) / invalid_state_transition (DF5-A7 Closed terminal — Closed → Active forbidden) / empty_participant_list_invalid (defensive 0-participant non-monologue mode) / anchor_must_be_pc (DF5-A4 PC anchor invariant — non-PC anchor reject via cross-validator with ACT_001) / cross_channel_participation_forbidden (DF5-A1 same-channel constraint per TDIL-A5) / closed_session_immutable (DF5-A7 — participation write attempt after Closed transition; Q11-D2 post-close direct edit forbidden) / distill_cache_version_mismatch (Q12-D2 cache invalidation — prompt_template_version mismatch OR llm_model_id deprecated) / cell_session_creation_rate_limited (anti-spam — PC creates >5 sessions in <1min wall-clock); +5 V1+ reservations: cross_reality_session (V2+ if multi-reality session — currently impossible per TDIL-A5 atomic-channel) / npc_only_session_disallowed (V1 hard-reject; V2+ DF1 ambient may allow per DF5-D9) / session_resume_disallowed (V1 hard; V3+ resume feature per DF5-D10) / summary_corruption_detected (V1+30d transcript verify SalienceTranscript backend per DF5-D43 V2+) / distill_quota_exceeded (V1+30d cost cap per usage-billing-service). V1 user-facing rejects: participant_cap_exceeded + cell_session_overload + actor_not_eligible_untracked + actor_busy_in_other_session + npc_refused (others schema-level canonical seed validation OR defensive). All 12 Qs LOCKED via 4-batch deep-dive 2026-04-27 zero revisions: Q1 Both CLI+GUI / Q2 0-NPC monologue allow + skip distill turn<3 / Q3 8-cap inclusive PC anchor / Q4 reputation-gated consent / Q5 single distill template + 3-5 facts JSON Schema 3-retry + I18nBundle vi+en + LLM self-scores salience + placeholder fallback / Q6 unlimited V1 retention + GDPR per-actor erasure / Q7 cross-session memory bleed YES top-K=10-20 salience / Q8 ~3K context per-tier (Free 2K/Paid 3K/Premium 5K) per-actor budget + soft cap priority drop / Q9 TDIL clocks orthogonal / Q10 30s wall-clock disconnect grace + presence field / Q11 pre-close edits all OK + post-close Regen+Purge only / Q12 EVT-T3 cache full JSON + replay from event_log canonical + provider_id field. **Section 16 SDK Architecture LOCKED** — `contracts/api/session/v1/` versioned contract + `services/session-service/` swappable backends (LruDistill V1 / SalienceTranscript V1+30d / KnowledgeServiceBridge V2+) + 5 migration patterns (shadow-read + dual-write + versioned DTO tolerant readers + capability-gated graceful degradation + contract test suite firewall) + ~30 contract test scenarios. **Multi-session-per-cell sparse architecture**: 95%+ cell actors AMBIENT (zero LLM cost); M concurrent sessions per cell (soft cap 50 V1 per DF5-A8); each session = explicit social act not spatial co-location. **Per-actor POV memory distill on close (DF5-A9)**: LLM × N participants on Closed transition; cached in EVT-T3 payload per Q12-D1 LOCKED full JSON for replay-determinism per Q12-D3 (replay reads cache; never re-LLM-calls). **No cross-session leak (DF5-A10)**: Session A's content NOT readable by Session B participants. **RESOLVES**: PC-D1 (multi-PC parties redirected V2 multi-PC join via DF5-D1) + PC-D2 (PvP V2 deferred via DF5-D3) + PC-D3 (no global chat per multi-session sparse model) + B4 PARTIAL (multi-NPC turn arbitration via NPC_002 Chorus). i18n: V1 ships I18nBundle from day 1 per Q5-D5. |

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

    // ─── ACT_001 Actor Foundation extensions (added 2026-04-27 DRAFT — Tier 5 Actor Substrate; unification refactor) ───
    // CanonicalActorDecl OWNERSHIP TRANSFERS from PL_001+NPC_001 → ACT_001 2026-04-27 unification.
    // Existing CanonicalActorDecl fields preserved; chorus_metadata extension ADDITIVE (per I14).
    //
    // CanonicalActorDecl shape post-unify (P2 LOCKED 2026-04-27 — spawn_cell + glossary_entity_id ADD):
    // pub struct CanonicalActorDecl {
    //     pub actor_id: ActorId,                   // EF_001 §5.1 sibling pattern (PC + NPC; Synthetic excluded V1)
    //     pub kind: ActorKind,                     // PC / NPC (Synthetic forbidden V1 per ACT-A7)
    //
    //     // ACT_001 P2 ADDITIVE (NEW 2026-04-27 — REQUIRED V1 — closure-pass-extension):
    //     pub spawn_cell: ChannelId,               // Initial cell location (cell-tier channel from
    //                                              // RealityManifest.places); cross-validated at canonical
    //                                              // seed; populates ActorCore.current_region_id at bootstrap.
    //                                              // Reject `actor.spawn_cell_unknown` if missing from places.
    //                                              // EF_001 EntityBorn cell_id sourced from this field.
    //     pub glossary_entity_id: GlossaryEntityId, // Actor's primary glossary entry (DISTINCT from
    //                                              // core_beliefs_ref which references canon belief set);
    //                                              // populates ActorCore.glossary_entity_id at bootstrap.
    //                                              // Reject `actor.glossary_entity_unknown` if missing from
    //                                              // knowledge-service canon.
    //
    //     pub canonical_traits: CanonicalTraits,   // name + role + voice register + physical (immutable)
    //     pub flexible_state_init: FlexibleState,  // initial mutable state (typed standard fields B2 LOCKED)
    //     pub knowledge_tags: Vec<KnowledgeTag>,   // closed-set strings
    //     pub voice_register: VoiceRegister,       // TerseFirstPerson / Novel3rdPerson / Mixed
    //     pub core_beliefs_ref: Option<GlossaryEntityId>,  // canon belief ref (may differ from glossary_entity_id)
    //     pub mood_init: ActorMood,                // initial multi-axis emotional state (B1 LOCKED — 4-axis u8 [0, 100])
    //
    //     // ACT_001 ADDITIVE (NEW 2026-04-27 unification):
    //     // chorus_metadata: Some for NPCs (always AI-driven V1); None for PCs (always User-driven V1).
    //     // V1+ AI-controls-PC-offline activation: PCs may have chorus_metadata Some when offline.
    //     pub chorus_metadata: Option<ChorusMetadataDecl>,
    // }
    //
    // ChorusMetadataDecl shape (Q3 LOCKED REVISION; renamed from NpcChorusMetadataDecl; kind-agnostic):
    // pub struct ChorusMetadataDecl {
    //     pub greeting_obligation: GreetingObligation,
    //     pub priority_tier_hint: PriorityTierHint,
    //     pub desires: Vec<DesireDecl>,            // renamed from NpcDesireDecl (NPC_003 ownership transfer)
    // }
    //
    // V1: NPCs declared with chorus_metadata=Some; PCs declared with chorus_metadata=None.
    // V1+: AI-controls-PC-offline activation (ACT-D1) populates chorus_metadata for offline PCs at runtime
    //      via Forge:EditChorusMetadata (NOT via canonical seed re-bootstrap).
    pub canonical_actors: Vec<CanonicalActorDecl>, // see ACT_001 §11; OWNERSHIP TRANSFERRED to ACT_001 2026-04-27

    // ─── PCS_001 PC Substrate extensions (added 2026-04-27 DRAFT — Tier 5 Actor Substrate post-ACT_001) ───
    // CanonicalActorDecl PCS_001 ADDITIVE FIELDS (REQUIRED for kind=Pc V1; sparse PC-only):
    //
    // CanonicalActorDecl shape post-PCS_001 (ACT_001-owned envelope; PCS_001 additive fields):
    // pub struct CanonicalActorDecl {
    //     // ... ACT_001 fields (per §2 ACT_001 section above) ...
    //
    //     // PCS_001 P2 ADDITIVE 2026-04-27 — REQUIRED V1 for kind=Pc:
    //     pub body_memory_init: Option<PcBodyMemory>,  // Some required for kind=Pc V1; native PC fallback if None
    //                                                  // PcBodyMemory: SoulLayer + BodyLayer + LeakagePolicy 4-variant
    //                                                  // (per Q5 REFINEMENT + Q6 LOCKED 2026-04-27)
    //     pub user_id_init: Option<UserId>,            // V1 typically None at canonical seed
    //                                                  // Bound via Forge:BindPcUser V1 OR runtime login V1+ via PO_001
    //                                                  // (per Q3 LOCKED canonical seed + Forge admin V1; runtime V1+ PCS-D1)
    // }
    //
    // PcBodyMemory shape (Q5 REFINEMENT + Q6 LOCKED):
    // pub struct PcBodyMemory {
    //     pub soul: SoulLayer,                          // origin_world_ref Option<GlossaryEntityId> per Q8 LOCKED
    //                                                   // + knowledge_tags Vec<KnowledgeTag>
    //                                                   // + native_skills Vec<ProgressionKindId> V1 empty Vec reserved
    //                                                   // + native_language LanguageId
    //     pub body: BodyLayer,                          // host_body_ref + knowledge_tags + motor_skills V1 empty Vec
    //                                                   // + native_language
    //     pub leakage_policy: LeakagePolicy,            // 4-variant per Q6 LOCKED:
    //                                                   //   NoLeakage / SoulPrimary { body_blurts_threshold: f32 }
    //                                                   //   / BodyPrimary { soul_slips_threshold: f32 } / Balanced
    // }
    //
    // V1 cap=1 PC per reality enforced via Stage 0 schema validator counting pc_user_binding rows
    // (per Q9 LOCKED PCS-A9); V1+ relax via NEW RealityManifest field below (PCS-D3):
    //
    // V1+ RealityManifest extension (PCS-D3 deferred):
    // pub max_pc_count: Option<u8>,                     // None = default 1; Some(N) = up to N PCs (charter coauthors V1+)

    // ─── TIT_001 Title Foundation extensions (added 2026-04-27 DRAFT — Tier 5 Actor Substrate post-FF_001 + FAC_001 + REP_001 priority; closes the political-rank triangle) ───
    // BOTH OPTIONAL V1 — empty Vec valid for sandbox/freeplay realities (no titles).
    //
    // 3-layer separation discipline post-REP_001 alignment per TIT-A4 LOCKED:
    //   L1 FAC_001 actor_faction_membership   = per-(actor, faction) operational role (disciple / elder / master)
    //   L2 REP_001 actor_faction_reputation   = per-(actor, faction) bounded standing (8-tier ReputationTier)
    //   L3 TIT_001 actor_title_holdings       = per-(actor, title) political/social rank with succession rules
    //
    // TitleDecl shape per TIT_001 §2.1: { title_id, display_name (I18nBundle), description (I18nBundle),
    //   binding: TitleBinding (3-variant: Faction(FactionId) / Dynasty(DynastyId) / Standalone per Q2 B LOCKED),
    //   succession_rule: SuccessionRule (3 V1: Eldest FF_001 traversal / Designated canonical+Forge / Vacate;
    //     V1+ FactionElect DIPL_001 V2+ dependency per Q3 A LOCKED),
    //   min_reputation_required: Option<MinRepGate> (V1 schema-reserved per Q4 C LOCKED — declarations stored;
    //     runtime validator V1+ alongside REP-D1 runtime delta milestone per TIT-D2),
    //   authority_decl: TitleAuthorityDecl ({ faction_role_grant: Option<FactionRoleGrant> V1 active —
    //     atomic FAC_001 role grant on title-grant via 3-write atomic pattern; narrative_hint: I18nBundle
    //     V1 active — LLM persona briefing + dialogue context; lex_axiom_unlock_refs: Vec<AxiomDeclRef>
    //     V1 schema-reserved per Q10 B LOCKED — validator V1+ via WA_001 closure pass adding 5-companion-fields
    //     uniformly: race + ideology + faction + reputation + title per TIT-D3 }),
    //   multi_hold_policy: MultiHoldPolicy (per-title author-declared per Q5 C LOCKED; 3-variant: Exclusive /
    //     StackableUnlimited default / StackableMax(N) CK3-style cap),
    //   vacancy_semantic: VacancySemantic (per-title author-declared per Q9 D LOCKED; 3-variant: PersistsNone
    //     default — title persists with no holder revivable / Disabled — flagged disabled Forge re-grant required /
    //     Destroyed — RealityManifest entry removed for fallen empires)
    // }.
    //
    // TitleHoldingDecl shape per TIT_001 §2.2: { actor_id, title_id (MUST be in canonical_titles),
    //   designated_heir: Option<ActorId> (Q6 C LOCKED canonical declaration; Some only when title_decl.succession_rule
    //   == Designated; None for Eldest FF_001 traversal / Vacate),
    //   initial_grant_reason: I18nBundle }.
    //
    // Per-title author-declared policy discipline (TIT-A5): each TitleDecl carries own MultiHoldPolicy +
    // TitleAuthorityDecl + VacancySemantic; covers wuxia + D&D + modern + sci-fi reality use cases.
    //
    // Synthetic actors forbidden V1 per TIT-A6. Cross-reality strict V1 per TIT-A7 (V2+ Heresy via TIT-D9).
    //
    // V1 events per Q6 C LOCKED + Q7 A LOCKED:
    //   - TitleGranted EVT-T4 (canonical seed + Forge admin runtime + SuccessionCascade V1 active)
    //   - Forge:GrantTitle / Forge:RevokeTitle / Forge:DesignateHeir EVT-T8 admin sub-shapes (3 V1)
    //   - TitleSuccessionTriggered EVT-T3 (sparse on cross-aggregate cascade triggered by WA_006 mortality)
    //   - TitleSuccessionCompleted EVT-T1 narrative milestone for LLM (mirrors PcTransmigrationCompleted pattern)
    //
    // Cross-aggregate validator TIT-C1 per Q7 A LOCKED: title-holder death (WA_006 mortality EVT-T3 actor_dies)
    // triggers synchronous succession cascade same turn (joins existing C1-C17 cross-aggregate consistency rules
    // from P4 commit; new TIT-C1 + TIT-C2..C8 schema validators).
    //
    // Wuxia preset typical V1: ~12 declared TitleDecls (5 sect-masters + 5 elders + 1 emperor + 1 crown prince) +
    // ~5-15 declared TitleHoldingDecls. Modern preset typical: ~8 titles (president + senators + cartel bosses +
    // judges). D&D preset typical: ~15 titles (king + dukes + counts + lords + knights + archmage + high priest).
    //
    // RESOLVES: FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial; runtime gating V1+) +
    // WA_006 sect-leader-death cascade gap (full V1).
    pub canonical_titles: Vec<TitleDecl>,                  // see TIT_001 §4.1; OPTIONAL V1 (empty Vec valid for sandbox)
    pub canonical_title_holdings: Vec<TitleHoldingDecl>,   // see TIT_001 §4.1; OPTIONAL V1 (initial holdings; Forge admin grants V1 active)

    // ─── DF05_001 Session/Group Chat Foundation extension (added 2026-04-27 DRAFT — V1-blocking biggest unknown RESOLVED) ───
    // OPTIONAL V1 — empty Vec default = no canonical sessions; sessions created entirely at runtime by PC `/chat`.
    // Authors opt-in for set-piece dramatic moments where session must exist at reality bootstrap (e.g., wuxia
    // canonical reunion scene where Master Lin teaches PC at chapter 1 start).
    //
    // CanonicalSessionDecl shape per DF05_001 §17:
    //   { session_id: SessionId (pre-deterministic for replay),
    //     channel_id: ChannelId (anchor cell),
    //     anchor_pc_template: ActorTemplateRef (PC role at session start),
    //     initial_npc_participants: Vec<ActorRef> (pre-joined NPCs),
    //     bootstrap_facts: Vec<MemoryFactSeed> (pre-seeded actor_session_memory) }
    //
    // V1 default: empty `canonical_sessions: []`. Authors opt-in for set-piece dramatic moments.
    // Wuxia preset typical V1: 0-2 declared sessions (e.g., master-disciple opening scene; old grudges flashback).
    // Modern/sci-fi/D&D preset typical: empty (sessions purely runtime).
    pub canonical_sessions: Vec<CanonicalSessionDecl>,     // see DF05_001 §17; OPTIONAL V1 (empty Vec valid for sandbox)

    // ─── PO_001 Player Onboarding extensions (added 2026-04-27 DRAFT — first user-visible feature post-foundation closure; FE-first design via wireframes Phase 0 commits 19855a5b + 4c4fd6d7) ───
    // BOTH OPTIONAL V1 — engine defaults apply when omitted.
    //
    // 3-mode onboarding architecture per PO-A2 LOCKED:
    //   Mode A Canonical PC — pick from canonical_pcs ref list (BG3 Origin Character pattern)
    //   Mode B Custom PC    — 8-step Basic Wizard + Advanced Settings (~46 V1 fields) + AI Character Assistant (3-level UX progression per PO-A3)
    //   Mode C XuyenKhong   — Disco Elysium amnesia + wuxia transmigration (uses PCS_001 PcBodyMemory SoulLayer + BodyLayer + LeakagePolicy 4-variant)
    //
    // OnboardingConfigDecl shape per PO_001 §2.1: { modes_enabled: Vec<OnboardingMode> (3-variant subset),
    //   canonical_pcs: Vec<ActorRef> (Mode A picker source; subset of canonical_actors[kind=Pc]),
    //   ai_assistant_enabled: bool (per-reality opt-in; default true V1 per PO-A4 LOCKED chat-service + knowledge-service),
    //   default_spawn_cell: ChannelId (fallback if user skips spawn cell selection per Q9 A LOCKED),
    //   onboarding_skin: Option<I18nBundle> (V1+ PO-D11 reality-themed skin variant),
    //   tutorial_steps: Vec<TutorialStepDecl> (V1+ PO-D10 richer tutorial schema-reserved) }.
    //
    // Engine default (when onboarding_config: None):
    //   modes_enabled = [Custom] (only Mode B; Canonical + XuyenKhong require explicit declaration)
    //   canonical_pcs = []
    //   ai_assistant_enabled = true
    //   default_spawn_cell = first cell-tier ChannelId in places (must exist)
    //
    // Wuxia preset typical V1: { modes_enabled: [Canonical, Custom, XuyenKhong], canonical_pcs: [5 actor refs], ai_assistant_enabled: true }
    // Modern preset typical: { modes_enabled: [Canonical, Custom], canonical_pcs: [4 actor refs], ai_assistant_enabled: true }
    // Sandbox/freeplay preset: None (engine defaults; Mode B only)
    //
    // canonical_pcs: Vec<ActorRef> validated subset of canonical_actors[kind=Pc] at canonical seed bootstrap
    // (cross-aggregate consistency rule PO-C2 — registered in 03_validator_pipeline_slots.md).
    // Empty Vec valid V1 = Mode A unavailable for this reality.
    //
    // V1 events per Q9 + Q7 LOCKED:
    //   - Forge:CompleteOnboarding EVT-T8 V1 ACTIVE (orchestrates 14-feature cascade per PO-A5 + PO-C1)
    //   - Forge:CreateOnboardingDraft + Forge:UpdateOnboardingDraft EVT-T8 V1 schema-reserved; V1+30d active per PO-D3 (auto-save)
    //   - OnboardingCompleted EVT-T1 narrative milestone for LLM (V1 active)
    //   - OnboardingDraftUpdated EVT-T3 V1 schema-reserved; V1+30d active per PO-D3
    //
    // Cross-aggregate validator PO-C1 per Q9 A LOCKED: Forge:CompleteOnboarding triggers synchronous cascade across
    // 14 features same turn (joins existing C1-C29 cross-aggregate consistency rules from prior commits;
    // new PO-C1 + PO-C2..C6 schema validators).
    //
    // Schema-stable / activation-deferred V1+ discipline (PO-A8): actor_user_session.onboarding_draft +
    // 2 EVT-T8 sub-shapes schema-reserved V1; activation V1+30d per PO-D3.
    //
    // RESOLVES: PCS-D1 (V1+ runtime login flow PC creation; full V1) + PCS-D10 (V1+ PO_001 Player Onboarding
    // integration; full V1).
    pub onboarding_config: Option<OnboardingConfigDecl>,    // see PO_001 §4.1; OPTIONAL V1 (None = engine default)
    pub canonical_pcs: Vec<ActorRef>,                       // see PO_001 §4.1; subset of canonical_actors[kind=Pc]; empty Vec valid V1

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

    // ─── TDIL_001 Time Dilation Foundation extensions (added 2026-04-27 DRAFT — architecture-scale; NOT foundation tier) ───
    // INLINE field additions on existing extension structs (NO new top-level RealityManifest field):
    //
    // 1. MAP_001 MapLayoutDecl gains `time_flow_rate: f32` per TDIL-1 (channel-level Convention B
    //    semantic per TDIL-A1). Default 1.0 (engine-canonical real-time); >1 fast (Dragon Ball
    //    chamber 365× wall time); <1 slow (Tây Du Ký heaven 0.0027× wall time). Range V1 [0.001, 1000.0]
    //    enforced by TDIL-V2 RateBoundsValidator. REQUIRED V1 (every channel declares; default 1.0
    //    permitted via author elision). Cell-tier MapLayoutDecl carries time_flow_rate=1.0 (engine
    //    fallback); cell-level override goes through PF_001 PlaceDecl below per §3.2-3.3 layering.
    //
    // 2. PF_001 PlaceDecl gains `time_flow_rate_override: Option<f32>` per TDIL-2 (cell-level REPLACE
    //    semantic per TDIL_001 §3.3). None = inherit from parent_channel.time_flow_rate; Some(rate)
    //    = REPLACE parent rate (NOT multiply — Dragon Ball chamber 365× is absolute, not 365× × parent).
    //    Range V1 [0.001, 1000.0] same as channel-tier. OPTIONAL V1 (None default; cell respects parent).
    //
    // 3. ACT_001 CanonicalActorDecl gains `initial_clocks: Option<InitialClocksDecl>` per TDIL-5
    //    (V1 OPTIONAL author override; default None = engine starts all 3 clocks at fiction_clock).
    //    InitialClocksDecl shape per TDIL_001 §4.3:
    //    pub struct InitialClocksDecl {
    //        pub actor_clock: i64,    // proper time τ at canonical seed; default = starting_fiction_time
    //        pub soul_clock: i64,     // soul age at canonical seed; default = starting_fiction_time
    //        pub body_clock: i64,     // body age at canonical seed; default = starting_fiction_time
    //    }
    //    Validated by TDIL-V3 InitialClocksValidator: all 3 ≥ 0; xuyên không clock-split semantic
    //    Q11 LOCKED (PCS_001 §S8 mechanic creates new PC with actor_clock=0 + soul_clock=source_a.soul_clock
    //    + body_clock=source_b.body_clock). Twin paradox preserved.
    //
    // NEW T2/Reality aggregate `actor_clocks` (NOT a RealityManifest field): owner=Actor; ALWAYS-PRESENT V1
    // post-creation (mirror ACT_001 actor_core ALWAYS-PRESENT pattern); seeded by ActorBorn from
    // canonical_actors[i].initial_clocks (or engine default = starting_fiction_time). Per TDIL_001 §4.1.
    //
    // EVT-T8 Forge sub-shape (V1+30d): Forge:EditChannelTimeFlowRate (TDIL-D1; runtime channel rate
    // adjustment via Forge); Forge:AdvanceChannelClock (TDIL-D2 V1+30d).
    // Forge edits to past actor_clock/soul_clock/body_clock FORBIDDEN PERMANENTLY V1+ per TDIL-A8.

    // ─── GEO_001 World Geometry Foundation extension (added 2026-05-13 DRAFT) ───────
    pub continent_geometries: Vec<ContinentGeometryDecl>,   // OPTIONAL V1 — empty Vec = no procgen geography (single-cell SPIKE_01 realities)
    // ─── GEO_001b CreativeSeed Authoring Flow extension (added 2026-05-13 write-side cycle) ───────
    pub authoring_metadata: Option<AuthoringMetadata>,      // OPTIONAL V1; absence implies legacy / no metadata captured
    //
    // AuthoringMetadata {
    //   producer: AuthoringProducer (5-variant — LlmGenerated{template_ref, knowledge_grounding} V1 /
    //             AuthorManual{ui_form_version} V1 / Imported{source_format, source_ref} V1+ /
    //             KnowledgeServiceExtracted{book_id, extraction_template_ref} V1+ /
    //             Hybrid{primary: Box<AuthoringProducer>, author_edits_applied: u32} V1),
    //   total_llm_cost_usd: Decimal (0 for non-LLM producers),
    //   total_llm_calls: u32 (0 for non-LLM producers),
    //   iteration_count: u32 (how many author-feedback turns),
    //   author_user_id: UserId,
    //   authoring_template_version: Option<u32> (S9 template version used; Some for LlmGenerated),
    //   knowledge_grounding_book_id: Option<BookId> (V1+ when knowledge-service ships),
    //   authoring_started_at: WallClock,
    //   authoring_completed_at: WallClock,
    // }
    //
    // Per-iteration LLM cost recorded in S6 user_cost_ledger as it accrues; total_llm_cost_usd here is the
    // sum at acceptance time. Audit join: S6 user_cost_ledger.reality_id = this reality's id during the
    // authoring window (between authoring_started_at and authoring_completed_at).
    //
    // Validated by GEO_001b-V1 ProducerValidator + GEO_001b-V2 CostCapValidator + GEO_001b-V3
    // IterationCapValidator. Per-iteration LLM call uses S9 template `world_authoring/v1.tmpl` per
    // §12Y.L2 governance with schema-constrained generation REQUIRED (OpenAI structured outputs / vLLM
    // grammar mode / equivalent) against creative_seed.v2.schema.json generated from Rust struct via
    // schemars at build time.
    //
    // NEW closed enums on CreativeSeed (V1+ schema_version 2 — additive per I14):
    //   SpatialPreference 14-variant (Northern / Southern / Equatorial / Coastal / Inland / Insular /
    //   Highland / Lowland / RiverValley / NearBiome(BiomeKind) / NearClimate(ClimateZone) /
    //   NearCulture(CultureTag) / NearSettlement(LocalizedName) / FarFromSettlement(LocalizedName) /
    //   ExplicitPosition{x, y} / Any).
    //
    // CreativeSeed.schema_version 1 → 2: position_normalized becomes Optional V1+; spatial_preference
    // Option<SpatialPreference> added Optional V1+; validator at-least-one-Some enforces
    // `authoring.spatial_intent_required` on culture_hints + canonical_settlements.
    //
    // BFF-held AuthoringSession is NOT an aggregate; not event-sourced V1. Per GEO_001b-Q1, V1
    // architectural choice: rejected drafts are ephemeral (privacy + storage cost); V1+ optionally
    // persist accepted-only iterations if audit need surfaces.
    // ContinentGeometryDecl {
    //   continent_channel_id: ChannelId,                   // MUST resolve to continent-tier channel per DP-Ch1; reject geography.invalid_channel_tier
    //   geography_seed: GeographySeed,                     // REQUIRED per continent if declared; { master_seed: u64, + 5 derived sub-seeds }
    //   creative_seed: CreativeSeed,                       // REQUIRED per continent if declared; reject geography.creative_seed_required_when_seeded if missing
    //   geography_deltas: Vec<GeographyDelta>,             // OPTIONAL initial canon-seeded edits at bootstrap; ordered append-only
    // }
    //
    // CreativeSeed shape: archetype (WorldArchetype 12-variant closed enum: Wuxia/HighFantasy/LowFantasy/
    // Cyberpunk/SteamPunk/Postapocalyptic/ScienceFiction/Historical/Mythological/Romance/Mystery/Custom) +
    // world_scale (WorldScale 5-variant: Pocket~1024 / Region~2048 / Continent~8192 / SuperContinent~12288 /
    // Megaplanet~16384 cells) + hemisphere_orientation + coastline_profile + climate_bias Option<ClimateZone>
    // + culture_hints Vec<CultureHint ≤16> + canonical_settlements Vec<CanonicalSettlementDecl> (author-pinned
    // burgs that MUST exist post-generation; placed before V1+ SET_001 weighted generation; ~5-50 typical) +
    // canonical_provinces Vec<CanonicalProvinceDecl> V1+ stage 5 + lore_hooks_per_region (LLM context only;
    // NOT consumed by generator) + naming_styles HashMap<CultureTag, NamingStyleDecl>.
    //
    // CreativeSeed is IMMUTABLE post-bootstrap V1 (reject geography.creative_seed_immutable_v1 on direct Forge
    // edit); V1+ extension via T6 LLM proposal → T8 Forge approval per GEO-D12.
    //
    // GeographyDelta {
    //   id: GeographyDeltaId (monotonic u64 per continent; append-only ordered),
    //   kind: GeographyDeltaKind (6 V1: AddNamedSettlement / RenameRegion / SetBiomeOverride / AddRoute /
    //         RemoveRoute / SetResourceOverride V2+),
    //   applied_at_fiction_time, authored_by_actor_id (Forge per WA_003 audit), reason: I18nBundle (50+ char
    //   per S5 Tier 2 Griefing discipline; Tier 1 Destructive for SetBiomeOverride + RemoveRoute),
    // }
    //
    // Validated by GEO-V1 SchemaGate + GEO-V2 ReferentialIntegrityGate (cell_id ∈ cells; route_id ∈ routes
    // if RemoveRoute) + GEO-V3 OrderingGate (prev_delta_id == world_geometry.last_delta_event_id; reject
    // geography.delta_order_violation; parallel to TDIL-A8 worldline-monotonicity discipline).
    //
    // NEW T2/Channel-continent aggregate `world_geometry` (NOT a RealityManifest field; one row per continent
    // channel; ChannelScoped per DP-Ch4 marker): owner=GEO_001; materialized at RealityBootstrapper via
    // EVT-T4 GeographyBorn from `continent_geometries[i]`. Per GEO_001 §3.1.
    //
    // EVT-T8 Forge sub-shapes V1 active: Forge:EditGeographyDelta (canonization adds delta) +
    // Forge:ForkGeographyInherit (DP-Internal SnapshotForker emits per continent; copies parent
    // deltas-at-fork-point per MV6 + 4-layer canon L3 scope).
    //
    // Composition with foundation siblings (each tracked as separate V1+ activation):
    //   MAP_001 V1+ position auto-derivation (GEO-D5 — map_layout.position derives from settlement centroids)
    //   PF_001 V1+ procedural place generation (PF-D7 activation — PlaceType selection from biome)
    //   CSC_001 V1+ skeleton selection from biome (forest_clearing for Forest; cave for Mountain; etc.)
    //   RES_001 V2+ resource distribution generator (GEO-D10 — climate × biome conditioned Poisson-disk)
    //   PROG_001 V2+ cultivation-realm biome modifiers (GEO-D7 MagicalAnomaly ClimateZone extension)

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
| `Forge:EditGeographyDelta { continent_channel_id, delta_kind, delta_payload, prev_delta_id }` (added 2026-05-13 fix cycle MED-1) | GEO_001 World Geometry |

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
