# Chunk A — Wire-Shape Foundation: `tier_index` + `value_band_thresholds` (TMP-Q4)

**Spec:** [`docs/specs/2026-05-30-value-band-treasures.md`](../specs/2026-05-30-value-band-treasures.md)
**Branch:** stacks on `mmo-rpg/terrain-blend-shader` (PO override of branch-name cap)
**Size:** M (5 BE + 2 FE = 7 files / 4 logic / 1 side effect = wire-shape additive)
**Goal:** Add `tier_index: Option<u8>` to `TilemapObjectPlacement` and `value_band_thresholds: Option<[u32; 4]>` to `RegistryRef`. Plumb `tier_index` through `place_and_connect_object` → `commit_placement` so TreasurePlacer can record the post-sort tier position alongside its existing `value` write. V2 byte-identical for non-treasure placements.

## Architecture

### Backend additive fields

`TilemapObjectPlacement` (in `services/tilemap-service/src/types/object.rs`):
```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TilemapObjectPlacement {
    // ... 10 existing fields (kind, anchor, canon_ref, biome_object_type,
    //     value, primitive, tag, footprint, orientation, properties) ...

    /// TMP-Q4 — sort position within the zone's effective tier list
    /// (high-`max` first, so `Some(0)` is the highest band). Populated
    /// by TreasurePlacer for both the pile placement AND its guard
    /// (the guard inherits the tier_index of the pile it guards).
    /// `None` for non-treasure placements (obstacles, connections,
    /// monoliths, decorations).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tier_index: Option<u8>,
}
```

`RegistryRef` (in `services/tilemap-service/src/types/registry.rs` or wherever `RegistryRef` lives):
```rust
pub struct RegistryRef {
    // ... existing fields ...

    /// TMP-Q4 — per-book value-band thresholds (ascending). 4 values =
    /// 5 bands (low / low-mid / mid / high / gilt). When None, viewer
    /// falls back to VALUE_BAND_DEFAULTS = [500, 2000, 5000, 12000].
    /// Backend validation at registry load: 4 values must be strictly
    /// ascending and finite u32 (no special cases). Per-book
    /// registries OWN their value scale.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub value_band_thresholds: Option<[u32; 4]>,
}
```

### Plumbing through the placement API

`commit_placement` (object_manager.rs ~line 236) — add `tier_index: Option<u8>` parameter:
```rust
fn commit_placement(
    state: &mut TilemapBuildState,
    anchor: TileCoord,
    footprint: TileMask,
    blocking: TileMask,
    access_path: Path,
    kind: TilemapObjectKind,
    value: Option<u32>,
    tier_index: Option<u8>,  // NEW
    grid: GridSize,
    registry: &crate::registry::Registry,
) -> PlacementResult {
    // ...
    state.object_placements.push(TilemapObjectPlacement {
        kind, anchor, canon_ref: None, biome_object_type: None,
        value,
        tier_index,                   // NEW
        primitive: Some(v2.primitive),
        tag: Some(v2.tag),
        footprint: Some(v2.footprint),
        orientation: None,
        properties: serde_json::Value::Null,
    });
    // ...
}
```

`place_and_connect_object` (the public API) — add the same parameter, forwarded to `commit_placement`. **9 call sites** to update:
- `treasure_placer::place_tier` — passes `Some(tier_pos)`
- `treasure_placer::place_guard` — passes `Some(tier_pos)` (inherited from pile)
- `connections_placer` (monolith pair + threshold guards) — passes `None`
- `obstacle_placer` (if it calls this; otherwise via its own commit path) — passes `None`
- `road_placer` / `river_placer` — passes `None`
- `town_placer` / `mine_placer` — passes `None` (V2 anyway)
- (test) `place_and_connect_object_naive` oracle — passes `None`

### TreasurePlacer tier_pos derivation

In `process()`, before the per-tier loop, enumerate the sorted tiers and pass the enumerate index as `tier_pos`:
```rust
for (tier_pos, tier) in tiers.into_iter().enumerate() {
    let tier_pos_u8 = tier_pos.try_into().unwrap_or(u8::MAX);  // > 255 tiers ⇒ saturate
    place_tier(..., tier, tier_pos_u8, ...);
}
```

