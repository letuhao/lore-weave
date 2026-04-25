# 00_map — Index

> **Category:** MAP — Map Foundation (foundation tier; sibling of EF_001 + PF_001; precedes domain feature folders)
> **Catalog reference:** [`catalog/cat_00_MAP_map_foundation.md`](../../catalog/cat_00_MAP_map_foundation.md) (owns `MAP-*` stable-ID namespace)
> **Purpose:** Defines the visual graph layer for the world's map UI (Tiên Nghịch / EVE Online / Stellaris pattern — node-link drill-down). Owns the `map_layout` aggregate per channel, position + tier metadata for non-cell tiers, image asset slots (V1 schema; V1+ pipeline), graph connections at non-cell tiers with distance + canonical Travel duration. Composes with PF_001 at cell tier (PF_001 owns place semantic + cell ConnectionDecl; MAP_001 owns cell visual layer + non-cell connections).

**Active:** MAP_001 — **Map Foundation** (DRAFT 2026-04-26 — Option C max scope)

**Folder closure status:** Open — DRAFT 2026-04-26. CANDIDATE-LOCK pending Phase 3 review cleanup + closure pass + downstream updates (PL_001 §13 + §16.2 reopen confirm + demo `_ui_drafts/MAP_GUI_v2.html` update with distance labels).

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| MAP_001 | **Map Foundation** (MAP) | Visual graph foundation: `map_layout` aggregate (T2/Channel; covers all tiers) + ChannelTier 5-variant closed enum + author-positioned absolute (x, y) within parent viewport + Option<TierMetadata> conditional schema (Some non-cell, None cell — PF_001 supplies) + 5-variant MapConnectionKind matching PF_001 + distance_units (canonical abstract leagues) + default_fiction_duration (OnFoot baseline; V1+ TVL_001 method matrix) + 3 image asset slots (icon/background/inline_artwork; V1 schema with V1+ pipeline phased rollout: AuthorUploaded V1+30d, PlayerUploaded V1+60d, LlmGenerated V2+) + 4-variant AssetSource closed enum + 3-variant AssetReviewState. Owns `map.*` RejectReason namespace (10 V1 rule_ids + 3 V1+ reservations). 10 V1-testable acceptance scenarios (AC-MAP-1..10) + 14 deferrals (MAP-D1..D14) + 5 open questions (MAP-Q1..Q5). | DRAFT 2026-04-26 | [`MAP_001_map_foundation.md`](MAP_001_map_foundation.md) | (this commit) |

---

## Kernel touchpoints (shared with MAP features)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on T2/Channel aggregates; DP-Ch* channel hierarchy underlies the per-tier map drill-down
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types `aggregate_type=map_layout`; EVT-T4 System `LayoutBorn` sub-type; EVT-T8 Administrative `Forge:EditMapLayout` sub-shape
- `_boundaries/01_feature_ownership_matrix.md` — `map_layout` owned by MAP_001 (added 2026-04-26)
- `_boundaries/02_extension_contracts.md` §1.4 — `map.*` RejectReason namespace prefix added 2026-04-26
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension `map_layout: Vec<MapLayoutDecl>` + `travel_defaults: TravelDefaults` added 2026-04-26
- `00_place/PF_001_place_foundation.md` — composes at cell tier (PF_001 cell ConnectionDecl unchanged; MAP_001 supplies cell visual layer)
- `04_play_loop/PL_001_continuum.md` §13 Travel + §16.2 RealityManifest activation — light reopen this commit to consume MAP_001 default_fiction_duration

---

## Naming convention

`MAP_<NNN>_<short_name>.md`. Sequence per-category. MAP_001 is the foundation; future MAP_NNN if cross-cutting map concerns arise (e.g., MAP_002 Asset Pipeline V1+30d, MAP_003 Multi-hop Pathfinding V1+30d).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

MAP_001 is foundational — every domain feature folder that visualizes places depends on MAP_001 contracts. Boundary discipline:
- Place semantic identity (PlaceType / StructuralState / fixtures) stays in PF_001
- Entity locations stay in EF_001 entity_binding
- Map visual layer (position + image asset slots + non-cell connections) stays in MAP_001
- Travel mechanics (speed/method matrix) stays in future TVL_001 V1+
- Asset pipeline (upload + LLM-gen) stays in future MAP_002 V1+

Three foundation features (EF_001 + PF_001 + MAP_001) compose cleanly without overlap; MAP_001 is the visual layer that completes the foundation tier for V1 spawn-readiness.

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) requires update post-MAP_001 LOCK to add §4.4e mandatory MAP_001 reading. Update scheduled at MAP_001 CANDIDATE-LOCK promotion (not in this DRAFT commit).

PL_005 Interaction §V1-kinds may want extension to add `ExamineTarget = Entity(EntityId) | Place(PlaceId) | MapNode(ChannelId)` discriminator (MAP-Q3 watchpoint) — V1+ if author content needs to "examine the country/continent".
