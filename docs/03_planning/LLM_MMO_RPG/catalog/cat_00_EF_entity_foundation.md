<!-- CHUNK-META
source: design-track manual seed 2026-04-26
chunk: cat_00_EF_entity_foundation.md
namespace: EF-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## EF — Entity Foundation (foundation tier; precedes domain feature catalogs)

> Foundation-level catalog. Owns `EF-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `EF-A*` | Axioms (locked invariants) |
> | `EF-D*` | Per-feature deferrals |
> | `EF-Q*` | Open questions |

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| EF-1 | EntityId 4-variant sum type (Pc / Npc / Item / EnvObject) | ✅ | V1 | — | [EF_001 §5](../features/00_entity/EF_001_entity_foundation.md#5-entityid-taxonomy--id-format) |
| EF-2 | `entity_binding` aggregate (T2 / Reality) — unified spatial presence with 4-state LocationKind | ✅ | V1 | EF-1, PL-1 | [EF_001 §3.1](../features/00_entity/EF_001_entity_foundation.md#31-entity_binding-t2--reality--primary) |
| EF-3 | `entity_lifecycle_log` aggregate (T2 / Reality, append-only) — per-entity audit trail | ✅ | V1 | EF-1 | [EF_001 §3.2](../features/00_entity/EF_001_entity_foundation.md#32-entity_lifecycle_log-t2--reality-append-only) |
| EF-4 | EntityKind trait spec (5 methods incl. type_default_affordances required) | ✅ | V1 | EF-1, EF-2 | [EF_001 §4](../features/00_entity/EF_001_entity_foundation.md#4-entitykind-trait-specification) |
| EF-5 | LifecycleState 4-state machine (Existing / Suspended / Destroyed / Removed) + allowed/forbidden transitions | ✅ | V1 | EF-2 | [EF_001 §6](../features/00_entity/EF_001_entity_foundation.md#6-lifecyclestate-state-machine) |
| EF-6 | AffordanceFlag closed enum (6 V1 flags: BeSpokenTo / BeStruck / BeExamined / BeGiven / BeReceived / BeUsed) + per-type defaults | ✅ | V1 | EF-1, EF-4 | [EF_001 §7](../features/00_entity/EF_001_entity_foundation.md#7-affordanceflag-closed-enum--enforcement) |
| EF-7 | Reference safety: hard-reject default + per-kind soft-override (Examine tolerates Destroyed) | ✅ | V1 | EF-5, EF-6 | [EF_001 §8](../features/00_entity/EF_001_entity_foundation.md#8-reference-safety-policy) |
| EF-8 | `entity.*` RejectReason namespace (7 rule_ids V1) | ✅ | V1 | EF-7 | [EF_001 §8](../features/00_entity/EF_001_entity_foundation.md#8-reference-safety-policy) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| EF-9 | EVT-V_entity_affordance validator slot (runs before per-kind validator chain) | ✅ | V1 | EF-6, EF-8 | [EF_001 §11](../features/00_entity/EF_001_entity_foundation.md#11-subscribe-pattern) |
| EF-10 | actor_binding → entity_binding rename (transfer from PL_001 §3.6) | ✅ | V1 | EF-2 | [EF_001 §1, §3.1, §16](../features/00_entity/EF_001_entity_foundation.md) + PL_001 reopen |
| EF-11 | EntityId variants V1+ extension (Vehicle / Spirit / Building / Quest / Channel) | 📦 | V2+ | EF-1 | [EF_001 §15 EF-D1](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-12 | AffordanceFlag V1+ extensions (BeCollidedWith / BeShotAt / BeCastAt / BeEmbraced / BeThreatened / BeTraveledTo / BeContainedIn) | 📦 | V1+ | EF-6 | [EF_001 §15 EF-D2](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-13 | EntityLocation::InContainer enforcement (requires Item feature + BeContainedIn affordance) | 📦 | V1+ | EF-2, EF-12 | [EF_001 §15 EF-D3](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-14 | EVT-T6 Proposal `EntitySpawnProposal` (LLM-suggested entity creation; author-review gate) | 📦 | V2+ | EF-1 | [EF_001 §15 EF-D5](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-15 | Cross-reality entity references (multiverse portals) | 📦 | V2+ | EF-1, multiverse | [EF_001 §15 EF-D6](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-16 | Hidden/fog-of-war 5th lifecycle state | 📦 | V1+ | EF-5 | [EF_001 §15 EF-D7](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-17 | Full ECS component registry | 📦 | V2+ | EF-4 | [EF_001 §15 EF-D8](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
| EF-18 | Per-affordance grant policy (e.g., be_spoken_to requires shared language) | 📦 | V1+ | EF-6 | [EF_001 §15 EF-D9](../features/00_entity/EF_001_entity_foundation.md#15-deferrals) |
