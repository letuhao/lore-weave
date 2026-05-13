# 00_tilemap — Index

> **Category:** TMP — Tilemap Foundation (foundation tier; sibling of MAP_001 + CSC_001 + EF_001 + PF_001; procedural-generation visual layer)
> **Catalog reference:** [`cat_00_TMP_tilemap_foundation.md`](../../catalog/cat_00_TMP_tilemap_foundation.md) (owns `TMP-*` stable-ID namespace)
> **Purpose:** Defines the procedural-generation visual layer for the world map. **MAP_001** = author-positioned graph (logical, abstract). **TMP_001** = procedurally-generated tilemap (visual, zoomable). **CSC_001** = cell interior (16×16 fully-composed scene). The 3 layers compose to give continent → cell drill-down with consistent procedural style.
> **Genre prior art surveyed:** Heroes of Might and Magic III (1999, NWC), Battle for Wesnoth (open source), Civilization V/VI (Firaxis), Dwarf Fortress (Bay 12), Caves of Qud (Freehold), VCMI (GPL v2+, open-source HoMM3 reimpl). See [TMP_001 §1.1](TMP_001_tilemap_foundation.md) for the genre survey + LoreWeave-specific design choices.
> **Graduated from:** [`features/_spikes/SPIKE_03_tilemap_world_view.md`](../_spikes/SPIKE_03_tilemap_world_view.md) (DRAFT 2026-04-27).

**Active:** none (folder closure pass 2026-05-13 — all 9 docs at CANDIDATE-LOCK).

**Folder closure status:** **CLOSED for V1+30d design 2026-05-13.** 9 docs at CANDIDATE-LOCK: TMP_001 foundation + TMP_002 zone placement + TMP_003 pipeline + TMP_004 template authoring + TMP_005 biome + TMP_006 treasure (Phase 3 finding: §8.5 questions restored — were lost in license-hygiene revision pass) + TMP_007 connections + TMP_008 LLM integration architecture + TMP_008b LLM contract spec. **Closure pass deliverables**: §15 AC-TMP-1..10 walked + expanded (setup / action / expected outcome triples with concrete rule_ids + event types); all 43 open questions RESOLVED (40 batch-accept-default + 3 user-locked: TMP-Q3 V2 default LLM-on / TMP-Q4 Phaser 3 FE engine / TMP-LLM-Q4 cross-zone L4 context YES with cost bump); Phase 3 review surfaced `tilemap.density_reduced` info-level rule_id missing from §9.2 inventory (added — 17 V1+30d rule_ids now, was 16); cost model bumped per TMP-LLM-Q4 closure-lock (~$8.50/reality Y1 from ~$7; +21% for cross-zone narrative continuity). LOCK promotion pending integration tests + V2 PoC validation. No further design work in TMP folder until V2 PoC findings or new V2+ extensions.

---

## Feature list

