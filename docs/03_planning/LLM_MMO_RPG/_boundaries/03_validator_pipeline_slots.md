# 03 — Validator Pipeline Slot Ordering (EVT-V*)

> **Status:** seed 2026-04-25 + alignment review 2026-04-26 (resolved EF-Q3 + PF-Q1 + MAP-Q1 + CSC-Q2 in single boundary pass; Stage 3.5 group inserted).
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.
>
> **Authoritative source pending:** event-model agent's Phase 3 (`07_event_model/05_validator_pipeline.md`) will LOCK the final ordering. Until that lands, this file is the working consensus. Foundation tier 4/4 structural validators (entity_affordance / place_structural / map_layout / cell_scene) now have explicit slot positions per Stage 3.5 group below.

---

## Why this file exists

Per EVT-A5 ("validator pipeline runs in fixed order, no skips"), the EVT-V* pipeline has a single ordering. Multiple features have already proposed where THEIR slot fits:

- **WA_001 Lex** §7.1: "schema → capability → A5 → A6-sanitize → ★ lex_check ★ → A6-output → canon-drift → causal-ref → commit"
- **WA_002 Heresy** §6.1: "★ heresy_check ★ runs immediately after Lex"
- **WA_006 Mortality** (provisional): hot-path mortality check is BEFORE validators (turn-submission gate, not validator pipeline)

Without coordination, drift accumulates. This file is the staging area for the final EVT-V* ordering.

---

## Proposed ordering (V1 — pending event-model agent's Phase 3 lock)

```text
incoming TurnEvent / EVT-T* candidate
    │
  [stage 0] schema validate
    │   purpose: payload shape per per-category contract (event-model Phase 2)
    │   owner: event-model
    │
  [stage 1] capability check (DP-K9)
    │   purpose: JWT carries required produce: claim and read/write permissions
    │   owner: DP / event-model
    │
  [stage 2] A5 intent classification
    │   purpose: confirms the proposal's intent matches the actor type
    │   owner: 05_llm_safety
    │
  [stage 3] A6 sanitize (input layer)
    │   purpose: jailbreak / injection scan on raw LLM output
    │   owner: 05_llm_safety
    │
  [stage 3.5] ★ structural validators ★ (alignment review locked 2026-04-26)
    │   purpose: world-state consistency checks (referenced entities/places/cells/map valid)
    │           runs BEFORE lex semantic check (cheaper rejects; fail-fast principle)
    │           each sub-stage has applicability predicate (early-exit when not relevant
    │           to event kind — see §applicability table below)
    │   ordering: fail-fast common-case-first; specific checks last
    │
    │   3.5.a ★ entity_affordance ★          → EF_001
    │         purpose: target entity exists + lifecycle ∈ {Existing,Suspended} +
    │                  required affordance flag in entity's effective AffordanceSet
    │         soft-override: per-InteractionKind tolerates_destroyed/tolerates_suspended
    │                        (PL_005 InteractionKindSpec; Examine tolerates Destroyed)
    │
    │   3.5.b ★ place_structural ★           → PF_001
    │         purpose: target place exists + structural_state allows action
    │                  (Pristine/Damaged/Restored = OK for most actions;
    │                   Destroyed = soft-rejectable per kind; Removed = hard-reject)
    │
    │   3.5.c ★ map_layout ★                 → MAP_001
    │         purpose: visual graph constraints — cross-tier disallowed V1;
    │                  Travel-specific (connection valid + tier matches)
    │
    │   3.5.d ★ cell_scene ★                 → CSC_001
    │         purpose: cell-internal layout constraints — zone integrity;
    │                  walkable/placeable for write events modifying cell state
    │
  [stage 4] ★ lex_check ★
    │   purpose: hard physics-axiom enforcement (does this ability exist in this reality?)
    │   owner: WA_001 Lex
    │
  [stage 5] ★ heresy_check ★ (only if lex_check returned AllowedWithBudget)
    │   purpose: budget tracking + cascade-on-exceed
    │   owner: WA_002 Heresy
    │
  [stage 6] A6 output filter
    │   purpose: post-LLM output filter — NSFW, persona-break, cross-PC leak
    │   owner: 05_llm_safety
    │   (also where WA_006 Mortality death-detection sub-validator lives — provisional)
    │
  [stage 7] canon-drift check (A6-related but distinct)
    │   purpose: L1/L2/L3 canon consistency
    │   owner: 05_llm_safety + knowledge-service
    │
  [stage 8] causal-ref integrity (EVT-A6)
    │   purpose: referenced parent events exist + same-reality + gap-free
    │   owner: event-model
    │
  [stage 9] world-rule lint (general)
    │   purpose: per-feature world-rule checks not covered by Lex/Heresy
    │   owner: cross-cutting (each feature's validator)
    │
  [commit] dp::advance_turn OR dp::t2_write per feature contract
```

