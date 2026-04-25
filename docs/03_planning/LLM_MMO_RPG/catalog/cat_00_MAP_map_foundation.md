<!-- CHUNK-META
source: design-track manual seed 2026-04-26
chunk: cat_00_MAP_map_foundation.md
namespace: MAP-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## MAP — Map Foundation (foundation tier; sibling of EF + PF; visual graph layer)

> Foundation-level catalog. Owns `MAP-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `MAP-A*` | Axioms (locked invariants) |
> | `MAP-D*` | Per-feature deferrals |
> | `MAP-Q*` | Open questions |

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| MAP-1 | `map_layout` aggregate (T2 / Channel scope; covers all tiers continent through cell) | ✅ | V1 | PF-1, PL-1, DP-Ch* | [MAP_001 §3.1](../features/00_map/MAP_001_map_foundation.md#31-map_layout-t2--channel-scope--primary) |
| MAP-2 | ChannelTier closed enum (5 V1: Continent / Country / District / Town / Cell) | ✅ | V1 | MAP-1 | [MAP_001 §2 + §3.1](../features/00_map/MAP_001_map_foundation.md) |
| MAP-3 | Position model: author-positioned absolute u32 (0..=1000) within per-tier viewport reset | ✅ | V1 | MAP-1 | [MAP_001 §5](../features/00_map/MAP_001_map_foundation.md#5-position-model--viewport-scaling) |
| MAP-4 | TierMetadata Option discriminator: Some non-cell (display_name + canon_ref + description) / None cell (PF_001 supplies) | ✅ | V1 | MAP-1, PF-1 | [MAP_001 §6](../features/00_map/MAP_001_map_foundation.md#6-tiermetadata-for-non-cell-tiers) |
| MAP-5 | MapConnectionKind closed enum (5 V1 matching PF_001: Public / Private / Locked / Hidden / OneWay) | ✅ | V1 | MAP-1, PF-4 | [MAP_001 §4](../features/00_map/MAP_001_map_foundation.md#4-mapconnectionkind-closed-enum) |
| MAP-6 | Distance + canonical Travel duration on connections (space-game pattern: distance_units + default_fiction_duration; OnFoot baseline V1) | ✅ | V1 | MAP-1, PL-1 | [MAP_001 §8](../features/00_map/MAP_001_map_foundation.md#8-distance--travel-cost-integration-space-game-pattern) |
| MAP-7 | Image asset architecture: 3 slots (icon / background / inline_artwork) + 4-source closed enum + 3-state review (V1 schema-only; V1+ MAP_002 phased pipeline) | ✅ | V1 schema | MAP-1 | [MAP_001 §7](../features/00_map/MAP_001_map_foundation.md#7-image-asset-architecture-v1-schema-v1-pipeline) |
| MAP-8 | RealityManifest `map_layout: Vec<MapLayoutDecl>` + `travel_defaults: TravelDefaults` (REQUIRED V1) | ✅ | V1 | MAP-1, PL-1 | [MAP_001 §9](../features/00_map/MAP_001_map_foundation.md#9-realitymanifest-extension--map-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| MAP-9 | `map.*` RejectReason namespace (10 V1 rule_ids + 3 V1+ reservations) | ✅ | V1 | MAP-1 | [MAP_001 §9](../features/00_map/MAP_001_map_foundation.md#9-realitymanifest-extension--map-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| MAP-10 | EVT-T4 LayoutBorn sub-type + EVT-T3 aggregate_type=map_layout + EVT-T8 Forge:EditMapLayout | ✅ | V1 | MAP-1, EVT-A11 | [MAP_001 §2.5](../features/00_map/MAP_001_map_foundation.md#25-event-model-mapping-per-07_event_model-option-c-taxonomy) |
| MAP-11 | UI drill-down render (per-tier viewport with node-link graph; demo validated `_ui_drafts/MAP_GUI_v1.html`) | ✅ | V1 | MAP-1, MAP-3, MAP-5 | [MAP_001 §14.2](../features/00_map/MAP_001_map_foundation.md#142-ui-drill-down-render-player-opens-map) |
| MAP-12 | NPC scripted-travel with canonical default_fiction_duration | ✅ | V1 | MAP-1, MAP-6, NPC-1 | [MAP_001 §14.3](../features/00_map/MAP_001_map_foundation.md#143-travel-resolution-with-canonical-distance--duration-non-cell-tier-v1-multi-hop) |
| MAP-13 | Author-edit map layout via WA_003 Forge (Forge:EditMapLayout AdminAction) | ✅ | V1 | MAP-1, WA-3 | [MAP_001 §14.4](../features/00_map/MAP_001_map_foundation.md#144-author-edit-map-layout-via-forge-wa_003) |
| MAP-14 | V1+30d MAP_002 Asset Pipeline — AuthorUploaded + CanonicalSeed | 📦 | V1+ | MAP-7, WA-3, S3 | [MAP_001 §16 MAP-D3](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-15 | V1+60d MAP_002 PlayerUploaded pipeline + Forge review queue | 📦 | V1+ | MAP-14 | [MAP_001 §16 MAP-D4](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-16 | V2+ MAP_002 LlmGenerated pipeline + provider-registry image-gen | 📦 | V2+ | MAP-15, provider-registry | [MAP_001 §16 MAP-D5](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-17 | V1+ auto-layout (D3 force-directed) with author-pin override | 📦 | V1+ | MAP-3 | [MAP_001 §16 MAP-D6](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-18 | V1+30d cell-tier distance + duration on PF_001 ConnectionDecl (PF_001 reopen) | 📦 | V1+ | MAP-6, PF-4 | [MAP_001 §16 MAP-D7](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-19 | V1+ multi-hop pathfinding for cross-tier `/travel` | 📦 | V1+ | MAP-1, MAP-6 | [MAP_001 §16 MAP-D8](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-20 | V1+ cross-tier connection allowance (portal/teleport across tiers) | 📦 | V1+ | MAP-5 | [MAP_001 §16 MAP-D9](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-21 | V1+30d per-PC discovered_nodes fog-of-war | 📦 | V1+ | MAP-1, PCS-* | [MAP_001 §16 MAP-D10](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-22 | V2+ relative-percentage positions for responsive UI | 📦 | V2+ | MAP-3 | [MAP_001 §16 MAP-D11](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-23 | V1+ TVL_001 Travel Mechanics (speed/method matrix consuming distance_units) | 📦 | V1+ | MAP-6 | [MAP_001 §16 MAP-D12](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-24 | V1+30d tier-density ceiling validator | 📦 | V1+ | MAP-1 | [MAP_001 §16 MAP-D13](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-25 | V1+ MapConnectionKind extensions (TimePortal / PocketDimension / Resonance) | 📦 | V1+ | MAP-5 | [MAP_001 §16 MAP-D2](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
| MAP-26 | V1+ ChannelTier extensions (StarSystem / Sector / Galaxy for sci-fi; PocketDimension for cultivation) | 📦 | V1+ | MAP-2 | [MAP_001 §16 MAP-D1](../features/00_map/MAP_001_map_foundation.md#16-deferrals) |