| ID | Conversational name | Title | Status | Lines | File |
|---|---|---|---|---:|---|
| TMP_001 | **Tilemap Foundation** (TMP) | Core aggregate `tilemap_view` (T2/Channel) + `tilemap_template` (T2/Reality) + 4-layer composition + tile state machine + MAP_001/CSC_001 integration + RealityManifest extension. Owns `tilemap.*` RejectReason namespace (17 V1+30d rule_ids + 6 V1+ reservations). | CANDIDATE-LOCK 2026-05-13 | ~700 | [`TMP_001_tilemap_foundation.md`](TMP_001_tilemap_foundation.md) |
| TMP_002 | **Zone Placement Algorithm** (TMP-PLACE) | Force-directed zone placement (Fruchterman & Reingold 1991 + simulated annealing per Kirkpatrick et al. 1983) + initial grid seed + Penrose-tiling for irregular zone shapes (Penrose 1974) + fractalize free-path skeleton (standard roguelike level-gen pattern). | CANDIDATE-LOCK 2026-05-13 | ~400 | [`TMP_002_zone_placement.md`](TMP_002_zone_placement.md) |
| TMP_003 | **Pipeline Modificators** (TMP-PIPE) | Modificator base + explicit dependency graph (`dependency()` / `postfunction()`) + parallel execution + 7 V1+30d modificators (TerrainPainter / ObstaclePlacer / ConnectionsPlacer / RoadPlacer / RiverPlacer / ObjectManager / TreasurePlacer) + single-thread fallback. Strategy + Visitor patterns (Gamma et al. 1994) + topological sort (Kahn 1962). Mirrors EVT-G* Generator framework. | CANDIDATE-LOCK 2026-05-13 | ~460 | [`TMP_003_pipeline_modificators.md`](TMP_003_pipeline_modificators.md) |
| TMP_004 | **Template Authoring** (TMP-TPL) | Template JSON schema (zones + connections + treasure tiers + mines + town hints + terrain types + biome selection rules) + `inherit_*_from` inheritance + 4-variant `ZoneRole` (Wilderness/Hub/Forbidden/Sea; V2+ adds AllyHome/RivalHome) + finalization discipline with cycle detection via Tarjan 1972 SCC. | CANDIDATE-LOCK 2026-05-13 | ~530 | [`TMP_004_template_authoring.md`](TMP_004_template_authoring.md) |
| TMP_005 | **Biome & Obstacles** (TMP-BIOME) | Biome obstacle-set architecture: author-tunable `BiomeSelectionRules` on template (engine default = mountain + trees + lake-xor-crater + plants + rocks + structure + animal + other) + terrain painting (match-terrain-to-town hint) + obstacle fill algorithm (largest-first + never-seal-gap connectivity invariant). | CANDIDATE-LOCK 2026-05-13 | ~430 | [`TMP_005_biome_and_obstacles.md`](TMP_005_biome_and_obstacles.md) |
| TMP_006 | **Treasure & Objects** (TMP-TR) | Tiered treasure value system (`Vec<{min, max, density}>`) + value tiers (high-first placement) + guard scaling + "never seal a gap" connectivity invariant via connected-components (Tarjan 1976) + object pool with inheritance + dwellings/mines/seer-huts/scrolls/pandora-boxes/prisons. | CANDIDATE-LOCK 2026-05-13 | ~360 | [`TMP_006_treasure_and_objects.md`](TMP_006_treasure_and_objects.md) |
| TMP_007 | **Connections & Guards** (TMP-CONN) | 5-variant `PassageKind` (Threshold/Open/Hint/Adversarial/Portal) + 3-pass placement (Portal → direct → indirect) + dining-philosopher cross-zone locking (Dijkstra 1965) + water route + monolith fallback + A* path search (Hart et al. 1968). | CANDIDATE-LOCK 2026-05-13 | ~400 | [`TMP_007_connections_and_guards.md`](TMP_007_connections_and_guards.md) |
| TMP_008 | **LLM Integration (L3+L4)** (TMP-LLM) | Architecture / V-tier / cost story for the V2 LLM augmentation layer. L3 zone classifier (categorical placement) + L4 regional narration (cached prose) + integration with 05_llm_safety + AIT-A4 hybrid 2-stage pattern reuse + corrected cost model (~$0.032/tilemap initial; ~$7/reality Y1). I/O contract detail lives in TMP_008b. | CANDIDATE-LOCK 2026-05-13 | ~400 | [`TMP_008_llm_integration.md`](TMP_008_llm_integration.md) |
| TMP_008b | **LLM Contract Spec** (TMP-LLM-C) | I/O detail for L3 + L4: cacheable 3-segment prompt structure (TMP-45) + Anthropic tool-use structured output (TMP-46) + structured per-case validation feedback (TMP-47) + per-object retry granularity + canonical-default fallback (TMP-48) + prompt-injection defense via `<author_text>` delimiting + tag-close-escape + 05_llm_safety + World Oracle (TMP-49) + L4 cache key with L3-digest (TMP-50) + deterministic key-phrase extraction (TMP-51) + closed-enum style hints (TMP-52). Addresses 4 HIGH + 4 MED LLM-friendliness gaps from `/review-impl` follow-up 2026-05-13. | CANDIDATE-LOCK 2026-05-13 | ~560 | [`TMP_008b_llm_contract_spec.md`](TMP_008b_llm_contract_spec.md) |

---

## Kernel touchpoints (shared with TMP features)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on T2/Channel aggregates (`tilemap_view` per-channel) + T2/Reality (`tilemap_template` per-reality)
- `06_data_plane/03_tier_taxonomy.md` — T2 tier consumed for both aggregates (turn-based; durable; channel + reality scope)
- `07_event_model/03_event_taxonomy.md` — EVT-T4 System sub-types `TilemapBorn` + `ZonesPlaced` (TMP_001-owned); EVT-T3 Derived `aggregate_type=tilemap_view` + `aggregate_type=tilemap_template`; EVT-T8 Administrative `Forge:RegenTilemap` + `Forge:EditTemplate` + `Forge:OverridePlacement`; EVT-T5 Generated for L3 zone-classifier outputs (V2); EVT-T6 Proposal for LLM payloads (V2)
- `_boundaries/01_feature_ownership_matrix.md` — `tilemap_view` + `tilemap_template` owned by TMP_001 (added 2026-05-13)
- `_boundaries/02_extension_contracts.md` §1.5 — `tilemap.*` RejectReason namespace prefix added 2026-05-13
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension `tilemap_templates: HashMap<ChannelTier, TilemapTemplateRef>` + `tilemap_defaults: TilemapDefaults` added 2026-05-13 (both OPTIONAL V1+30d — engine-defaulted; absence triggers `tilemap_defaults` engine fallback)
- `00_map/MAP_001_map_foundation.md` §5 — TMP_001 derives tile coordinates from MAP_001 author-positioned (x, y) per TMP-A6 (MAP_001 is source of truth; TMP is rendered layer)
- `00_cell_scene/CSC_001_cell_scene_composition.md` — cells appear as TilemapObjects on parent-tier tilemap; click cell → drill into CSC_001 16×16 interior. Cell tier has NO `tilemap_view`.
- `00_place/PF_001_place_foundation.md` — non-cell-tier channels also have `place` rows V1+ (currently PF_001 V1 restricts to cell only); TMP_001 V1+30d coexists without reopening PF_001
- `04_play_loop/PL_001_continuum.md` §13 Travel — V2+ tile-traversal travel encounters consume TMP-D4
- `16_ai_tier/AIT_001_ai_tier_foundation.md` AIT-A4 — hybrid 2-stage generation pattern (cheap engine stage + lazy LLM stage) directly reused at TMP_008 §3 (L3 classifier)
- `05_llm_safety/` — TMP L3+L4 LLM calls go through 05_llm_safety guardrails (intent classifier + injection defense + World Oracle determinism)