### Hot-path checks (PRE-pipeline gate)

These run BEFORE the validator pipeline (cheap rejects to save validator cost):

| Check | Owner | Purpose |
|---|---|---|
| Turn-slot availability | PL_001 (turn-slot Strict) + DP-Ch51 | Claim turn-slot before processing turn |
| Idempotency cache | PL_001 §14 | Cached response returns immediately for retries |
| Mortality state | WA_006 Mortality (PROVISIONAL — should be PL_001 hook) | Reject turns from Dead/Dying/Ghost PCs |
| Concurrent-turn detection | PL_002 §6 | Reject second turn-submit while first is in-flight |

### Post-commit side-effects

These run AFTER commit (queued during validator pipeline; executed in same handler):

| Side-effect | Owner | Trigger |
|---|---|---|
| FictionClock advance | PL_001 §3.1 | After Accepted PlayerTurn with `fiction_duration > 0` |
| ContaminationState increment | WA_002 Heresy | After Accepted action that consumed contamination budget |
| WorldStability strain bump | WA_002 Heresy | After Accepted contamination action with `ConvertWorldEnergy` substrate |
| NpcReactionPriority `last_reacted_turn` update | NPC_002 Chorus | After Accepted NPCTurn from Chorus |
| MortalityState transition (provisional) | WA_006 Mortality | After PlayerTurn/NPCTurn with death-detection trigger |
| ForgeAuditEntry append | WA_003 Forge | After every ForgeEdit AdminAction |
| Idempotency cache write | PL_001 §14 | After every accepted/rejected turn (60s TTL) |
| **PlaceDestroyed cascade** (added 2026-04-26 alignment review) | PF_001 §6.1 | After Accepted PF_001 place state delta `→ Destroyed`; emits dedicated EVT-T3 sub-shape with occupants list; consumer features (PCS_001 / NPC_001 / future Item / future EnvObject) subscribe for cascade response; cascade ordering 4-step deterministic per PF_001 §7 |
| **EntityLifecycle cascade (HolderCascade)** (added 2026-04-26) | EF_001 §6.1 | After Accepted EF_001 lifecycle delta from cascade source (parent destroyed → held items drop / containers cascade); deterministic atomic batch with cascading entity_binding deltas |

---

## Stage 3.5 sub-stage applicability (alignment review 2026-04-26)

Each sub-stage in the structural-validators group has an applicability predicate. When `applies_to_event(event) == false`, the sub-stage early-exits without running its expensive checks. This keeps the pipeline cheap for events where structural validation isn't relevant.

| Sub-stage | Applies when | Early-exit when |
|---|---|---|
| **3.5.a entity_affordance** | EVT-T1 Submitted with target entity_ids in payload (PL_005 InteractionKinds: Speak/Strike/Examine/Give/Use); EVT-T1 sub-types referencing entities | EVT-T4 System (DP-emitted; no actor target) · EVT-T8 Administrative scope-based (no entity reference) · EVT-T3 Derived (already-validated cascade outputs) · payload has no entity_id field |
| **3.5.b place_structural** | Any event with cell-context (most PC actions; PL_005 InteractionKinds; Travel) | EVT-T8 Administrative pre-canon-active phase · cross-reality refs (V1+ only; structural across realities) · pure metadata events (no place reference) |
| **3.5.c map_layout** | Travel events specifically (PL_001 §13 cell-to-cell or non-cell-tier scripted-NPC-travel); Forge:EditMapLayout admin events | Non-Travel EVT-T1 · cell-internal events (PL_005 Speak/Strike/Examine/Give/Use within same cell) · entity_binding lifecycle deltas (handled by entity_affordance instead) |
| **3.5.d cell_scene** | Write events modifying cell state — Forge:EditCellScene; PL_005 Strike Destructive cascade triggers (place state transition); CSC's own Layer 3 LLM commit | Read events (cell scene UI subscribe) · non-cell scope events · already-canonical events that don't mutate cell layout |

