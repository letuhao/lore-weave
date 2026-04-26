<!-- CHUNK-META
source: design-track manual seed 2026-04-27
chunk: cat_00_ACT_actor_foundation.md
namespace: ACT-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## ACT — Actor Foundation (foundation tier; Tier 5 Actor Substrate; unified per-actor substrate replacing NPC_001 R8 anomaly)

> Foundation-level catalog. Owns `ACT-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `ACT-A*` | Axioms (locked invariants) |
> | `ACT-D*` | Per-feature deferrals (V1+ / V2 phases) |
> | `ACT-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**ACT-A1 (Per-actor unified pattern):** All ACT_001 aggregates keyed by ActorId (or composite (ActorId, _) for relationship/session). NO per-NPC-only or per-PC-only ACT_001 aggregates V1. Pattern matches all Tier 5 substrate features (IDF + FF + FAC + REP + PROG + RES + PL_006). Resolves NPC_001 R8 import anomaly.

**ACT-A2 (3-layer architectural model):** L1 Identity (always present), L2 Capability/Kind (stable; encoded in ActorId variant), L3 Control source (dynamic; sparse aggregate population). Layer assignment determines storage density. Future-proofs AI-controls-PC-offline V1+ via L3 dynamic transition.

**ACT-A3 (`actor_core` always present post-creation):** Every non-Synthetic actor has `actor_core` row from creation event onward. Read fallback: missing row = creation event not yet processed (transient; not "default Neutral" semantics). Synthetic actors have NO `actor_core` row V1.

**ACT-A4 (`actor_chorus_metadata` sparse — control-source-driven population):** Row populated ONLY when actor's current control source = AI. V1: NPCs always have row (always AI); PCs never have row (always User-controlled V1). V1+ AI-controls-PC-offline: PCs populate row when offline; row removed/inactive when online.

**ACT-A5 (`actor_actor_opinion` bilateral):** Per-(observer_actor, target_actor) opinion stored. Observer ≠ target enforced (Stage 0 schema reject `actor.opinion_self_target_forbidden`). V1 active patterns: NPC→PC (preserved from npc_pc_relationship_projection); V1+ patterns: PC→NPC + NPC→NPC + PC→PC. Symmetry NOT enforced — separate rows per direction; values may differ.

**ACT-A6 (`actor_session_memory` per-(actor, session)):** Memory facts scoped to specific session; supports LLM context continuity. V1: NPCs populated; V1+ AI-controls-PC-offline: PCs populated when offline.

**ACT-A7 (Synthetic actor forbidden V1):** Universal substrate discipline (matches IDF + FF + FAC + REP + PROG + RES + PL_006). Reject `actor.synthetic_actor_forbidden` Stage 0 schema for ChorusOrchestrator/BubbleUpAggregator/etc.

