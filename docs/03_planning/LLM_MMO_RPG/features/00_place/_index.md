# 00_place — Index

> **Category:** PF — Place Foundation (foundation tier; sibling of EF_001 Entity Foundation; precedes domain feature folders)
> **Catalog reference:** [`catalog/cat_00_PF_place_foundation.md`](../../catalog/cat_00_PF_place_foundation.md) (owns `PF-*` stable-ID namespace)
> **Purpose:** Defines what counts as a meaningful in-fiction location. Owns the `place` aggregate (T2/Channel-cell), `PlaceType` closed enum (10 V1 kinds), connection graph (DP-hierarchy implicit + explicit horizontal edges), 4-state StructuralState machine for in-fiction degradation, fixture-seed declarations for canonical EnvObjects, and time-lapse evolution hooks (author-edit + in-fiction event V1; scheduled decay V1+30d).

**Active:** none (folder closure pass 2026-04-26 — PF_001 at CANDIDATE-LOCK)

**Folder closure status:** **CLOSED for V1 design 2026-04-26.** PF_001 at CANDIDATE-LOCK with §15 acceptance criteria walked (10 scenarios; 4 precision-tightened post Phase-3) + Phase 3 review cleanup applied (Severity 1+2+3, 14 fixes) + downstream-impact tracked (PCS_001 brief §4.4d update at next agent spawn; PL_005 ExamineTarget extension at PL_005 closure pass). LOCK pending integration tests. No further design work in PF folder until V2+ extensions (multi-place per cell PF-D4 / scheduled decay PF-D3 / procedural place generation PF-D7) or new sibling PF features open new design threads.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| PF_001 | **Place Foundation** (PF) | Semantic place substrate: `place` aggregate (T2/Channel-cell, 1:1 with cell channels; PlaceId newtype with From/Into ChannelId) + 10-variant PlaceType closed enum + 5-variant ConnectionKind + Vec<ConnectionDecl> hybrid connection graph (bidirectional hint-only V1) + 4-state StructuralState machine with cascade-only-on-Destroyed rule + 4-step cascade ordering (place delta → PlaceDestroyed signal → consumer cascades → cell-resident cascade) + 11-variant EnvObjectKind closed enum + fixture-seed split (author-declared EnvObjectSeedDecl vs materialized EnvObjectSeed; world-service computes seed_uid) + RealityManifest `places: Vec<PlaceDecl>` REQUIRED extension + author-edit/in-fiction-event/V1+30d-scheduler time-lapse hooks. Owns `place.*` RejectReason namespace (12 V1 rule_ids + 4 V1+ reservations) + dedicated EVT-T3 `PlaceDestroyed` cascade-trigger sub-shape. 10 V1-testable acceptance scenarios (AC-PF-1..10; 4 precision-tightened post Phase-3) + 14 deferrals (PF-D1..D14) + 5 open questions (PF-Q1..Q5). | **CANDIDATE-LOCK 2026-04-26** | [`PF_001_place_foundation.md`](PF_001_place_foundation.md) | 0a967bb → eec8d5b → closure (this commit) |

---

## Kernel touchpoints (shared with PF features)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on T2/Channel-cell aggregates; DP-Ch* channel hierarchy provides parent/child traversal underlying place connection graph
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types `aggregate_type=place`; EVT-T4 System `PlaceBorn` sub-type; EVT-T8 Administrative `Forge:EditPlace` sub-shape
- `_boundaries/01_feature_ownership_matrix.md` — `place` owned by PF_001 (added 2026-04-26)
- `_boundaries/02_extension_contracts.md` §1.4 — `place.*` RejectReason namespace prefix added 2026-04-26
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension `places: Vec<PlaceDecl>` added 2026-04-26
- `00_entity/EF_001_entity_foundation.md` §6.1 — cascade rules (Place → Destroyed propagates into EnvObjects + Items via HolderCascade reason_kind)

---

## Naming convention

`PF_<NNN>_<short_name>.md`. Sequence per-category. PF_001 is the foundation; future PF_NNN if cross-cutting place concerns arise (e.g., V1+ multi-place-per-cell, V1+ procedural place generation).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

PF_001 is foundational — every domain feature folder that references "where" depends on PF_001 contracts. Boundary discipline: place semantic identity stays in PF_001; runtime ambient stays in PL_001 scene_state; entity locations stay in EF_001 entity_binding. Three aggregates per cell, three concerns, no overlap.

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) requires update post-PF_001 LOCK to add §4.4d mandatory PF_001 reading + IN-scope clause "PC spawn cell MUST reference valid PlaceId per PF_001 invariant". Update scheduled at PF_001 CANDIDATE-LOCK promotion (not in this DRAFT commit).

PL_005 Interaction §V1-kinds requires extension to add `ExamineTarget = Entity(EntityId) | Place(PlaceId)` discriminator. PL_005 is currently DRAFT — closure pass for PL_005 should fold this in.
