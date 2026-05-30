# Per-Resource Decoration Family Splits (TMP-Q6)

**Status:** DRAFT
**Author:** Claude (Opus 4.7) + letuhao1994 (PO)
**Created:** 2026-05-30
**Branch:** `mmo-rpg/decoration-family-splits` (stacks on `mmo-rpg/zone-role-viz` post-TMP-Q5)
**Driver:** TMP-Q1 ships a single `decoration_density: DecorationDensity` knob (min/max/fraction) applied uniformly across every decoration tag. TMP-Q5 chunk C added a role-aware multiplier. Authors who want "lots of bushes but rare crystal shards" or "no bones in this book at all" have NO per-family control today — every decoration scales together. PO directive: decompose decorations into FAMILIES (rock, vegetation, structure, bone, water, snow) and let authors bias density per family at both the **template** level (per-zone-set decisions) AND the **registry** level (per-book aesthetic).

---

## 1. Goal

Make decoration density legible + tunable per family:

1. **Family tagging on `ObjectKindDef`** — each decoration entry in the registry declares a `family: Option<String>` field. Backend reads it; FE can group decorations by family for the inspector + MetadataPanel breakdown.
2. **Per-family density multipliers at two levels:**
   - **Template** (`TilemapTemplate.decoration_family_density: Option<HashMap<String, f32>>`) — per-fixture author control.
   - **Registry** (`RegistryRef.decoration_family_density: Option<HashMap<String, f32>>`) — per-book aesthetic baseline.
   - Resolution: template wins when both are present (template > registry > 1.0).
3. **Role-aware bias multiplies on top** (TMP-Q5 chunk C): final multiplier = `role_multiplier × family_multiplier`. Composition is multiplicative so Wilderness × bone_×0.5 = 1.2 × 0.5 = 0.6 (half-effect of role bias).
4. **Per-book demo in xianxia_sample.toml** — declare a family bias that fits the book's aesthetic (e.g., crystal_shard at 2.0, bones at 0.3).
5. **FE MetadataPanel breakdown by family** — collapsible section showing per-family counts + percentages.

## 2. Non-Goals