Then inside `place_tier`:
```rust
fn place_tier(
    state: &mut TilemapBuildState,
    zone_idx: usize,
    tier: TreasureTierSpec,
    tier_index: u8,                   // NEW
    assigned_count: u32,
    assets: &TreasureAssets,
    rng: &mut ChaCha8Rng,
    registry: &Registry,
) {
    // ...
    place_and_connect_object(
        state, zone_idx,
        &assets.pile_template,
        TilemapObjectKind::Treasure,
        Some(pile_value),
        Some(tier_index),             // NEW
        &search_area, min_dist,
        OptimizeType::BothDistanceAndCenter,
        registry,
    )
    // ...
    place_guard(state, zone_idx, pile_value, tier_index, &footprint, &assets.guard_template, registry);
}
```

### Registry validation (band thresholds)

`Registry::from_file` — after loading the optional `value_band_thresholds`, validate:
```rust
fn validate_value_band_thresholds(thresholds: &Option<[u32; 4]>) -> Result<()> {
    let Some(t) = thresholds else { return Ok(()) };
    // Strictly ascending (so each band is non-empty).
    for i in 0..3 {
        if t[i] >= t[i + 1] {
            return Err(format!(
                "value_band_thresholds must be strictly ascending; got {:?}",
                t
            ).into());
        }
    }
    Ok(())
}
```

No frontend-side validation in chunk A — frontend just reads + applies. Frontend defensive clamp lives in chunk B's `pickValueBand` helper.

### Frontend types extension

`frontend-game/src/types/tilemap.ts`:
```ts
export interface TilemapObjectPlacement {
  // ... existing 10 fields ...
  /** TMP-Q4 — tier index (0-based, sorted by max-desc) for treasure piles
   *  and their guards. `undefined` for non-treasure placements. */
  tier_index?: number;
}

export interface RegistryRef {
  // ... existing fields ...
  /** TMP-Q4 — per-book value-band thresholds. 4 ascending values = 5 bands. */
  value_band_thresholds?: [number, number, number, number];
}
```

No JS-side validation needed; frontend trusts backend-validated thresholds.

## File list (7 files projected)

| # | File | Action | Lines (est) | Purpose |
|---|---|---|---|---|
| 1 | `services/tilemap-service/src/types/object.rs` | MOD | ~15 | Add `tier_index: Option<u8>` to `TilemapObjectPlacement` + 2 round-trip tests |
| 2 | `services/tilemap-service/src/engine/object_manager.rs` | MOD | ~10 | Add `tier_index` param to `commit_placement` + `place_and_connect_object` |
| 3 | `services/tilemap-service/src/engine/modificators/treasure_placer.rs` | MOD | ~15 | Enumerate sorted tiers + pass `Some(tier_pos)` through pile + guard placement |
| 4 | `services/tilemap-service/src/engine/modificators/connections_placer.rs` | MOD | ~4 | Pass `None` at 1-2 call sites (monolith + threshold guard) |
| 5 | (other call sites if any: road / river / obstacle / decoration / town / mine via their respective files) | MOD | ~10 | Pass `None` |
| 6 | `services/tilemap-service/src/types/registry.rs` (and/or `tilemap.rs` where `RegistryRef` lives) | MOD | ~10 | Add `value_band_thresholds: Option<[u32; 4]>` to `RegistryRef` + validation in `Registry::from_file` + 3 tests (round-trip, validation reject, accept) |
| 7 | `services/tilemap-service/tests/golden/tilemap_baseline.json` | MOD (regenerate) | wire change | Regenerate via `cargo test regenerate_golden_baseline -- --ignored` after struct change |
| 8 | `frontend-game/src/types/tilemap.ts` | MOD | ~5 | Add `tier_index?: number` + `value_band_thresholds?` |

**File count may grow to 8-10** as the `tier_index: None` patch cascades through every `place_and_connect_object` call site (5-6 distinct files in the engine). Counted as 7-8 for the gate; reclassify if BUILD discovers >10.

## Invariants