**Applicability is determined by event-kind match against the predicate table.** Each sub-stage's owner-feature documents the predicate in their spec (EF_001 §11 / PF_001 §12 / MAP_001 §12 / CSC_001 §13). Validator implementation calls `applies_to_event(event)` first; skips cleanly if false.

---

## Soft-override mechanism (Q4 alignment 2026-04-26)

EF_001 §8 declares per-rule_id soft-override eligibility (e.g., `entity.entity_destroyed` is soft-overridable for Examine kind). The mechanism is INTERNAL to the entity_affordance validator (Stage 3.5.a):

```
entity_affordance validator logic:
  ┌─────────────────────────────────────────────────────────────┐
  │ for each entity_ref in event.targets:                       │
  │   tile = lookup(entity_ref) → fail entity.unknown_entity    │
  │   lifecycle = tile.lifecycle_state                          │
  │                                                              │
  │   if lifecycle == Destroyed:                                │
  │     if event.kind has tolerates_destroyed flag:             │
  │       ★ SOFT-PASS: emit warning; pipeline continues ★       │
  │     else:                                                    │
  │       ✗ HARD-FAIL: reject entity.entity_destroyed           │
  │                                                              │
  │   if lifecycle == Removed:                                  │
  │     ✗ HARD-FAIL: reject entity.entity_removed               │
  │     (Removed has NO soft-override; "this entity never was")│
  │                                                              │
  │   if lifecycle == Suspended:                                │
  │     similar tolerates_suspended check per kind              │
  │                                                              │
  │   ... affordance checks                                      │
  └─────────────────────────────────────────────────────────────┘
```

Pipeline downstream (lex / heresy / etc.) sees pass/fail only — soft-override is invisible at stage boundary. PL_005 InteractionKindSpec declares `tolerates_destroyed: bool` and `tolerates_suspended: bool` per kind (EF_001 §8 referenced contract).

Same pattern applies to other sub-stages with rule_ids marked "soft-override eligible" in their respective namespace tables (PF_001 §9 + MAP_001 §9 + CSC_001 §10.2).

---

## Stage → rule_id namespace matrix (Q6 alignment 2026-04-26)

Helps onboarding — quick lookup "which stage owns my rule_id":

| Stage | Validator | rule_id prefix | Owner namespace V1 count | V1+ reservations |
|---|---|---|---|---|
| 0 | schema validate (incl. canonical seed cross-aggregate consistency — see §"Stage 0 canonical seed cross-aggregate consistency rules" below) | (engine error + Tier 5 substrate namespaces) | event-model + Tier 5 features | — |
| 1 | capability check | `capability.*` | DP-K9 | — |
| 2 | A5 intent classification | (logged) | 05_llm_safety A5 | — |
| 3 | A6 sanitize | `oracle.*` / `canon_drift.*` (input layer subset) | 05_llm_safety | — |
| **3.5.a** | **entity_affordance** | **`entity.*`** | **EF_001 (10 V1)** | 2 V1+ (cyclic_holder_graph, cross_reality_reference) |
| **3.5.b** | **place_structural** | **`place.*`** | **PF_001 (12 V1)** | 4 V1+ (scheduled_decay_collision, cross_reality_connection, procedural_generation_rejected, connection_gate_unresolved) |
| **3.5.c** | **map_layout** | **`map.*`** | **MAP_001 (13 V1)** | 3 V1+ (cross_reality_layout, layout_too_dense, connection_method_unsupported) |
| **3.5.d** | **cell_scene** | **`csc.*`** | **CSC_001 (9 V1)** | 4 V1+ (skeleton_invalid, procedural_density_too_high, narration_unsafe_content, layer3_occupant_set_changed) |
| 4 | lex_check | `lex.*` | WA_001 | — |
| 5 | heresy_check | `heresy.*` | WA_002 | — |
| 6 | A6 output filter | (logged) | 05_llm_safety A6 | — |
| 7 | canon-drift check | `canon_drift.*` | 05_llm_safety | — |
| 8 | causal-ref integrity | (event-model) | event-model EVT-A6 | — |
| 9 | world-rule lint | `world_rule.*` | cross-cutting | — |

