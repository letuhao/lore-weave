<!-- CHUNK-META
source: design-track manual seed 2026-04-26
chunk: cat_00_PF_place_foundation.md
namespace: PF-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## PF — Place Foundation (foundation tier; sibling of EF for entity addressability)

> Foundation-level catalog. Owns `PF-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `PF-A*` | Axioms (locked invariants) |
> | `PF-D*` | Per-feature deferrals |
> | `PF-Q*` | Open questions |

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PF-1 | `place` aggregate (T2 / Channel-cell scope) — 1:1 with cell channels | ✅ | V1 | EF-1, PL-1 | [PF_001 §3.1](../features/00_place/PF_001_place_foundation.md#31-place-t2--channel-cell-scope--primary) |
| PF-2 | PlaceType closed enum (10 V1 kinds) — Residence/Tavern/Marketplace/Temple/Workshop/OfficialHall/Road/Crossroads/Wilderness/Cave | ✅ | V1 | PF-1 | [PF_001 §4](../features/00_place/PF_001_place_foundation.md#4-placetype-closed-enum) |
| PF-3 | Place ↔ Channel 1:1 strict invariant (cell-tier only; higher-tier channels have no place rows) | ✅ | V1 | PF-1 | [PF_001 §5](../features/00_place/PF_001_place_foundation.md#5-place--channel-mapping) |
| PF-4 | Connection graph (DP hierarchy implicit + Vec<ConnectionDecl> explicit) — 5 ConnectionKinds: Public/Private/Locked/Hidden/OneWay | ✅ | V1 | PF-1, PF-3 | [PF_001 §6](../features/00_place/PF_001_place_foundation.md#6-connection-graph) |
| PF-5 | StructuralState 4-state machine (Pristine/Damaged/Destroyed/Restored) + allowed/forbidden transitions + cascade into EF_001 §6.1 | ✅ | V1 | PF-1, EF-5 | [PF_001 §7](../features/00_place/PF_001_place_foundation.md#7-structuralstate-state-machine) |
| PF-6 | Fixture-seed model: deterministic UUID v5 instantiation + 11 V1 EnvObjectKinds + per-kind affordance defaults | ✅ | V1 | PF-1, EF-1, EF-6 | [PF_001 §8](../features/00_place/PF_001_place_foundation.md#8-fixture-seed-model) |
| PF-7 | RealityManifest `places: Vec<PlaceDecl>` extension (required at bootstrap) | ✅ | V1 | PF-1, B2 | [PF_001 §9](../features/00_place/PF_001_place_foundation.md#9-realitymanifest-extension--place-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| PF-8 | `place.*` RejectReason namespace (11 V1 rule_ids) | ✅ | V1 | PF-1 | [PF_001 §9](../features/00_place/PF_001_place_foundation.md#9-realitymanifest-extension--place-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| PF-9 | EVT-V_place_structural validator slot (TBD ordering relative to EVT-V_entity_affordance) | 🟡 | V1 | PF-5, EF-9 | [PF_001 §12](../features/00_place/PF_001_place_foundation.md#12-subscribe-pattern) + PF-Q1 watchpoint |
| PF-10 | Author-edit place via WA_003 Forge (Forge:EditPlace AdminAction) | ✅ | V1 | PF-1, WA-3 | [PF_001 §2.5 + §14.5](../features/00_place/PF_001_place_foundation.md) |
| PF-11 | In-fiction structural transition via PL_005 Strike Destructive cascade | ✅ | V1 | PF-5, PL-5 (PL_005) | [PF_001 §14.3](../features/00_place/PF_001_place_foundation.md) |
| PF-12 | PL_005 Examine of place (ExamineTarget::Place) — combined narrator (canon + structural + ambient + fixtures) | ✅ | V1 | PF-1, PL-5 | [PF_001 §14.4](../features/00_place/PF_001_place_foundation.md) + PL_005 closure-pass extension |
| PF-13 | Travel through Public connection (PL_001 §13 consumer) | ✅ | V1 | PF-4, PL-1 | [PF_001 §14.2](../features/00_place/PF_001_place_foundation.md) |
| PF-14 | V1+ PlaceType extensions (Dungeon/Battlefield/Vehicle/ShipDeck/DreamRealm) | 📦 | V1+ | PF-2 | [PF_001 §16 PF-D1](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-15 | V1+ ConnectionKind extensions (TimePortal/PocketDimension/Resonance) | 📦 | V1+ | PF-4 | [PF_001 §16 PF-D2](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-16 | V1+30d scheduled place decay (forest regrowth, market crowd cycle) | 📦 | V1+ | PF-5, EVT-G* | [PF_001 §16 PF-D3](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-17 | Multi-place per cell (apartment building) | 📦 | V1+ | PF-3 | [PF_001 §16 PF-D4](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-18 | Place-level Heresy contamination | 📦 | V1+ | PF-1, WA-2 | [PF_001 §16 PF-D5](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-19 | Cross-reality place references (multiverse portal) | 📦 | V2+ | PF-1, MV* | [PF_001 §16 PF-D6](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-20 | Procedural place generation (LLM proposal + author-review gate) | 📦 | V2+ | PF-1, EVT-T6 | [PF_001 §16 PF-D7](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-21 | Place audio/visual asset references for V1+ rendering | 📦 | V1+ | PF-1 | [PF_001 §16 PF-D8](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-22 | Place-level economy (Marketplace pricing, Workshop crafting) | 📦 | V1+ | PF-1 | [PF_001 §16 PF-D9](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-23 | Hidden connection per-PC discovery flags | 📦 | V1+ | PF-4 | [PF_001 §16 PF-D10](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
| PF-24 | V1+ container EnvObject affordance integration (BeContainedIn) | 📦 | V1+ | PF-6, EF-D3 | [PF_001 §16 PF-D11](../features/00_place/PF_001_place_foundation.md#16-deferrals) |