1. **V2 byte-identical preserved for non-treasure placements** — `tier_index: None` means `skip_serializing_if` omits the field. Existing golden bytes for obstacles/roads/rivers/connections unchanged. Treasure cells get +`"tier_index":N` keys.
2. **Backward-compat read** — pre-Q4 fixture JSON without `tier_index` round-trips (`#[serde(default)]` produces `None`).
3. **Determinism preserved** — `tier_index` derivation is pure (enumerate index of post-sort tier vec); no new RNG calls.
4. **Validation rejects malformed thresholds** — non-ascending arrays fail registry-load; runtime trusts validated values.
5. **Guard inherits pile tier_index** — when the inspector shows a `MonsterLair` guard adjacent to a treasure pile, the lair's `tier_index` matches the pile it guards. Consistent reading. (LOW-4 fix: code comment in `place_guard`.)
6. **Long tier vectors REJECTED at template load (HIGH-1 fix)** — `ZoneSpec::treasure_tiers.len() > u8::MAX` (256+ tiers) fails template parse with `tilemap.treasure_tiers_too_long`. Defense-in-depth: TreasurePlacer's u8 cast can never overflow because the parser rejects first. Real authoring: 1-3 tiers; cap is paranoid.

## Design review findings (self-review pass — pre-BUILD)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| **HIGH-1** | HIGH | `treasure_tiers.len() > 255` would silently saturate at u8::MAX, overwriting the highest tier's badge color | Add `ZoneSpec`/template-load validation: `treasure_tiers.len() <= u8::MAX`. Reject with `tilemap.treasure_tiers_too_long` error |
| **HIGH-2** | HIGH (loudly-failing) | 17 test call sites of `place_and_connect_object` in `object_manager.rs` + 2 in `treasure_placer.rs` all need the new `tier_index: Option<u8>` arg. cargo build fails loudly if any are missed | Pre-BUILD: enumerate all call sites; chunk A checklist below |
| **MED-1** | MED | `RegistryRef.value_band_thresholds` validation location TBD — `RegistryRef` is constructed in `registry.rs:reference()` not in `from_file` | Verify in BUILD: locate where the optional field flows in from TOML, add validation alongside `TerrainKindDef.blend_radius` precedent |
| **MED-2** | MED | TS 4-tuple `[number, number, number, number]` doesn't enforce ascending at type level | Defensive clamp in chunk B's `pickValueBand`; document the trust boundary |
| **LOW-1** | LOW | Guard's `tier_index` inheritance is non-obvious in code | Add code comment in `place_guard` explaining the inheritance pattern |
| **LOW-2** | LOW | Backward-compat fixture without `tier_index` needs explicit test | Add `placement_deserializes_pre_q4_fixture_without_tier_index` test |
| **LOW-3** | LOW | `value_band_thresholds = None` fallback to defaults must be documented | `pickValueBand` (chunk B) carries `VALUE_BAND_DEFAULTS = [500, 2000, 5000, 12000]` constant with doc-comment |
| **LOW-4** | LOW | `Option<u8>` over `Option<NonZeroU8>` because 0 is a meaningful tier index, NOT a sentinel | Doc-comment on the field stating this |
| **COSMETIC-1** | COSMETIC | `Eq` derive cascade — chunk-C TMP-Q3 dropped Eq from TerrainCell because of `f32`. `RegistryRef` has only `String + Option<[u32; 4]>`; both are `Eq`. No drop needed | Confirm: `RegistryRef` derive stays `Eq + PartialEq` |

## Place-and-connect call site checklist (HIGH-2)

**Production call sites** (must populate per kind):
- [ ] `treasure_placer.rs:169` — pile placement → `Some(tier_index)`
- [ ] `treasure_placer.rs:247` — guard placement → `Some(tier_index)` (inherited)
- [ ] `connections_placer.rs:*` — monolith + threshold guard → `None`
- [ ] `road_placer.rs:*` — road segments → `None` (if road_placer calls it; verify; otherwise its commit path needs the field as well)
- [ ] `river_placer.rs:*` — river crossings → `None`
- [ ] `obstacle_placer.rs:*` — obstacles → `None`
- [ ] `decoration_placer.rs:*` — decorations → `None`

