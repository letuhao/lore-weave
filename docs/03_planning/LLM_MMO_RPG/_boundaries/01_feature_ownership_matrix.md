# 01 — Feature Ownership Matrix

> **Status:** seed 2026-04-25 — reflects the 11 features designed before this folder existed.
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.

---

## How to read

For every aggregate, schema, namespace, or validator slot in the LoreWeave LLM-MMO-RPG design, exactly ONE feature owns it. Other features REFERENCE without redefining.

Before designing a new feature: search this matrix for the aggregates / concepts you intend to own. If already owned by another feature, EITHER reference the existing owner OR escalate via boundary-review (claim lock + propose split / transfer).

---

## Aggregate ownership

| Aggregate | Tier × Scope | Owner feature | Notes |
|---|---|---|---|
| `fiction_clock` | T2 / Reality singleton | **PL_001 Continuum** | Per-reality fiction time. |
| `scene_state` | T2 / Channel (cell) | **PL_001 Continuum** | Per-cell ambient state. |
| `participant_presence` | T1 / Channel (cell) | **PL_001 Continuum** | Live "who's here" view; re-derived from DP-emitted MemberJoined/Left. |
| ~~`actor_binding`~~ → `entity_binding` | T2 / Reality | **EF_001 Entity Foundation** (CANDIDATE-LOCK 2026-04-26; transferred from PL_001 2026-04-26) | TRANSFERRED 2026-04-26: was "Where is X covers PCs + NPCs uniformly" under PL_001 §3.6. EF_001 extends scope to all 4 EntityType variants (Pc/Npc/Item/EnvObject) via 4-state `LocationKind` discriminator (InCell / HeldBy / InContainer / Embedded) + 4-state `LifecycleState` (Existing / Suspended / Destroyed / Removed) + per-instance `affordance_overrides`. PL_001 reopen: §3.6 now references EF_001 as owner. §14 acceptance: 10 scenarios AC-EF-1..10 (Phase 3 cleanup + closure-pass precision-tightening). See [EF_001 §3.1](../features/00_entity/EF_001_entity_foundation.md#31-entity_binding-t2--reality--primary). |
| `entity_lifecycle_log` | T2 / Reality (append-only) | **EF_001 Entity Foundation** (CANDIDATE-LOCK 2026-04-26) | Per-entity append-only audit trail of LifecycleState transitions. Causal-ref to triggering EVT-T1 Submitted. Reason kinds: CanonicalSeed / RuntimeSpawn / PcMortalityKill / NpcCold / AdminDecanonize / AutoRestoreOnCellLoad / AdminRestoreFromRemoved / InteractionDestructive / HolderCascade / Unknown (split AdminRestore in Phase 3 cleanup; HolderCascade added with §6.1 cascade rules). V1+ archiving deferred (EF-D10). See [EF_001 §3.2](../features/00_entity/EF_001_entity_foundation.md#32-entity_lifecycle_log-t2--reality-append-only). |
| `turn_idempotency_log` | T2 / Reality | **PL_001 Continuum** | Reconnect/idempotency safety. *Borderline; may relocate to PL_004 session lifecycle when designed.* |
| `tool_call_allowlist` | T2 / Reality | **PL_002 Grammar** (CANDIDATE-LOCK 2026-04-25) | Per-actor-type LLM tool-call allowlist. §13 acceptance: 10 scenarios. |
| `npc_reaction_priority` | T2 / Channel (cell) | **NPC_002 Chorus** (CANDIDATE-LOCK 2026-04-26) | Per-(cell, NPC) priority hint for multi-NPC reactions. §14 acceptance: 10 scenarios (SPIKE_01 turn 5 reproducibility verified). |
| `chorus_batch_state` | T1 / Channel (cell) | **NPC_002 Chorus** (CANDIDATE-LOCK 2026-04-26) | Transient orchestrator coordination. |
| `npc` (R8 import) | T2 / Reality | **NPC_001 Cast** (CANDIDATE-LOCK 2026-04-26) | DP-A14 annotations only; aggregate body locked by 02_storage R8. §14 acceptance: 10 scenarios. |
| `npc_session_memory` (R8 import) | T2 / Reality | **NPC_001 Cast** (CANDIDATE-LOCK 2026-04-26) | DP-A14 annotations only; body locked by 02_storage R8. |
| `npc_pc_relationship_projection` (R8 import) | T2 / Reality | **NPC_001 Cast** (CANDIDATE-LOCK 2026-04-26) | DP-A14 annotations only; body locked by 02_storage R8. |
| `npc_node_binding` | T2 (T3 on handoff) / Reality | **NPC_001 Cast** (CANDIDATE-LOCK 2026-04-26) | NPC owner-node mapping with epoch fence. |
| `lex_config` | T2 / Reality singleton | **WA_001 Lex** (CANDIDATE-LOCK 2026-04-25) | Per-reality physics/ability/energy axioms. §14 acceptance: 10 scenarios. |
| `actor_contamination_decl` | T2 / Reality | **WA_002 Heresy** (CANDIDATE-LOCK 2026-04-25) | Per-(actor, kind) contamination exception. |
| `actor_contamination_state` | T2 / Reality | **WA_002 Heresy** (CANDIDATE-LOCK 2026-04-25) | Per-(actor, kind) runtime budget tracking. |
| `world_stability` | T3 / Reality singleton | **WA_002 Heresy** (CANDIDATE-LOCK 2026-04-25) | 5-stage state machine. |
| `forge_audit_log` | T2 / Reality | **WA_003 Forge** (CANDIDATE-LOCK 2026-04-25) | Append-only audit; ALSO USED by PLT_001 + PLT_002 + WA_006 with their own AuditAction sub-shapes. WA_003 closure-reframed 2026-04-25 — patterns extractable to future CC_NNN are V1-essential here, V2+ optimization not boundary fix. §14 acceptance: 10 scenarios. |
| `coauthor_grant` | T2 / Reality | **PLT_001 Charter** (CANDIDATE-LOCK 2026-04-25; formerly WA_004; relocated 2026-04-25) | Active Co-Author grants. §14 acceptance: 10 scenarios AC-CHR-1..10. |
| `coauthor_invitation` | T2 / Reality | **PLT_001 Charter** (CANDIDATE-LOCK 2026-04-25) | Pending invitations with TTL. |
| `ownership_transfer` | T2 (T3 at Finalize) / Reality | **PLT_002 Succession** (CANDIDATE-LOCK 2026-04-25; formerly WA_005; relocated 2026-04-25) | Multi-stage state machine. PLT_002b lifecycle split 2026-04-25 — §14 acceptance: 10 scenarios AC-SUC-1..10. |
| `mortality_config` | T2 / Reality singleton | **WA_006 Mortality** (CANDIDATE-LOCK 2026-04-25) | Per-reality death-mode config. WA_006 thin-rewritten 2026-04-25 closure pass (730 → 403 lines); only legitimate WA scope kept. §12 acceptance: 6 scenarios. |
| `pc_mortality_state` | T2 / Reality | **PCS_001** (when designed) | Mechanics handed off from WA_006 in closure pass — over-extended sections removed from WA_006 entirely; future PCS_001 owner has clean slate. |
| `meta_user_pending_invitations` | global meta-DB table | **PLT_001 Charter** (CANDIDATE-LOCK 2026-04-25; formerly WA_004) | Cross-reality denormalized; CHR-D9 watchpoint. |
| `actor_status` | T2 / Reality | **PL_006 Status Effects** (DRAFT 2026-04-26) | Cross-actor (PC + NPC) status foundation. Per-(reality, actor_id) row holds `Vec<StatusInstance>`. Owns **StatusFlag closed-set enum** (V1: Drunk / Exhausted / Wounded / Frightened); V1+ kinds reserved (Stunned/Bleeding/Poisoned/Charmed/Encumbered/Buffed/Tired/Hungry/Restrained). Apply/Dispel via PL_005 Interaction OutputDecl with `aggregate_type=actor_status`. V1+30d auto-expire via Scheduled:StatusExpire Generator (EVT-T5). PCS_001 + future NPC_003 reference this enum (no drift). §15 acceptance: 7 V1-testable scenarios. |

---

## Schema / envelope ownership

These are SHARED across multiple features; each has a designated ENVELOPE owner who governs additive evolution.

| Schema | Envelope owner | Extending features | Extension rule |
|---|---|---|---|
| `TurnEvent` payload (EVT-T1 PlayerTurn / EVT-T2 NPCTurn) | **PL_001 Continuum** §3.5 | PL_002 (`command_kind`), NPC_002 (`reaction_intent`, `aside_target`, `action_kind`), WA_006 (provisional `outcome`) | See [`02_extension_contracts.md` §1](02_extension_contracts.md#1-turnevent-envelope) — additive only per foundation I14; envelope versioned `TurnEventSchema = N`. |
| `RealityManifest` | **(unowned — needs split)** ⚠ | PL_001 Continuum (starting_fiction_time + root_channel_tree + canonical_actors), WA_001 (LexConfig), WA_002 (contamination_allowances), WA_006 (mortality_config provisional), NPC_001 (CanonicalActorDecl extension) | See [`02_extension_contracts.md` §2](02_extension_contracts.md#2-realitymanifest) — proposal: extract to a new `IF_001_reality_manifest.md` infrastructure feature. |
| `ForgeEditAction` enum | **WA_003 Forge** §7 | PLT_001 Charter (CharterInvite/Accept/...), PLT_002 Succession (Succession*), WA_006 Mortality (MortalityConfig edits — provisional) | Closed enum extended via additive variants per I14. |
| Capability JWT (`forge.roles` + `forge.roles_version`) | **PLT_001 Charter** §6.3 | extended by PLT_002 (RealityOwner role), WA_006 (provisional MortalityAdmin) | Borderline with auth-service — flag for review when auth-service contributes. |
| `EVT-T8 Administrative` sub-shapes (was AdminAction; renamed in Option C redesign 2026-04-25) | event-model agent (Phase 2) | WA_003 (`ForgeEdit`), PLT_001 (`Charter*`), PLT_002 (`Succession*`), WA_006 (`MortalityAdminKill` provisional), core-admin (`Pause`/`Resume`/`ForceEndScene`/`WorldRuleOverride`) | Each feature DECLARES its sub-shapes; event-model `_index.md` lists current union. EVT-A11 mandates exactly-one ownership. |
| **EVT-T1 Submitted sub-types** (Option C redesign 2026-04-25 + PL_005 Interaction added 2026-04-26) | 07_event_model envelope; sub-types feature-owned | PL_001 + PL_002 own `PCTurn` (Speak/Action/MetaCommand/FastForward); NPC_001 + NPC_002 own `NPCTurn`; **PL_005 Interaction** owns `Interaction:Speak` / `Interaction:Strike` / `Interaction:Give` / `Interaction:Examine` / `Interaction:Use` (5 V1 kinds; V1+ Collide/Shoot/Cast/Embrace/Threaten reserved); future quest-engine owns `QuestOutcome` | Per EVT-A11 sub-type ownership discipline. Replaces former T2 NPCTurn category. |
| **EVT-T3 Derived sub-types** (Option C redesign 2026-04-25; EF_001 transfer 2026-04-26) | 07_event_model envelope; sub-discriminator = `aggregate_type` | Each aggregate-owner feature owns its delta-kinds (PL_001 owns fiction_clock/scene_state/participant_presence — `actor_binding` transferred to **EF_001 as `entity_binding`** 2026-04-26 + new `entity_lifecycle_log`; NPC_001 owns npc_pc_relationship_projection/npc_node_binding; PL_006 owns actor_status; etc.). Calibration sub-shapes (DayPasses/MonthPasses/YearPasses) owned by PL_001 (derived from FictionClock advance). | Replaces former T7 CalibrationEvent category — calibration is mechanically Derived. |
| **EVT-T4 System sub-type `EntityBorn`** (EF_001 CANDIDATE-LOCK 2026-04-26) | 07_event_model envelope; sub-type feature-owned | **EF_001 Entity Foundation** owns `EntityBorn { entity_id, entity_type, cell_id }` emitted at canonical seed (RealityBootstrapper) and runtime spawn (world-service). Cell membership emitted alongside via DP-A18 MemberJoined. | Per EVT-A11 sub-type ownership discipline. |
| **EntityKind trait** + **EntityBindingExt** (EF_001 CANDIDATE-LOCK 2026-04-26) | **EF_001 Entity Foundation** §4 | PCS_001 implements `EntityKind for Pc` · NPC_001 implements `EntityKind for Npc` · future Item feature implements `EntityKind for Item` · future EnvObject feature implements `EntityKind for EnvObject`. Each consumer MUST implement `type_default_affordances(&self)` (no default impl; `&self` for dyn-dispatch) — forces explicit affordance declaration. | EntityKind: 4 body-only methods (`entity_id` · `entity_type` · `type_default_affordances` · `display_name`). EntityBindingExt: 2 binding-side methods (`lifecycle_state` · `effective_affordances`). Phase 3 cleanup split body-vs-binding properties for cleaner dyn dispatch. See [EF_001 §4](../features/00_entity/EF_001_entity_foundation.md#4-entitykind-trait-specification). |
| **EVT-T5 Generated sub-types** (Option C redesign 2026-04-25) | 07_event_model envelope; sub-types feature-owned | future gossip aggregator owns `BubbleUp:RumorBubble`; future world-rule-scheduler owns `Scheduled:NPCRoutine` (V1+30d) + `Scheduled:WorldTick` (V1+30d); future quest-engine owns `Scheduled:QuestTrigger`; future combat owns RNG-based generators | Replaces former T9 QuestBeat:Trigger / T10 NPCRoutine / T11 WorldTick categories — all three were Generated mechanism. EVT-A9 RNG determinism applies. |
| **Generator Registry** (Phase 6 EVT-G1, 2026-04-25 late evening) | 07_event_model envelope; specific generators feature-owned | Each registered generator declared with `logical_id`=`(feature_owner:sub_type)`, `registry_uuid`=blake3(logical_id), `trigger_sources`, `output_category`, `rng_seed_strategy`, `capacity_ceiling`, `owner_service`. V1 generators (when implemented): future gossip aggregator (`gossip:RumorBubble`); future scheduler (`world-rule-scheduler:NPCRoutine`/`WorldTick`); future combat (`combat:DamageRoll`); future quest-engine (`quest:Trigger`). Coordinator role in-process per channel-writer (no new service V1) — see [EVT-G5](../07_event_model/12_generation_framework.md#evt-g5--coordinator-service-responsibilities--deployment). | Closes original-goal #4 ("generate event theo điều kiện + xác suất") at systematic level. EVT-A9 + EVT-A12 (f) operationalized. |
| `RejectReason` namespace prefixes | **PL_001 Continuum** §3.5 (envelope) | `lex.*` → WA_001, `heresy.*` → WA_002, `mortality.*` → WA_006 (provisional), `world_rule.*` → cross-cutting, `oracle.*` → 05_llm_safety A3, `canon_drift.*` → 05_llm_safety A6, `capability.*` → DP-K9, `parse.*` → PL_002, `chorus.*` → NPC_002, `forge.*` → WA_003, `charter.*` → PLT_001, `succession.*` → PLT_002, `interaction.*` → PL_005, `status.*` → PL_006, `entity.*` → EF_001 | Each feature owns its prefix; Continuum doesn't enumerate. **Path A tightening applied 2026-04-25 (commit f7c0a54).** |

---

## Stable-ID prefix ownership

Per [`../00_foundation/06_id_catalog.md`](../00_foundation/06_id_catalog.md). Reproduced here for boundary-review convenience.

| Prefix | Owner | Status |
|---|---|---|
| `DP-A*` / `DP-T*` / `DP-R*` / `DP-S*` / `DP-K*` / `DP-C*` / `DP-X*` / `DP-F*` / `DP-Ch*` | 06_data_plane (LOCKED) | locked |
| `EVT-A1..A12` / `EVT-T1`/`T3`/`T4`/`T5`/`T6`/`T8` (active) + `EVT-T2`/`T7`/`T9`/`T10`/`T11` (`_withdrawn` 2026-04-25 Option C redesign per I15) / `EVT-P1`/`P3`/`P4`/`P5`/`P6`/`P8` (active) + `EVT-P2`/`P7`/`P9`/`P10`/`P11` (`_withdrawn`) / `EVT-V1..V7` / `EVT-L1..L19` / `EVT-S1..S6` / **`EVT-G1..G6`** (Phase 6 Generation Framework, locked 2026-04-25 late evening) / `EVT-Q*` | 07_event_model | Phase 1-6 LOCKED + Option C redesign 2026-04-25 |
| `MV*` / `MV12-D*` | 03_multiverse | locked |
| `R*` / `S*` / `C*` / `SR*` | 02_storage | locked |
| `I*` (foundation invariants) | 00_foundation | locked |
| `EF-*` (foundation tier; `EF-A*` axioms · `EF-D*` deferrals · `EF-Q*` open questions) | catalog/cat_00_EF_entity_foundation.md (added 2026-04-26) | EF_001 Entity Foundation |
| `PL-*` / `WA-*` / `PO-*` / `NPC-*` / `PCS-*` / `SOC-*` / `NAR-*` / `EM-*` / `PLT-*` / `CC-*` / `DL-*` | catalog/cat_NN_*.md per category | each catalog file owns its prefix |
| `LX-D*` / `LX-Q*` | WA_001 | per-feature deferral IDs |
| `HER-D*` / `HER-Q*` | WA_002 | per-feature deferral IDs |
| `FRG-D*` / `FRG-Q*` | WA_003 | per-feature deferral IDs |
| `CHR-D*` / `CHR-Q*` | PLT_001 | per-feature deferral IDs |
| `SUC-D*` / `SUC-Q*` | PLT_002 | per-feature deferral IDs |
| `MOR-D*` / `MOR-Q*` | WA_006 | per-feature deferral IDs |
| `GR-D*` / `GR-Q*` | PL_002 | per-feature deferral IDs |
| `CST-D*` / `CST-Q*` | NPC_001 | per-feature deferral IDs |
| `CHO-D*` / `CHO-Q*` | NPC_002 | per-feature deferral IDs |

Per-feature `*-D*` / `*-Q*` IDs are deferral IDs scoped to the feature's design doc. They never collide because the prefix is feature-specific. Foundation I15 stable-ID-renaming rule applies.

---

## Drift watchpoints (cross-cutting)

These are documented mismatches that require cross-feature coordination to resolve. Each is owned by the feature that flagged it, but resolution may require boundary-folder edits.

| ID | Owner-flagger | Drift | Resolution path |
|---|---|---|---|
| **GR-D8** | PL_002 | Rejected-turn commit primitive (`t2_write` per PL_001 §15 vs `advance_turn` per EVT-T1 spec) | event-model agent Phase 2 to absorb per-outcome sub-spec |
| **CST-D1** | NPC_001 | `npc.current_session_id` semantic (R8 wording vs OOS-1 in DP); also see EF-Q2 — npc.current_region_id may migrate to entity_binding post-EF_001 | reconcile with 02_storage agent + EF_001 review |
| **LX-D5** | WA_001 | Lex slot ordering in EVT-V* | event-model agent Phase 3 |
| **EF-Q3** | EF_001 | Validator slot ordering: EVT-V_entity_affordance vs EVT-V_lex (structural-before-semantic suggests entity first) | `_boundaries/03_validator_pipeline_slots.md` alignment update |
| **HER-D8** | WA_002 | EVT-T11 WorldTick V1+30d activation | event-model agent Phase 4 |
| **HER-D9** | WA_002 | LexSchema v1→v2 migration sequencing | implementation phase ops |
| **CHR-D9** | PLT_001 | Cross-reality `meta_user_pending_invitations` table | platform infrastructure |
| **WA_006 over-extension** | boundary review 2026-04-25 | 5 sections of WA_006 belong to PCS_001 / 05_llm_safety / PL_001 | rewrite WA_006 when feature owners take over |
| **B2 RealityManifest envelope** | boundary review 2026-04-25 | No single owner of the manifest schema | propose IF_001_reality_manifest.md (deferred) |

---

## Adding a new entry

When a new feature is designed:
1. Lock-claim `_boundaries/_LOCK.md`
2. Add the feature's owned aggregates to "Aggregate ownership"
3. If the feature extends a shared schema: add to "Schema / envelope ownership" + update `02_extension_contracts.md`
4. If the feature adds a validator slot: update `03_validator_pipeline_slots.md`
5. If the feature uses a new stable-ID prefix: add to "Stable-ID prefix ownership"
6. Append a row to `99_changelog.md`
7. Lock-release

---

## When ownership changes

Aggregate transfers are RARE (most aggregates stay with their original owner). When they happen (e.g., WA_006's `pc_mortality_state` will move to PCS_001):
1. Lock-claim
2. Update the matrix entry: change Owner, mark date of transfer, add reason
3. Update both feature design docs (giving + receiving)
4. Append a row to `99_changelog.md` with full transfer details
5. Lock-release