**ACT-A8 (Cross-reality strict V1):** Reality boundaries enforced V1; V2+ Heresy migration via WA_002 (universal V2+ deferral pattern).

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| ACT-1 | `actor_core` aggregate (T2/Reality, ALWAYS PRESENT post-creation; identity layer L1) | ✅ | V1 | EF-1 (ActorId), DP-A14 | [ACT_001 §3.1](../features/00_actor/ACT_001_actor_foundation.md#31-actor_core-t2--reality-scope--primary-always-present) |
| ACT-2 | `actor_chorus_metadata` aggregate (T2/Reality, sparse — AI-drive metadata; L3 control state) | ✅ | V1 | ACT-1, EF-1 | [ACT_001 §3.2](../features/00_actor/ACT_001_actor_foundation.md#32-actor_chorus_metadata-t2--reality-scope--sparse-ai-drive-metadata) |
| ACT-3 | `actor_actor_opinion` aggregate (T2/Reality, sparse bilateral — per-(observer, target); L3 relationship) | ✅ | V1 | ACT-1, EF-1 | [ACT_001 §3.3](../features/00_actor/ACT_001_actor_foundation.md#33-actor_actor_opinion-t2--reality-scope--sparse-bilateral) |
| ACT-4 | `actor_session_memory` aggregate (T2/Reality, per-(actor, session); L3 LLM context; bounded R8-L2) | ✅ | V1 | ACT-1, EF-1 | [ACT_001 §3.4](../features/00_actor/ACT_001_actor_foundation.md#34-actor_session_memory-t2--reality-scope--per-session) |
| ACT-5 | `ActorMood` type (renamed from NpcMood; -100..+100; kind-agnostic) | ✅ | V1 | ACT-1 | [ACT_001 §3.1](../features/00_actor/ACT_001_actor_foundation.md#31-actor_core-t2--reality-scope--primary-always-present) |
| ACT-6 | `DesireDecl` type (renamed from NpcDesireDecl; kind-agnostic; NPC_003 ownership transfer) | ✅ | V1 | ACT-2, NPC_003 | [ACT_001 §3.2](../features/00_actor/ACT_001_actor_foundation.md#32-actor_chorus_metadata-t2--reality-scope--sparse-ai-drive-metadata) |
| ACT-7 | EVT-T4 System sub-types — `ActorBorn` + `ActorChorusMetadataBorn` (canonical seed) | ✅ | V1 | EVT-A11, ACT-1, ACT-2 | [ACT_001 §2.5](../features/00_actor/ACT_001_actor_foundation.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| ACT-8 | EVT-T8 AdminAction sub-shapes — `Forge:EditActorCore` + `Forge:EditChorusMetadata` + `Forge:EditActorOpinion` + `Forge:EditActorSessionMemory` | ✅ | V1 | ACT-1..4, WA-3 (forge_audit_log) | [ACT_001 §2.5](../features/00_actor/ACT_001_actor_foundation.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| ACT-9 | EVT-T3 Derived sub-types — `aggregate_type=actor_actor_opinion` Update + `aggregate_type=actor_session_memory` Update (preserved from NPC_001 §13 session-end derivation) | ✅ | V1 | EVT-A11, ACT-3, ACT-4 | [ACT_001 §2.5](../features/00_actor/ACT_001_actor_foundation.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| ACT-10 | RealityManifest CanonicalActorDecl extension (chorus_metadata fields additive) | ✅ | V1 | ACT-2, EF-1 | [ACT_001 §11](../features/00_actor/ACT_001_actor_foundation.md#11-sequence-canonical-seed-wuxia-4-npcs--1-pc) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| ACT-11 | RejectReason `actor.*` namespace (6 V1 rules + 3 V1+ reservations) | ✅ | V1 | RES-* (i18n contract) | [ACT_001 §9](../features/00_actor/ACT_001_actor_foundation.md#9-failure-mode-ux) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| ACT-12 | 3-layer architectural model (L1 Identity + L2 Capability/Kind + L3 Control source) | ✅ | V1 | ACT-1..4 | [ACT_001 §1](../features/00_actor/ACT_001_actor_foundation.md#1-user-story-npc_001-unification--future-proofing-ai-controls-pc-offline-v1) |
| ACT-13 | NPC_001 closure-pass-extension (3 aggregates ownership transfer; persona assembly §6 update; `npc_node_binding` KEPT) | ✅ | V1 | ACT-1..4, R8 | (commit 3/5) |
| ACT-14 | NPC_002 closure-pass-extension (read paths updated; ActorOpinion::for_target replaces NpcOpinion::for_pc) | ✅ | V1 | ACT-1, ACT-3 | (commit 3/5) |
| ACT-15 | NPC_003 closure-pass-extension (desires field ownership transfer; type rename) | ✅ | V1 | ACT-2, NPC_003 | (commit 3/5) |
| ACT-16 | 02_storage R08 update (schema split + rename; main session attribution; additive) | ✅ | V1 | R8 | (commit 3/5) |

### Per-feature deferrals (ACT-D*)

| Deferral | Description | Phase |
|---|---|---|
| ACT-D1 | V1+ AI-controls-PC-offline feature activation — populates actor_chorus_metadata for offline PCs | V1+ when feature ships |
| ACT-D2 | V1+ PC↔NPC bilateral opinion runtime population — activates with AI-controls-PC-offline | V1+ runtime opinion milestone |
| ACT-D3 | V1+ NPC↔NPC opinion (sect rivalry drama) — bilateral pattern enables sect drama feature | V1+ when concrete |
| ACT-D4 | V1+ PC↔PC opinion (multi-PC realities) — multiplayer feature activation | V1+ when concrete |
| ACT-D5 | V1+ NPC xuyên không (currently PC-only V1 via PCS_001 body_memory) | V1+ when concrete |
| ACT-D6 | V2+ cross-reality migration via WA_002 Heresy | V2+ |
| ACT-D7 | V1+ canon-drift detector integration (A6 + actor_core knowledge_tags + actor_session_memory) | V1+ enrichment |
| ACT-D8 | V1+ NPC_003 desires lifecycle events (currently author-only via Forge V1) | V1+ when concrete |
| ACT-D9 | V1+ actor_chorus_metadata schema enrichment (additional AI-drive metadata as features ship) | V1+ additive |
| ACT-D10 | V1+ unified node_binding (currently NPC-only npc_node_binding; PC offline V1+ may consolidate) | V1+ when AI-controls-PC-offline ships |

### Open questions (ACT-Q*)

NONE V1. All Q1-Q6 LOCKED via main session deep-dive 2026-04-27 (2 REVISIONS — Q3 REVISION on AI-controls-PC-offline insight + Q6 user-revised to full unify all 3 opportunities).

### Cross-feature integration map

| Feature | Direction | Integration |
|---|---|---|
| EF_001 Entity Foundation | ACT_001 reads | ActorId source-of-truth (sibling pattern §5.1); ActorKind discrimination |
| 02_storage R08 | ACT_001 updates | Schema split: npc → actor_core + actor_chorus_metadata; rename npc_session_memory → actor_session_memory; rename npc_pc_relationship_projection → actor_actor_opinion bilateral |
| RES_001 Resource | ACT_001 reads | I18nBundle pattern (§2.3) for display strings + reject user_message |
| WA_003 Forge | ACT_001 reuses | forge_audit_log pattern (3-write atomic for 4 EVT-T8 sub-shapes) |
| 07_event_model EVT-A10 | ACT_001 conforms | Event log = universal SSOT; no separate actor_event_log aggregate |
| NPC_001 Cast | ACT_001 RESOLVES | R8 import anomaly (3 aggregates per-NPC → per-actor unified) |
| NPC_002 Chorus | ACT_001 consumed by | Chorus reads actor_core + actor_chorus_metadata + actor_actor_opinion for priority Tier 2-3 |
| NPC_003 NPC Desires | ACT_001 RESOLVES | desires field ownership transfer (npc.desires → actor_chorus_metadata.desires; type rename) |
| PCS_001 PC Substrate | ACT_001 consumed by V1+ | Builds on ACT_001 stable base; owns pc_user_binding + pc_mortality_state + pc_stats_v1_stub |
| AI-controls-PC-offline V1+ | ACT_001 consumed by V1+ | Activates actor_chorus_metadata PC population (ACT-D1); read flow same as NPCs |
| Multi-PC realities V1+ | ACT_001 consumed by V1+ | Bilateral actor_actor_opinion supports PC↔PC dynamics (ACT-D4) |
| Sect rivalry NPC↔NPC drama V1+ | ACT_001 consumed by V1+ | Bilateral actor_actor_opinion supports NPC↔NPC opinion (ACT-D3) |
| A6 canon-drift detector V1+ | ACT_001 consumed by V1+ | Reads actor_core knowledge_tags + actor_session_memory facts for drift detection (ACT-D7) |
| REP_001 Reputation | (independent) | REP_001 reads actor_core for actor identity; per-(actor, faction) reputation independent of ACT_001 substrate |
| PROG_001 Progression | (independent) | PROG_001 reads actor_core for actor identity; tracking_tier field on PROG_001 (NPC tier semantics) independent |