### Tier 5 Actor Substrate namespaces (added 2026-04-27 P4 closure-pass-extension)

These namespaces validate at **Stage 0 schema** (canonical seed validation + Forge admin events; cross-aggregate consistency rules below); they don't have dedicated pipeline slots. Most don't run during LLM-output pipeline (they're bootstrap-time + Forge-time validators):

| Namespace | Owner feature | V1 rules count | V1+ reservations | Validation timing |
|---|---|---|---|---|
| `resource.*` | RES_001 Resource Foundation | 12 V1 | 3 V1+ | Stage 0 canonical seed + Forge admin + PL_005 transfer flows |
| `race.*` | IDF_001 Race Foundation | 5 V1 | 4 V1+ | Stage 0 canonical seed + Forge admin |
| `language.*` | IDF_002 Language Foundation | 4 V1 | 2 V1+ | Stage 0 canonical seed + Stage 7 Speak validator V1+ |
| `personality.*` | IDF_003 Personality Foundation | 3 V1 | 2 V1+ | Stage 0 canonical seed + Forge admin |
| `origin.*` | IDF_004 Origin Foundation | 4 V1 | 2 V1+ | Stage 0 canonical seed + Forge admin |
| `ideology.*` | IDF_005 Ideology Foundation | 3 V1 | 5 V1+ | Stage 0 canonical seed + Forge admin |
| `family.*` | FF_001 Family Foundation | 8 V1 | 4 V1+ | Stage 0 canonical seed + Forge admin |
| `faction.*` | FAC_001 Faction Foundation | 8 V1 | 4 V1+ | Stage 0 canonical seed + Forge admin |
| `progression.*` | PROG_001 Progression Foundation | 7 V1 | 6 V1+ | Stage 0 canonical seed + PL_005 cascade hot-path + V1+ Stage 4 lex_check (axiom-gated abilities) |
| `reputation.*` | REP_001 Reputation Foundation | 6 V1 | 4 V1+ | Stage 0 canonical seed + Forge admin + V1+ runtime delta events |
| `actor.*` | ACT_001 Actor Foundation | 8 V1 (P2 added: spawn_cell_unknown + glossary_entity_unknown) | 3 V1+ | Stage 0 canonical seed cross-aggregate consistency (see §below) |
| `pc.*` | PCS_001 PC Substrate | 7 V1 | 3 V1+ | Stage 0 canonical seed cross-aggregate consistency + Forge admin |
| `ai_tier.*` | AIT_001 AI Tier Foundation | 8 V1 | 4 V1+ | Stage 0 canonical seed + V1+ runtime tier transitions |
| `time_dilation.*` | TDIL_001 Time Dilation Foundation | 4 V1 | 6 V1+30d | Stage 0 canonical seed + per-turn channel boundary checks |
| `title.*` | TIT_001 Title Foundation | 9 V1 (Phase 3 cleanup added 2 binding-membership-required rules) | 5 V1+ | Stage 0 canonical seed + Forge admin + cross-aggregate cascade C18 (synchronous on WA_006 mortality EVT-T3) |
| `session.*` | DF05_001 Session/Group Chat Foundation | 14 V1 (Phase 3 cleanup added participant_already_joined defensive) | 5 V1+ | Stage 0 canonical seed (canonical_sessions OPTIONAL V1) + Stage 1 runtime (PC `/chat` create + actor join/leave) + Stage 7 Forge admin (9 sub-shapes) + Stage 8 close cascade (POV-distill + actor_session_memory writes) + cross-aggregate cascades C26-C29 (anchor_pc_kind + same_channel + cell_capacity + one_active_per_actor) |

**Total V1 rule_ids across all namespaces:** ~44+ (entity/place/map/csc) + ~110+ (Tier 5 substrate; ~96 prior + 14 DF5) = ~154 V1 reject rules total across the engine. ~113+ are **Stage 0 schema validators** (canonical seed + Forge admin + cross-aggregate cascade); ~44+ are LLM-output pipeline validators (Stage 3.5+).

---

## Stage 0 canonical seed cross-aggregate consistency rules (added 2026-04-27 P4 closure-pass-extension)

Cross-aggregate consistency rules run at **bootstrap time** (canonical seed validation; NOT in LLM-output pipeline). When RealityBootstrapper validates a `RealityManifest`, these rules ensure cross-aggregate coherence post-bootstrap. Each rule's owner-feature is responsible for the validation logic; cross-references documented here for boundary review convenience.

### Rules at canonical seed bootstrap

| Rule | Owner | Cross-references | Reject |
|---|---|---|---|
| **C1: actor_core ↔ entity_binding scope_id consistency** | EF_001 + ACT_001 | `actor_core.current_region_id` (cell-tier ChannelId) MUST match `entity_binding.scope_id` (when scope_tier = Channel/cell) for the same actor_id post-bootstrap | `actor.cell_binding_mismatch` (V1+ activation if pain emerges; V1 implicit via shared `spawn_cell` source field per P2) |
| **C2: CanonicalActorDecl.spawn_cell ∈ RealityManifest.places** | ACT_001 + PF_001 | spawn_cell (cell-tier ChannelId) MUST reference declared place per PF_001 places extension | `actor.spawn_cell_unknown` (P2 LOCKED 2026-04-27) |
| **C3: CanonicalActorDecl.glossary_entity_id ∈ knowledge-service canon** | ACT_001 + knowledge-service | glossary_entity_id MUST reference valid canonical glossary entry | `actor.glossary_entity_unknown` (P2 LOCKED 2026-04-27) |
| **C4: actor_origin.native_language ∈ RealityManifest.languages** | IDF_004 + IDF_002 | actor_origin.native_language LanguageId MUST be declared in RealityManifest.languages per IDF_002 LanguageDecl | `language.unknown_language_id` (IDF_002 namespace) |
| **C5: actor_origin.default_ideology_refs ∈ RealityManifest.ideologies** | IDF_004 + IDF_005 | All IdeologyId refs MUST be in RealityManifest.ideologies | `origin.unknown_ideology_ref` (IDF_004 namespace) |
| **C6: actor_origin.birthplace_channel ∈ RealityManifest.places** | IDF_004 + PF_001 | birthplace_channel ChannelId (cell-tier) MUST be declared place | `origin.unknown_birthplace` (IDF_004 namespace) |
| **C7: actor_faction_membership.faction_id ∈ canonical_factions** | FAC_001 | faction_id MUST be in RealityManifest.canonical_factions | `faction.unknown_faction_id` (FAC_001 namespace) |
| **C8: actor_faction_membership ideology binding (resolves IDL-D2)** | FAC_001 + IDF_005 | If FactionDecl.requires_ideology Some, actor's ideology stance MUST satisfy each (IdeologyId, MinFervorLevel) per Q LOCKED FAC | `faction.ideology_binding_violation` (FAC_001 namespace) |
| **C9: actor_faction_reputation references (FAC_001 + EF_001)** | REP_001 + FAC_001 + EF_001 | actor_id ∈ canonical_actors AND faction_id ∈ canonical_factions; sparse storage discipline | `reputation.unknown_actor_id` + `reputation.unknown_faction_id` (REP_001 namespace) |
| **C10: actor_progression.kind_id ∈ progression_kinds** | PROG_001 | All ProgressionKindId refs in actor_progression MUST be declared in RealityManifest.progression_kinds | `progression.training.kind_unknown` (PROG_001 namespace) |
| **C11: PcBodyMemory languages ∈ RealityManifest.languages** | PCS_001 + IDF_002 | PcBodyMemory.{soul, body}.native_language LanguageId MUST be declared per IDF_002 | `language.unknown_language_id` (cross-feature; PCS_001 emits for body_memory) |
| **C12: PcBodyMemory references ∈ knowledge-service canon** | PCS_001 + knowledge-service | SoulLayer.origin_world_ref (Optional GlossaryEntityId) + BodyLayer.host_body_ref (Optional GlossaryEntityId) MUST be valid canon entries when Some | `pc.invalid_transmigration_combination` (PCS_001 namespace; renamed from invalid_xuyenkhong_combination per user direction) |
| **C13: V1 cap=1 PC per reality** | PCS_001 | Stage 0 schema validator counts canonical_actors with kind=Pc + pc_user_binding rows; cap=1 V1; V1+ relax via RealityManifest.max_pc_count Optional (PCS-D3) | `pc.multi_pc_per_reality_forbidden_v1` (PCS_001 namespace) |
| **C14: actor_chorus_metadata sparse population matches ActorKind** | ACT_001 | chorus_metadata Some ↔ ActorKind = NPC V1 (control source = AI always V1); chorus_metadata None ↔ ActorKind = PC V1 (User-control); V1+ AI-controls-PC-offline relaxes for offline PCs | `actor.kind_specific_field_mismatch` (ACT_001 namespace) |
| **C15: mortality_config.mode = RespawnAtLocation V1 forbidden** | PCS_001 + WA_006 | If mortality_config.mode = RespawnAtLocation declared but PCS-D2 Respawn flow V1+ not active, reject canonical seed bootstrap; reality must use Permadeath or Ghost mode V1 | `pc.respawn_unsupported_v1` (PCS_001 namespace; per Q7 LOCKED) |
| **C16: actor_clocks initialization from body_memory canonical** | TDIL_001 + PCS_001 + ACT_001 | TDIL_001 actor_clocks initialized at canonical seed reading body_memory.{soul, body} state if PC has xuyên không origin_world_ref Some; otherwise actor_clock + soul_clock + body_clock all start at 0 (native PC + native NPC) | `time_dilation.invalid_initial_clocks` (TDIL_001 namespace) |
| **C17: AIT_001 tier_hint at canonical seed** | AIT_001 + ACT_001 | If AIT_001 tier semantics declared on CanonicalActorDecl, validate tier_hint matches NpcTrackingTier V1 enum (Major / Minor / Untracked); PC always Tier 0 (no tier_hint declared); cross-validate with capacity caps (≤20 Major, ≤100 Minor per AIT_001 §11) | `ai_tier.canonical_tier_required` + `ai_tier.capacity_exceeded` (AIT_001 namespace) |
| **C18 (TIT-C1): title-holder death → synchronous succession cascade** | TIT_001 (consumer of WA_006 mortality EVT-T3) | RUNTIME cross-aggregate cascade (NOT canonical seed) — title-holder death (WA_006 mortality_state Alive → Dying / Dead) synchronously fires TIT_001 succession cascade same turn per Q7 A LOCKED; cascade applies SuccessionRule (Eldest FF_001 dynasty traversal / Designated heir / Vacate); emits TitleSuccessionTriggered EVT-T3 + TitleGranted EVT-T4 (if heir) + TitleSuccessionCompleted EVT-T1 narrative; atomic FAC_001 actor_faction_membership.role_id update if TitleAuthorityDecl.faction_role_grant Some | (no reject; cascade applies VacancySemantic when ineligible) |
| **C19 (TIT-C2): TitleHoldingDecl + Forge:GrantTitle title_id ∈ canonical_titles** | TIT_001 | TitleHoldingDecl.title_id (canonical seed) + Forge:GrantTitle.title_id (runtime) MUST be declared in RealityManifest.canonical_titles | `title.declared.unknown` (TIT_001 namespace) |
| **C20 (TIT-C3): TitleHoldingDecl + Forge:GrantTitle actor_id ∈ canonical_actors** | TIT_001 + EF_001 | actor_id MUST be declared in RealityManifest.canonical_actors | `title.holding.actor_unknown` (TIT_001 namespace) |
| **C21 (TIT-C4): TitleBinding::Faction(faction_id) → faction_id ∈ canonical_factions** | TIT_001 + FAC_001 | If TitleDecl.binding == Faction(faction_id), faction_id MUST be in RealityManifest.canonical_factions | `title.binding.faction_unknown` (TIT_001 namespace) |
| **C22 (TIT-C5): TitleBinding::Dynasty(dynasty_id) → dynasty_id ∈ canonical_dynasties** | TIT_001 + FF_001 | If TitleDecl.binding == Dynasty(dynasty_id), dynasty_id MUST be in RealityManifest.canonical_dynasties | `title.binding.dynasty_unknown` (TIT_001 namespace) |
| **C23 (TIT-C6): MultiHoldPolicy compliance per actor** | TIT_001 | Stage 0 schema validator counts rows per actor_ref; rejects if violates declared MultiHoldPolicy::StackableMax(N) cap | `title.holding.multi_hold_violation` (TIT_001 namespace) |
| **C24 (TIT-C7): Exclusive policy compliance per title** | TIT_001 | Stage 0 schema validator counts rows per title_id; rejects if MultiHoldPolicy::Exclusive title has >1 holder concurrently | `title.holding.exclusive_violation` (TIT_001 namespace) |
| **C25 (TIT-C8): designated_heir alive at succession cascade time** | TIT_001 | At cascade trigger (C18), validate designated_heir alive (mortality_state ≠ Dead/Dying); if invalid, set new_holder=None with trigger_reason=HeirIneligible per §7.2 cascade pseudocode | `title.succession.heir_invalid` (TIT_001 namespace; OR sets None gracefully per cascade flow) |
| **C26 (DF5-C1): session.anchor_pc_id MUST be PC kind** | DF05_001 | At session creation (`/chat` runtime OR canonical seed), verify anchor_actor_id resolves to ACT_001 actor_core where ActorKind::Pc; reject if non-PC | `session.anchor_must_be_pc` (DF05_001 namespace) |
| **C27 (DF5-C2): session.channel_id MUST be cell-tier** | DF05_001 | At session creation, verify channel_id resolves to PF_001 cell-tier place row (NOT continent/country/district/town aggregation tier); reject if higher-tier channel | `session.cross_channel_participation_forbidden` (DF05_001 namespace; alt phrasing for tier mismatch) |
| **C28 (DF5-C3): per-cell session capacity ≤50 V1** | DF05_001 | At session creation, count Active sessions where channel_id matches; reject if ≥50 V1 per DF5-A8 soft cap | `session.cell_session_overload` (DF05_001 namespace) |
| **C29 (DF5-C4): per-actor one Active session V1** | DF05_001 | At session_participation Born, verify actor has no other Active session_participation row where left_fiction_time IS NULL; reject if found per DF5-A5 | `session.actor_busy_in_other_session` (DF05_001 namespace) |

### Rule application discipline

- **Stage 0 schema validation runs at canonical seed bootstrap** (RealityBootstrapper) AND at Forge admin events (mid-runtime). Rules that reference RealityManifest fields validate against the manifest at bootstrap; runtime Forge edits validate against current aggregate state.
- **Each rule's owner feature** is responsible for the validation logic in their owner-service (e.g., FAC_001 owner-service runs C7 + C8; PCS_001 owner-service runs C13 + C15).
- **Cross-reference rules** (e.g., C4 validates IDF_004 actor_origin against IDF_002 languages) — ownership belongs to the FIRST feature in the dependency direction (IDF_004 owns C4 logic since actor_origin is IDF_004's aggregate).
- **C1 implicit V1, explicit V1+** — C1 (actor_core ↔ entity_binding scope_id) is enforced V1 implicitly via shared `spawn_cell` source field (P2 LOCKED 2026-04-27); both aggregates populate from the same CanonicalActorDecl.spawn_cell field. Explicit cross-aggregate validation V1+ if drift detected.
- **C18 (TIT-C1) is RUNTIME cascade, not canonical seed** — Unlike C1-C17 + C19-C25 (all canonical seed bootstrap-time validators), C18 fires at RUNTIME on every WA_006 mortality EVT-T3 actor_dies event for any title-holder. Synchronous same-turn cascade (per Q7 A LOCKED) — title-holder death triggers TitleSuccessionTriggered + (optional) TitleGranted + (optional) TitleSuccessionCompleted within the same turn-event's commit window. Joins the pattern of WA_006 cross-aggregate cascades (mortality_state + vital_pool zeroing) but extends to political-rank layer.
- **C19-C25 mirror earlier patterns** — C19/C20 (declared.unknown / actor_unknown) follow C2/C3 ACT_001 patterns; C21/C22 (faction_unknown / dynasty_unknown) follow C7/C5 FAC_001/IDF_004 patterns; C23/C24 (multi-hold / exclusive) are TIT-specific multi-row count validators; C25 (heir_invalid) supports C18 cascade flow.

### What's NOT in this list

- **Within-aggregate schema validation** — handled by individual feature's namespace (`<feature>.unknown_*`, `<feature>.invalid_*`); not "cross-aggregate"
- **LLM-output pipeline validation** — Stage 1+ (capability / A5 / A6 / structural / lex / heresy / etc.) is separate from Stage 0 canonical seed; those rules apply to PC turn submissions + NPC reactions, not bootstrap
- **V1+ runtime cascade rules** (e.g., NPC_002 Tier 4 priority modifier reading REP_001) — V1+ enrichment when respective features ship runtime activations

---

## Adding a new validator slot

When a future feature proposes a new validator slot:

1. Lock-claim `_LOCK.md`
2. Edit "Proposed ordering" above to insert the new stage at the right position
3. Document:
   - Slot name (e.g., `inventory_check`)
   - Owner feature
   - Purpose (one line)
   - Why it slots at that position (cost? dependency? safety?)
4. Update `01_feature_ownership_matrix.md` "Schema / envelope ownership" if applicable
5. Append `99_changelog.md`
6. Lock-release
7. Notify event-model agent if Phase 3 is still in progress; their work absorbs this final ordering

---

## Drift resolutions

These boundary-review decisions have been recorded here as the canonical resolution. When a feature's design doc disagrees, it's the feature doc that's stale.

| Drift watchpoint | Resolution |
|---|---|
| **LX-D5 (Lex slot ordering)** | Locked: stage 4 (per §7.1 above). |
| **HER-D8 (Heresy stage transitions emit EVT-T11 vs EVT-T8)** | Provisional: V1 emits EVT-T8 AdminAction-only; V1+30d adds EVT-T11 WorldTick. Captured in 04_event_taxonomy.md (event-model). |
| **GR-D8 (rejected-turn commit primitive)** | Pending event-model agent Phase 2 per-category contract for EVT-T1. PL_001/PL_002's `t2_write` interpretation stands as feature-side contract until reconciled. |
| **WA_006 Mortality hot-path slot** | Provisional: PRE-pipeline gate (see "Hot-path checks" table). When WA_006 is rewritten thin + PCS_001 owns `pc_mortality_state`, the gate logic stays here as a PL_001 hook. |
| **A6 sub-validator placement (death-detection / NSFW / canon-drift)** | A6 is multi-stage (sanitize at stage 3, output filter at stage 6, drift at stage 7). All sub-validators within A6 are 05_llm_safety territory. |
| **EF-Q3 (entity_affordance slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.a** (between A6-sanitize stage 3 and lex_check stage 4). Soft-override mechanism INTERNAL to validator per §"Soft-override mechanism" above. |
| **PF-Q1 (place_structural slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.b** (after entity_affordance, before map_layout/cell_scene). Same group as EF-Q3. |
| **MAP-Q1 (map_layout slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.c** (after entity_affordance + place_structural; Travel-specific applicability per §"Stage 3.5 sub-stage applicability" above). Same group. |
| **CSC-Q2 (cell_scene slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.d** (most specific; cell-internal write events only per applicability table). Same group. Completes the structural-validator group of 4. |

---

## Future hardening

V2+ may add:
- Telemetry per stage (latency, fail rate, fail reason) → SLO dashboards
- Per-tier validator subset (e.g., AdminAction skips canon-drift but runs capability)
- Async parallel validators where order doesn't matter
- Validator-result caching for repeat content (LLM outputs that get re-validated)

These are deferred. V1 is the linear ordering above.