- New decoration TAGS (V1 keeps the 29 existing tags; family field is added without splitting any tag)
- Per-zone family bias (zone-level granularity isn't needed; template + registry cover it)
- Family-aware spacing rules (`min_spacing` stays per-tag)
- Backend gameplay logic that reads family (the field is metadata for visualization + density bias only)
- FE drill-down from family row to highlight matching decorations (V3 polish)

## 3. Acceptance Criteria

| ID | Criterion | Verifier |
|---|---|---|
| **AC-DFS-1** | `ObjectKindDef.family: Option<String>` rides the wire as additive Option. Default `lw` registry's pre-Q6 fixtures load with `family = None` (backward compat). | Backend round-trip test |
| **AC-DFS-2** | Each of 29 default.toml decoration entries gets a `family` field assigning it to one of 6 V1 families: `rock`, `vegetation`, `structure`, `bone`, `water`, `snow`. | Backend test enumerates + asserts no orphans |
| **AC-DFS-3** | Family validation at registry load: id must match `^[a-z][a-z0-9_]*$`; backend rejects invalid family names. | Backend test pair (accept + reject) |
| **AC-DFS-4** | `TilemapTemplate.decoration_family_density: Option<HashMap<String, f32>>` rides the wire; deserialize tolerant; non-finite + negative multipliers rejected at template parse / registry load. | Backend serde tests + validation tests |
| **AC-DFS-5** | `RegistryRef.decoration_family_density: Option<HashMap<String, f32>>` rides the wire; sparse overrides honored; same validation as template. | Backend serde tests |
| **AC-DFS-6** | Resolution: template multiplier wins per-family when present; otherwise registry multiplier; otherwise 1.0. Sparse family overrides honored at each layer (a template that declares only `rock` falls back to registry for `vegetation`). | Backend test pinning resolution chain |
| **AC-DFS-7** | DecorationPlacer per-tag selection probability is biased by family multiplier. Total decoration target unchanged (the multiplier rebalances the weighted pool, not the count). | Backend integration test: family-bias-up vs family-bias-down produces different decoration tag distributions for the same seed |
| **AC-DFS-8** | Xianxia per-book demo: `xianxia_sample.toml` declares a family bias matching the book's aesthetic. End-to-end test verifies the wire shape carries the override. | Backend test |
| **AC-DFS-9** | FE MetadataPanel "decoration breakdown" collapsible section shows per-family counts + percentages, sorted desc. Uses memoized `computeDecorationFamilyBreakdown(view, registry)` helper. | Vitest + DOM assertion |
| **AC-DFS-10** | TS types extend additively: `ObjectKindDef.family?`, `decoration_family_density?` on TilemapTemplate + RegistryRef. tsc clean. | tsc + vitest |
| **AC-DFS-11** | Cross-service live-smoke: cargo backend + pnpm dev + chromium `/play` renders with default registry → decoration breakdown shows 6 families with non-zero counts. | Manual smoke logged in chunk C VERIFY |

## 4. Architecture

### Family enumeration (V1)

6 families covering the 29 existing decoration tags:

| Family | Tags (default lw) |
|---|---|
| `rock` | small_rock, weathered_rock, crystal_shard, boulder, oasis_rocks, ruins_stone, ice_shard |
| `vegetation` | dead_tree, mushroom_cluster, bush, fungus_patch, flower_patch, tall_grass, fern, log_pile, cactus, pine_branch, frozen_log, reed_patch, water_lily |
| `structure` | broken_cart, signpost, abandoned_pickaxe, wheel_rut |
| `bone` | bone_pile, bones, bleached_bones |
| `water` | bog_pool |
| `snow` | snowdrift |

Future books can add families via per-book registries — V1 doesn't constrain the family namespace beyond the id-format regex.

### Wire shape extensions

```rust
// services/tilemap-service/src/types/registry.rs
pub struct ObjectKindDef {
    // existing fields ...
    /// TMP-Q6 — family classifier for decoration objects. `None` for
    /// non-decoration kinds. Used by per-family density multipliers
    /// (template + registry levels) + FE breakdown grouping.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub family: Option<String>,
}

// services/tilemap-service/src/types/template.rs (chunk B)
pub struct TilemapTemplate {
    // existing fields ...
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decoration_family_density: Option<HashMap<String, f32>>,
}

// services/tilemap-service/src/types/registry.rs RegistryRef (chunk B)
pub struct RegistryRef {
    // existing fields ...
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decoration_family_density: Option<HashMap<String, f32>>,
}
```

### Resolution chain (chunk B)

For a given decoration tag with `family = "rock"`:
1. Lookup `template.decoration_family_density["rock"]` — if present, use this multiplier.
2. Else lookup `registry.zone_role_colors.reference()` wait no — `registry.reference().decoration_family_density["rock"]` — if present, use this.
3. Else 1.0 (no bias).

The multiplier modifies the per-tag `density_weight` field that DecorationPlacer's `roll_weighted_tag` already consumes. So `family=rock` decorations with template-bias 2.0 get sampled twice as often as their nominal density_weight suggests.

The OVERALL decoration count (target) is unchanged — the multiplier rebalances the weighted pool, not the count. To get more/fewer decorations TOTAL, authors still tune `decoration_density` per chunk-A TMP-Q1.

### Chunks

**Chunk A (this plan):** Schema only.
- `ObjectKindDef.family: Option<String>` + validation
- Annotate all 29 default.toml entries + xianxia_sample.toml
- TS types extension
- HTTP integration test
- No bias logic yet

**Chunk B:** Per-family density bias.
- `TilemapTemplate.decoration_family_density: Option<HashMap<String, f32>>`
- `RegistryRef.decoration_family_density: Option<HashMap<String, f32>>`
- Validation for multipliers (non-negative finite)
- DecorationPlacer resolution chain + bias application
- Tests (including resolution-order pinning)

**Chunk C:** FE breakdown + xianxia demo.
- `computeDecorationFamilyBreakdown(view, registry)` pure helper
- MetadataPanel `<DecorationFamilyBreakdown>` collapsible
- Xianxia per-book bias demo (high crystal, low bones)
- Visual goldens (re-use existing minimal.json or new fixture)

## 5. Out of scope

- Splitting existing decoration tags into finer-grained sub-tags
- Per-tag (not per-family) density bias (`density_weight` already covers this at registry-load time)
- Family-aware combat/loot (semantic is for visualization + density only)
- Localization / pretty-printing of family names
- Drill-down from family row to highlight matching decorations on canvas

## 6. Known limitations

- **Hard-coded V1 family set** — `rock` / `vegetation` / `structure` / `bone` / `water` / `snow` are the V1 families. Per-book registries can add new family strings (e.g., xianxia adds `talisman`) — those work end-to-end but won't have FE styling beyond the FALLBACK color (chunk C documents).
- **No template-level override of family field** — the family is registry-defined. A template can't redirect a tag to a different family without overriding the whole ObjectKindDef.
- **Resolution chain doesn't combine** — template multiplier REPLACES registry multiplier per-family. To "stack" both, the author manually multiplies before declaring.
