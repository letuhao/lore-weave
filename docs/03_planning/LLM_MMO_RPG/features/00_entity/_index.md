# 00_entity — Index

> **Category:** EF — Entity Foundation (foundation tier; precedes domain feature folders)
> **Catalog reference:** [`catalog/cat_00_EF_entity_foundation.md`](../../catalog/cat_00_EF_entity_foundation.md) (owns `EF-*` stable-ID namespace)
> **Purpose:** Defines what counts as an addressable thing in the world. Owns the unified `EntityId` taxonomy (Pc / Npc / Item / EnvObject), spatial presence (`entity_binding`, transferred from PL_001 actor_binding), lifecycle state machine, affordance enum, and the `EntityKind` trait. Every aggregate body that consumers (PCS_001 / NPC_001 / future Item / future EnvObject) want addressable as an Entity MUST implement EntityKind.

**Active:** EF_001 — **Entity Foundation** (DRAFT 2026-04-26 — Option C max scope)

**Folder closure status:** Open — DRAFT 2026-04-26. CANDIDATE-LOCK pending §15 acceptance verification + downstream rename completion + PCS_001 brief update.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| EF_001 | **Entity Foundation** (EF) | Unified entity substrate: `EntityId` 4-variant sum type (Pc/Npc/Item/EnvObject) + `entity_binding` aggregate (transferred from PL_001 §3.6) + `entity_lifecycle_log` append-only audit + 4-state LifecycleState machine + 6 V1 AffordanceFlag closed enum + EntityKind trait spec + hard-reject + per-kind soft-override reference safety. Owns `entity.*` RejectReason namespace. 10 acceptance scenarios + 9 deferrals (EF-D1..D9). | DRAFT 2026-04-26 | [`EF_001_entity_foundation.md`](EF_001_entity_foundation.md) | (this commit) |

---

## Kernel touchpoints (shared with EF features)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on T2/Reality aggregates; DP-A18 cell-channel MemberJoined/Left emitted around lifecycle transitions
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types `aggregate_type=entity_binding` + `aggregate_type=entity_lifecycle_log`; EVT-T4 System `EntityBorn` sub-type
- `_boundaries/01_feature_ownership_matrix.md` — `entity_binding` owned by EF_001 (transfer 2026-04-26 from PL_001) + `entity_lifecycle_log` new
- `_boundaries/02_extension_contracts.md` §1.4 — `entity.*` RejectReason namespace prefix added 2026-04-26
- `_boundaries/03_validator_pipeline_slots.md` — new EVT-V_entity_affordance slot (alignment update needed)

---

## Naming convention

`EF_<NNN>_<short_name>.md`. Sequence per-category. EF_001 is the foundation; future EF_NNN if cross-cutting entity concerns arise (e.g., entity-component registry V2+).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

EF_001 is foundational — every domain feature folder (04_play_loop / 05_npc_systems / 06_pc_systems / future Item folder / future EnvObject folder) depends on EF_001 contracts. Boundary discipline: aggregate body (Pc / Npc / Item / EnvObject) stays in the owning feature folder; EF_001 owns the trait + the cross-entity primitives only.

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) requires update post-EF_001 lock to add EF_001 to required reading + specify "implement `EntityKind for Pc`" in IN-scope §S section. Update scheduled at EF_001 CANDIDATE-LOCK promotion (not in this DRAFT commit).
