# 00_cell_scene — Index

> **Category:** CSC — Cell Scene Composition (foundation tier; sibling of EF_001 + PF_001 + MAP_001; 4th and final V1 foundation feature)
> **Catalog reference:** [`catalog/cat_00_CSC_cell_scene_composition.md`](../../catalog/cat_00_CSC_cell_scene_composition.md) (owns `CSC-*` stable-ID namespace)
> **Purpose:** The 4-layer composition pipeline that turns a cell-tier place into a renderable in-scene UI. Layer 1 hand-authored skeleton template + Layer 2 seed-driven procedural fixture placement + Layer 3 LLM categorical zone-assignment for occupants (optional with canonical fallback) + Layer 4 LLM creative narration (optional). Architecture validated by demo evidence at `_ui_drafts/CELL_SCENE_v1..v4` — v3 LLM-as-grid-generator failed (32K reasoning tokens, 0 outputs); v4 LLM-as-zone-classifier succeeded (2.5K total tokens, all entities placed correctly).

**Active:** none (folder closure pass 2026-04-26 — CSC_001 at CANDIDATE-LOCK)

**Folder closure status:** **CLOSED for V1 design 2026-04-26.** CSC_001 at CANDIDATE-LOCK with §16 acceptance criteria walked (11 scenarios; 0 rule_id mismatches at closure — Phase 3 cleanup proactively aligned) + Phase 3 review cleanup applied (Severity 1+2+3, 13 fixes incl. lazy-cell creation bug fix S2.5) + downstream-impact tracked. LOCK pending integration tests. No further design work in CSC folder until V2+ extensions (per-PlaceType skeleton libraries / Asset Pipeline integration / multi-locale narration) or new sibling CSC features open new design threads.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| CSC_001 | **Cell Scene Composition** (CSC) | 4-layer composition pipeline: hand-authored skeleton templates (3 V1 Tavern + 1 default_generic_room fallback) + seeded procedural fixture placement (Counter/Table/Chair/Fireplace/Window; deterministic via blake3 seed + ChaCha8Rng) + LLM zone-assignment categorical decision (4 validators + 3-retry feedback loop + per-entity fallback chain via `fallback_chain_for` + canonical default fallback + PC race policy) + LLM Vietnamese xianxia narration (free-form; in-memory LRU cache; best-effort replay V1). Owns `cell_scene_layout` aggregate (T2/Channel-cell). Replaces architecturally-flawed LLM-as-grid-generator approach (v3 evidence: 30K reasoning tokens / 0 successful outputs) with bounded layered fallback chains. Owns `csc.*` RejectReason namespace (9 V1 rule_ids + 4 V1+ reservations after Phase 3 + closure). 11 V1-testable acceptance scenarios (AC-CSC-1..11) + 13 deferrals (CSC-D1..D13) + 5 open questions (CSC-Q1..Q5). | **CANDIDATE-LOCK 2026-04-26** | [`CSC_001_cell_scene_composition.md`](CSC_001_cell_scene_composition.md) | 23b03d9 → 7750465 → closure (this commit) |

---

## Kernel touchpoints (shared with CSC features)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on T2/Channel-cell aggregates
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types `aggregate_type=cell_scene_layout`; EVT-T4 System `SceneLayoutBorn` sub-type; EVT-T8 Administrative `Forge:EditCellScene` sub-shape
- `_boundaries/01_feature_ownership_matrix.md` — `cell_scene_layout` owned by CSC_001 (added 2026-04-26)
- `_boundaries/02_extension_contracts.md` §1.4 — `csc.*` RejectReason namespace prefix added 2026-04-26
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension `scene_skeleton_overrides: HashMap<ChannelId, SkeletonId>` added 2026-04-26
- `00_place/PF_001_place_foundation.md` — PF_001 `place.place_type` consumed for skeleton selection; cell-tier 1:1 invariant inherited
- `00_entity/EF_001_entity_foundation.md` — EF_001 `entity_binding WHERE cell_id` consumed for occupant list
- `00_map/MAP_001_map_foundation.md` — MAP_001 `map_layout.background_asset` (V1+) renders under cell scene
- `04_play_loop/PL_001b_continuum_lifecycle.md` — §16.3 lazy cell creation must also create `cell_scene_layout` (light reopen this commit)
- `_ui_drafts/CELL_SCENE_v1..v4` — design evidence (architectural pivot trajectory)

---

## Naming convention

`CSC_<NNN>_<short_name>.md`. Sequence per-category. CSC_001 is the foundation; future CSC_NNN if cross-cutting cell-scene concerns arise (V1+: per-PlaceType skeleton libraries / asset pipeline integration / multi-locale narration).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

CSC_001 is the **4th and final V1 foundation feature** — completes the foundation tier covering: WHO (EF_001), WHERE-semantic (PF_001), WHERE-visual-graph (MAP_001), WHAT-inside-cell (CSC_001).

Boundary discipline:
- Cell-internal grid composition + layer pipeline stays in CSC_001
- Cross-tier visual graph stays in MAP_001
- Place semantic identity stays in PF_001
- Entity addressability stays in EF_001

Four foundations compose cleanly without overlap; CSC_001 is the visual rendering layer that makes the foundation tier complete for V1 spawn-readiness.

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) requires update post-CSC_001 LOCK to add §4.4f mandatory CSC_001 reading + IN-scope clause "PC spawn cell triggers `cell_scene_layout` lazy creation per CSC_001 §15.1". Update scheduled at CSC_001 CANDIDATE-LOCK promotion (not in this DRAFT commit).