**Test call sites in object_manager.rs** (lines 479/516/542/562/567/578/592/695/754/783/822/921/945/962) — pass `None` to all 14 + the 1 production-test pair. Spot-checked in BUILD; cargo build surfaces any missed.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `placement_round_trips_with_tier_index_when_some` | object.rs | `Some(N)` serializes + deserializes |
| `placement_omits_tier_index_when_none` | object.rs | None ⇒ no key on wire (byte-identical preservation) |
| `placement_deserializes_pre_q4_fixture_without_tier_index` | object.rs | Backward-compat read |
| `treasure_placer_populates_tier_index_on_piles` | treasure_placer.rs | Highest-max tier ⇒ `Some(0)` |
| `treasure_placer_populates_tier_index_on_guards` | treasure_placer.rs | Guard inherits pile tier_index |
| `non_treasure_placements_leave_tier_index_none` | object_manager.rs (or via integration) | obstacle / monolith / connection guard all have `None` |
| `registry_ref_round_trips_with_value_band_thresholds` | registry.rs | Some(array) serializes |
| `registry_ref_skip_serializing_when_thresholds_none` | registry.rs | None ⇒ no key |
| `registry_rejects_non_ascending_value_band_thresholds` | registry.rs | `[1000, 500, ...]` errors at load |
| `registry_accepts_strictly_ascending_value_band_thresholds` | registry.rs | `[500, 2000, 5000, 12000]` loads |
| `regenerate_golden_baseline` (existing harness, re-run) | tests/golden | Wire-shape change baselined |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Cascade of `tier_index: None` updates breaks every placement call site | Grep `place_and_connect_object` AND `commit_placement` for every call site before touching; checklist in BUILD; cargo build fails fast on missing arg |
| Golden baseline mismatch causes wide test churn | Regenerate via existing `cargo test regenerate_golden_baseline -- --ignored`; commit golden alongside types change (single atomic commit) |
| `place_and_connect_object` signature grows past `clippy::too_many_arguments` | Already at `#[allow(clippy::too_many_arguments)]` on `commit_placement` — add same attr to public API if lint fires |
| u8 saturation looks like a real tier index | Audit log: if `tier_pos > u8::MAX`, emit `tilemap.tier_index_saturated` info event (deferred to a future polish if it ever fires in practice) |
| `RegistryRef` field-add breaks downstream consumers expecting a specific JSON shape | Additive + skip_serializing_if; the only consumer is the frontend which is being updated in same chunk |
| Registry validation regression introduces silent acceptance | Test pair (reject malformed + accept valid) included; validation happens at `from_file` not at runtime |

## Ground-truth verification table

| Reference | File:line | Verified |
|---|---|---|
| `TilemapObjectPlacement` struct | `services/tilemap-service/src/types/object.rs:136` | YES |
| `commit_placement` (writes placement) | `services/tilemap-service/src/engine/object_manager.rs:236` | YES |
| `place_and_connect_object` (public API) | `services/tilemap-service/src/engine/object_manager.rs` | YES (called from treasure_placer.rs:247 + connections_placer.rs) |
| TreasurePlacer's `place_tier` (sorted tiers loop site) | `services/tilemap-service/src/engine/modificators/treasure_placer.rs:90` | YES (`for tier in tiers { place_tier(...) }`) |
| `TreasureTierSpec` (sort field) | `services/tilemap-service/src/types/treasure.rs:11` | YES |
| `RegistryRef` struct location | grep TODO before BUILD | NEEDS GREP |
| `Registry::from_file` (validation hook) | `services/tilemap-service/src/registry.rs` | YES (chunk-C TMP-Q3 added blend hint validation here — same pattern) |
| `tilemap_baseline.json` golden | `services/tilemap-service/tests/golden/tilemap_baseline.json` | YES |
| `TilemapObjectPlacement` TS | `frontend-game/src/types/tilemap.ts:188` | YES |
| `RegistryRef` TS | `frontend-game/src/types/tilemap.ts` (grep before edit) | NEEDS GREP |

## Out of scope

- Frontend rendering of `tier_index` (chunk B owns the badge)
- MetadataPanel zone breakdown (chunk C)
- ZoneRole → default tiers fallback (PO-ruled OUT)
- Cross-tier merge / band re-scaling (V2)
