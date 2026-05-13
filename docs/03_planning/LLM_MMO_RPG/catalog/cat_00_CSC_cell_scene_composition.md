<!-- CHUNK-META
source: design-track manual seed 2026-04-26
chunk: cat_00_CSC_cell_scene_composition.md
namespace: CSC-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## CSC — Cell Scene Composition (foundation tier; sibling of EF + PF + MAP; cell-internal rendering layer)

> Foundation-level catalog. Owns `CSC-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `CSC-A*` | Axioms (locked invariants) |
> | `CSC-D*` | Per-feature deferrals |
> | `CSC-Q*` | Open questions |

### Core architectural axiom

**CSC-A1 (Layered LLM-architecture):** LLM tasks at cell scene composition MUST be confined to layers matching LLM strengths (categorical decisions in Layer 3; creative free-form prose in Layer 4). LLM weaknesses (spatial coordinate manipulation at scale; multi-cell consistency tracking; token-efficient grid encoding) MUST be handled by deterministic engine code (Layer 1 hand-authored templates + Layer 2 seeded procedural placement). Token economy validated by demo evidence (v3 grid-generator: 31K tokens failed; v4 zone-classifier: 2.5K tokens succeeded; **12.7× cost reduction with higher reliability**).

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| CSC-1 | `cell_scene_layout` aggregate (T2 / Channel-cell scope; cell-tier only V1) | ✅ | V1 | PF-1, EF-1, DP-A14 | [CSC_001 §3.1](../features/00_cell_scene/CSC_001_cell_scene_composition.md#31-cell_scene_layout-t2--channel-cell-scope--primary) |
| CSC-2 | Layer 1 — skeleton template registry (3 Tavern templates + 1 default_generic_room fallback V1) | ✅ | V1 | PF-2 | [CSC_001 §4](../features/00_cell_scene/CSC_001_cell_scene_composition.md#4-layer-1--skeleton-template-registry) |
| CSC-3 | Layer 2 — seeded procedural fixture placer (Counter/Table/Chair/Fireplace/Window; blake3 seed; deterministic per EVT-A9) | ✅ | V1 | CSC-1, CSC-2 | [CSC_001 §5](../features/00_cell_scene/CSC_001_cell_scene_composition.md#5-layer-2--procedural-fixture-placer) |
| CSC-4 | Layer 3 — LLM categorical zone assignment (JSON contract + 4 validators + 3-retry feedback loop) | ✅ | V1 | CSC-1, CSC-3, EF-1 | [CSC_001 §6](../features/00_cell_scene/CSC_001_cell_scene_composition.md#6-layer-3--llm-zone-assignment) |
| CSC-5 | Layer 3 canonical default fallback (engine algorithm; always succeeds; no LLM) | ✅ | V1 | CSC-3 | [CSC_001 §6.5](../features/00_cell_scene/CSC_001_cell_scene_composition.md) |
| CSC-6 | Layer 4 — LLM creative narration (Vietnamese xianxia free-form prose; in-memory LRU cache) | ✅ | V1 | CSC-1, PF-1, PL-1 | [CSC_001 §7](../features/00_cell_scene/CSC_001_cell_scene_composition.md#7-layer-4--llm-narration) |
| CSC-7 | 4-layer failure mode chain (each layer bounded fallback; cell scene always renders) | ✅ | V1 | CSC-2..CSC-6 | [CSC_001 §9](../features/00_cell_scene/CSC_001_cell_scene_composition.md#9-failure-modes-per-layer--fallback-chains) |
| CSC-8 | Replay-determinism via blake3 seed + cache keys per EVT-A9 | ✅ | V1 | CSC-3, EVT-A9 | [CSC_001 §8](../features/00_cell_scene/CSC_001_cell_scene_composition.md#8-replay-determinism) |
| CSC-9 | RealityManifest extension `scene_skeleton_overrides: HashMap<ChannelId, SkeletonId>` (per-cell author override) | ✅ | V1 | CSC-2 | [CSC_001 §10.1](../features/00_cell_scene/CSC_001_cell_scene_composition.md#10-realitymanifest-extension--csc-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| CSC-10 | `csc.*` RejectReason namespace (8 V1 rule_ids + 3 V1+ reservations) | ✅ | V1 | CSC-1 | [CSC_001 §10.2](../features/00_cell_scene/CSC_001_cell_scene_composition.md#10-realitymanifest-extension--csc-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| CSC-11 | EVT-T4 SceneLayoutBorn + EVT-T3 aggregate_type=cell_scene_layout + EVT-T8 Forge:EditCellScene | ✅ | V1 | CSC-1, EVT-A11 | [CSC_001 §2.5](../features/00_cell_scene/CSC_001_cell_scene_composition.md#25-event-model-mapping-per-07_event_model-option-c-taxonomy) |
| CSC-12 | Author-edit cell scene via WA_003 Forge (Forge:EditCellScene AdminAction) | ✅ | V1 | CSC-1, WA-3 | [CSC_001 §15.4](../features/00_cell_scene/CSC_001_cell_scene_composition.md) |
| CSC-13 | V1+ skeleton libraries for non-Tavern PlaceTypes (Residence/Marketplace/Temple/Workshop/OfficialHall/Road/Crossroads/Wilderness/Cave) | 📦 | V1+ | CSC-2 | [CSC_001 §17 CSC-D1](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-14 | V1+ procedural decorations (carpets / candles / ambient props beyond fixtures) | 📦 | V1+ | CSC-3 | [CSC_001 §17 CSC-D2](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-15 | V1+30d Layer 3 LLM cost gating per usage-billing-service | 📦 | V1+ | CSC-4, usage-billing-service | [CSC_001 §17 CSC-D3](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-16 | V1+ Layer 4 narration freshness refresh (per-turn or scheduled) | 📦 | V1+ | CSC-6 | [CSC_001 §17 CSC-D4](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-17 | V1+ author skeleton uploads via Forge V2 + S3 storage | 📦 | V1+ | CSC-2, MAP-D3 | [CSC_001 §17 CSC-D5](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-18 | V1+ multi-cell layout (apartment building cells share structure) | 📦 | V1+ | CSC-1, PF-D4 | [CSC_001 §17 CSC-D6](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-19 | V1+ animated entity transitions (visual smoothness) | 📦 | V1+ | CSC-1 | [CSC_001 §17 CSC-D7](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-20 | V1+ tactical features (line-of-sight / cover / range) | 📦 | V1+ | CSC-1, PL-5 | [CSC_001 §17 CSC-D8](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-21 | V1+ Forge skeleton editor UI (visual editor) | 📦 | V1+ | CSC-2, WA-3 | [CSC_001 §17 CSC-D9](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-22 | V2+ procedural narration (LLM per-turn ambient updates) | 📦 | V2+ | CSC-6 | [CSC_001 §17 CSC-D10](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-23 | V1+ persistent `cell_scene_narration_cache` aggregate | 📦 | V1+ | CSC-6 | [CSC_001 §17 CSC-D11](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-24 | V1+ TVL_001 within-cell PC movement integration | 📦 | V1+ | CSC-1, TVL_001 | [CSC_001 §17 CSC-D12](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
| CSC-25 | V2+ multi-locale narration (en V1+; ja/zh V2+) | 📦 | V2+ | CSC-6, LocalizedName | [CSC_001 §17 CSC-D13](../features/00_cell_scene/CSC_001_cell_scene_composition.md#17-deferrals) |