---

## Naming convention

`TMP_<NNN>_<short_name>.md`. Sequence per-category. TMP_001..TMP_008 covers V1+30d + V2 design surface. Future TMP_NNN reserved for V2+ extensions:
- TMP_009 V2 sprite atlas pipeline (TMP-D6)
- TMP_010 V2 procedural settlement layouts (TMP-D8)
- TMP_011 V3 RMG wizard UX (TMP-D1 + TMP-D2)
- TMP_012 V2+ tactical combat tilemap derivative (TMP-D7)

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

TMP_001 is **derived** from MAP_001 — author-edited positions on MAP_001 propagate into TMP_001 tile coordinates automatically (subscribe pattern). MAP_001 is canonical; TMP_001 is rendered layer. This means:

- Forge author edits MAP_001 position → TMP_001 `tilemap_view` re-renders (EVT-T3 Derived on `tilemap_view` triggered by EVT-T3 on `map_layout`)
- Forge author edits TMP_001 template → engine regenerates `tilemap_view` with new procedural output (EVT-T8 `Forge:EditTemplate` → cascade to TMP-A8 generation pipeline)
- Forge author edits `tilemap_view` directly (e.g., `Forge:OverridePlacement`) → V1+30d schema-additive; opens manual paint UX V3 TMP_010

V1+30d default: every non-cell channel auto-generates a `tilemap_view` at RealityManifest bootstrap. Author can opt-out via `tilemap_defaults.skip_tier: [ChannelTier::District]` for performance-sensitive realities; UI falls back to MAP_001 graph view for skipped tiers.

LLM Layer 3 + 4 (TMP_008) is **V2**, not V1+30d. V1+30d ships with `L3 = CanonicalDefault` (engine algorithm placement) + `L4 = None` (no narration). V2 lights up LLM layers behind `tilemap_defaults.llm_enabled: bool` opt-in.

---

## Why TMP exists (foundation-tier rationale)

V1+30d Map UX research (SPIKE_03) identified three concrete user-experience gaps that MAP_001's logical graph cannot close:

1. **Immersion gap** — node-link graphs feel abstract; HoMM3 / EU4 / Stellaris / Wesnoth players expect a continuous explorable canvas. Without tilemap, the "MMO RPG" feel is dampened.
2. **Spatial reasoning gap** — when designing book canon ("the bandit camp is in the forest north of the river"), authors need a visual canvas to position narrative elements. Graph nodes don't carry biome / terrain context that anchors the prose.
3. **LLM-grounding gap** — LLM-driven NPCs need to "know" the world they live in. A graph "Forest → Mountain" edge gives less context than "you see oak trees thinning into pine; ahead the path climbs toward snow-capped peaks." TMP_008 L4 narration closes this.

TMP_001 closes all three gaps without breaking MAP_001 (graph stays canonical) or CSC_001 (cell interior stays canonical). Three foundation features (MAP + CSC + TMP) compose cleanly:

```
Continent tier → tilemap_view (256×256) showing 4 country regions + roads + rivers + biome
                   ↓ click country
Country tier   → tilemap_view (192×192) showing 12 districts + 2 towns + capital
                   ↓ click district
District tier  → tilemap_view (128×128) showing 4 villages + 1 fortress
                   ↓ click village/town
Town tier      → tilemap_view (64×64) showing markets + districts within town + buildings
                   ↓ click building/zone-in-town
Cell tier      → CSC_001 16×16 interior (CSC is authoritative; no TMP)
```

Every tier above Cell has a `tilemap_view`. Cell uses CSC_001. The 5-tier drill-down is consistent.
