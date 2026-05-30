# Chunk A — `ObjectKindDef.family` Schema + Annotations (TMP-Q6)

**Spec:** [`docs/specs/2026-05-30-decoration-family-splits.md`](../specs/2026-05-30-decoration-family-splits.md)
**Branch:** `mmo-rpg/decoration-family-splits` (stacks on `mmo-rpg/zone-role-viz`)
**Size:** L (7 files / 3 logic / 1 side effect — wire-shape additive)
**Goal:** Add `family: Option<String>` to `ObjectKindDef`, annotate all 29 default.toml decoration entries + xianxia_sample.toml, validate at registry load, extend TS types. No bias logic yet — chunk B owns the resolution chain.

## Architecture

```rust
// services/tilemap-service/src/types/registry.rs
pub struct ObjectKindDef {
    // existing fields ...
    /// TMP-Q6 — family classifier (decoration grouping for FE
    /// breakdown + chunk-B per-family density bias). `None` for
    /// non-decoration objects (towns, treasure, etc.). Validated
    /// at registry load: id-format regex.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub family: Option<String>,
}
```

Validation at `Registry::from_file`: same regex as terrain/object ids (`^[a-z][a-z0-9_]*$`) — keeps family namespace flat + book-extensible.

## File list (7 files)

| # | File | Action |
|---|---|---|
| 1 | `services/tilemap-service/src/types/registry.rs` | MOD — `ObjectKindDef.family` field + tests |
| 2 | `services/tilemap-service/src/registry.rs` | MOD — validation hook + tests |
| 3 | `services/tilemap-service/registry/default.toml` | MOD — family annotation on 29 decoration entries |
| 4 | `services/tilemap-service/registry/xianxia_sample.toml` | MOD — xianxia family annotation |
| 5 | `services/tilemap-service/tests/http_integration.rs` | MOD — HTTP wire test for family on the wire |
| 6 | `frontend-game/src/types/tilemap.ts` | MOD — `ObjectKindDef.family?` |
| 7 | `docs/plans/2026-05-30-decoration-family-splits-chunk-A.md` | NEW — this plan |

## Family assignment (29 default decoration tags → 6 families)

| Family | Tags |
|---|---|
| `rock` | small_rock, weathered_rock, crystal_shard, boulder, oasis_rocks, ruins_stone, ice_shard |
| `vegetation` | dead_tree, mushroom_cluster, bush, fungus_patch, flower_patch, tall_grass, fern, log_pile, cactus, pine_branch, frozen_log, reed_patch, water_lily |
| `structure` | broken_cart, signpost, abandoned_pickaxe, wheel_rut |
| `bone` | bone_pile, bones, bleached_bones |
| `water` | bog_pool |
| `snow` | snowdrift |

## Invariants

1. V2 byte-identical preserved when no decoration entry declares `family` — `skip_serializing_if = "Option::is_none"`
2. Backward-compat read — pre-Q6 fixtures load (no `family` key → None)
3. Validation rejects malformed family names per id-format regex
4. Annotation completeness — every `lw:decoration.*` entry MUST have a family (test enumerates)
5. Family namespace flat + book-extensible — no fixed enum on the backend

## Test plan

| Test | Verifies |
|---|---|
| `object_kind_def_round_trips_with_family` | Wire shape |
| `object_kind_def_skip_serializes_family_when_none` | V2 byte-identical |
| `object_kind_def_deserializes_pre_q6_fixture_without_family` | Backward compat |
| `registry_rejects_invalid_family_name` | Validation reject |
| `registry_accepts_valid_family_name` | Validation accept |
| `default_registry_decorations_all_have_family` | Annotation completeness |
| `xianxia_sample_decorations_all_have_family` | Xianxia annotation completeness |
| `render_endpoint_emits_family_on_decoration_objects` | HTTP wire test |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Golden baseline cascades from family-field addition | family=None on non-decoration kinds keeps wire identical; treasure-placer fixtures unchanged |
| Annotation miss on a future new decoration entry | `default_registry_decorations_all_have_family` test enumerates |
| Family regex too restrictive | Same `^[a-z][a-z0-9_]*$` as id format; chunk C / future expand as needed |
| TS type field shape vs Rust Option | TS `family?: string`; matches Option<String> serde shape |

## Out of scope (chunks B + C)

- `decoration_family_density` on Template + RegistryRef (chunk B)
- DecorationPlacer per-family bias logic (chunk B)
- FE MetadataPanel family breakdown (chunk C)
- Per-book bias demo with xianxia (chunk C)
