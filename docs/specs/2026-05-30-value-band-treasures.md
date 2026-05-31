# Value-Band Treasures — Per-Pile Value Attribution + HoMM3 Zone-Role Tier Visualization (TMP-Q4)

**Status:** DRAFT
**Author:** Claude (Opus 4.7) + letuhao1994 (PO)
**Created:** 2026-05-30
**Branch:** `mmo-rpg/terrain-blend-shader` (PO override of `feedback_branch_name_as_scope_cap`; stacks on TMP-Q3 chunks A/B/C `e0cb356a`)
**Driver:** Backend `TreasurePlacer` ships well-tuned tier composition (high-`max` first, per-zone density, guard scaling at `MIN_GUARD_VALUE=2000`), but on the frontend every treasure pile renders as the **same generic sprite at the same scale** — a 100-gold landmark looks identical to a 12,000-gold artifact pile. Authors have no way to see "did my zone's value bands land correctly?" without reading the JSON log. PO directive: visualize value tiers HoMM3-style with badges + zone overlay so the author + tester can read the treasure economy at a glance.

---

## 1. Goal

Make treasure value-tier information legible on `/play` without breaking V2 byte-identical wire shape, with two visualization channels:

1. **Per-pile badges** (always-on) — small colored badge on each treasure sprite encoding its tier index. Color scale matches HoMM3's tier banding (low = grey/green, mid = blue, high = purple, gilt = gold).
2. **Toggleable zone-tier overlay** (off by default) — translucent zone tint matching the zone's max-tier max-value, for design-review at-a-glance.
3. **MetadataPanel zone breakdown** (always visible) — table listing `zone_id · role · tier count · placed pile count · total value`.

And on the backend: extend `TilemapObjectPlacement` with `Option<u32>` value + `Option<u8>` tier_index attribution so the frontend can render exactly the value the backend chose (no client-side guessing).

## 2. Non-Goals

- Backend tier-algorithm changes (TreasurePlacer's composition + sort + guard rules stay byte-identical for V2 goldens)
- `ZoneRole → default tiers` engine fallback (decided OUT — `treasure_tiers` empty stays empty)
- Combat / loot-drop integration (V2 NPC encounter combat is its own surface)
- HUD-overlay-style "you collected X gold" UX (this is a viewer aid, not in-game UI)
- Sprite-asset changes for high-value piles (no new XL/XXL pile sprites; tier visualization is overlay-only)
- Per-resource splits (separate TMP-Q5 candidate)

## 3. Acceptance Criteria

| ID | Criterion | Verifier |
|---|---|---|
| **AC-VBT-1** | `TilemapObjectPlacement.tier_index` rides the wire as `Option<u8>` with `skip_serializing_if = "Option::is_none"`. V2 byte-identical preserved for non-treasure placements (`tier_index` omitted when `None`). `value` was already on the wire as `Option<u32>` (no change). | Backend round-trip test + golden snapshot regenerated only for treasure cells |
| **AC-VBT-2** | TreasurePlacer populates `tier_index` (sort position post-`max`-desc) for every placed pile AND its guard. Non-treasure object placements (obstacles, connections, monoliths) pass `None`. | Backend integration test on `place_tilemap_with_registry` default fixture |
| **AC-VBT-3** | Pile-badge rendering: each treasure sprite gets a small colored badge (8×8 px), color from a 5-band scale. Badges respect zoom-LOD. | Vitest unit on color-band picker + chromium e2e visual smoke |
| **AC-VBT-4** | Inspector (shift-click) shows pile `value`, `tier_index`, `guard_value_threshold` for treasure placements. Non-treasure placements show prior content. | Vitest unit on TileInspector + chromium e2e click test |
| **AC-VBT-5** | Viewer-store `showTreasureBands: boolean` (default false) toggles the zone-tier overlay. Overlay color = zone max-tier max-value mapped to band scale. | Vitest unit on toggle + chromium e2e toggle test |
| **AC-VBT-6** | MetadataPanel shows per-zone breakdown table (id · role · tier-count · pile-count · total-value) for the rendered tilemap. | Vitest unit on derivation + chromium e2e visible-text test |
| **AC-VBT-7** | Per-book registry can override the global value-band scale via `value_band_thresholds: [u32; 4]` array in `RegistryRef` (defaults `[500, 2000, 5000, 12000]`). | Backend round-trip + frontend override test |
| **AC-VBT-8** | Visual regression goldens captured for: (a) badges ON / overlay OFF, (b) badges ON / overlay ON. 2% diff tolerance (matches chunk-C blend regression precedent). | Playwright `toHaveScreenshot` |
| **AC-VBT-9** | Performance: badge-rendering cost stays under 5% of frame time at Country tier (192² ≈ 200 treasure placements). | FPS probe extended (re-use TMP-Q3 chunk-C harness) |
| **AC-VBT-10** | Cross-service live-smoke: cargo backend + pnpm dev + chromium /play renders the new wire shape end-to-end with `MetadataPanel` zone breakdown visible. | Manual smoke logged in chunk C VERIFY |

## 4. Architecture

### Chunk A — Backend wire-shape extension + frontend types

**Ground-truth verified:** `TilemapObjectPlacement.value: Option<u32>` is **ALREADY** on the wire (BE [`object.rs:155`] + FE [`tilemap.ts:194`]). `TreasurePlacer.place_tier` already passes the composed `pile_value` through `place_and_connect_object` → `commit_placement` → `TilemapObjectPlacement.value = Some(pile_value)`. So chunk A only adds the NEW fields, not `value` itself.

**Backend additive wire shape (new):**
```rust
// services/tilemap-service/src/types/object.rs (existing TilemapObjectPlacement)
pub struct TilemapObjectPlacement {
    // ... existing fields incl. `value: Option<u32>` ...
    
    /// Tier index (0-based, post-sort-by-max-desc) within the zone's
    /// effective tier list. Populated by TreasurePlacer. `None` for
    /// non-treasure placements (every other call site passes None).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tier_index: Option<u8>,
}

// services/tilemap-service/src/types/registry.rs RegistryRef:
pub struct RegistryRef {
    // ... existing fields ...
    
    /// Per-book value-band thresholds (ascending). 4 values = 5 bands
    /// (low / low-mid / mid / high / gilt). When None, viewer uses
    /// VALUE_BAND_DEFAULTS = [500, 2000, 5000, 12000].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub value_band_thresholds: Option<[u32; 4]>,
}
```

**TreasurePlacer plumbing:**
- In `place_tier`, capture the post-sort tier position (an enumerate index, 0-based, with sorted-by-max-desc semantics) before the per-tier loop.
- Add `tier_index: Option<u8>` parameter to `place_and_connect_object` (the public API) + `commit_placement` (internal). TreasurePlacer passes `Some(tier_pos)`, all other callers pass `None`.
- Guard placement (the MonsterLair beside the pile) ALSO gets the same `tier_index` so the inspector can show "tier 0 guarded by this lair" — consistent reading.
- `tier_position` = enumerate index of the current tier in the post-sort list (high-max-first, so index 0 is the highest band).
- u8 is overspec (real authoring rarely exceeds 3 tiers per zone); chosen to keep wire compact.

**Frontend wire shape (TS):**
```ts
// frontend-game/src/types/tilemap.ts
export interface TilemapObjectPlacement {
  // ... existing fields incl. value?: number ...
  /** Tier index (0-based, sorted by max-desc) for treasure pile placements. */
  tier_index?: number;
}

export interface RegistryRef {
  // ... existing fields ...
  value_band_thresholds?: [number, number, number, number];
}
```

### Chunk B — Per-pile badges + Inspector

**Badge color scale (HoMM3-ish):**
```ts
// VALUE_BAND_DEFAULTS = [500, 2000, 5000, 12000]
// 5 bands: low (<500), low-mid (<2000), mid (<5000), high (<12000), gilt (≥12000)
const BAND_COLORS = [
  0x9ca3af, // low      — slate-400
  0x10b981, // low-mid  — emerald-500
  0x3b82f6, // mid      — blue-500
  0xa855f7, // high     — purple-500
  0xfbbf24, // gilt     — amber-400
];
```

**Rendering approach:**
- New helper `frontend-game/src/game/render/treasure-badge.ts` exports `pickValueBand(value: number, thresholds?: [number, number, number, number]): number` (0..4 band index).
- Object overlay code in `object-overlay.ts` checks for `placement.value !== undefined && placement.tier_index !== undefined` and stamps a 8×8 colored Phaser graphics circle in the placement's top-right corner. LOD: skip badges at zoom < 0.4.
- TileInspector reads `placement.value` + `placement.tier_index` from the lookup payload. Adds a "Treasure" section with value, tier index (`tier 0` = highest in the zone), and a small color swatch.

### Chunk C — Zone-tier overlay + MetadataPanel breakdown

**Zone overlay:**
- `viewer-store.showTreasureBands: boolean` (default false) + `setShowTreasureBands` action.
- `LayerToggles.tsx` gets a new "Treasure bands" checkbox in the "Polish" subsection.
- WorldScene subscribes to `showTreasureBands`. When true, renders a Phaser graphics layer (one per zone) with `fillColor = bandFor(zoneMaxTierValue)` at `alpha = 0.18` over each zone's `assigned_tiles` mask. When false, layer is hidden (NOT destroyed — chunk-B fallback chain pattern).
- Computed once per tilemap load, not per frame.

**MetadataPanel zone breakdown:**
- New collapsible "Zones" section in `MetadataPanel.tsx`.
- Table: `zone_id · role · tier-count · placed-pile-count · total-value`.
- Derivation lives in a pure helper `frontend-game/src/components/viewer/zone-breakdown.ts` (testable). Computes from `tilemap_view.zones` + `tilemap_view.object_placements.filter(p => p.value !== undefined)`.
- Sorted by `total-value` descending so the spotlight zones float to the top.

**Visual regression:**
- Two new Playwright goldens (badges-on + overlay-on) re-using the chunk-C visual-regression harness.

## 5. Chunk decomposition

| Chunk | Files (~) | Logic | Side effects | Scope |
|---|---:|---:|---:|---|
| **A** | 4 BE + 2 FE = 6 | 3 | 1 (wire-shape additive) | Backend extends `TilemapObjectPlacement` with `value` + `tier_index`; TreasurePlacer populates; TS types extend; round-trip + drift tests |
| **B** | 4 FE | 3 | 0 | `treasure-badge.ts` helper + object-overlay badge stamping + TileInspector treasure section + vitest |
| **C** | 5 FE + 1 BE doc-only | 2 | 0 | Viewer-store toggle + LayerToggles checkbox + WorldScene overlay + MetadataPanel breakdown + visual regression goldens |

Total projected: 11–12 files / 8 logic / 1 side effect ⇒ XL classification (gate confirmed).

## 6. Test plan

| Test | Chunk | Verifies |
|---|---|---|
| `treasure_placer_populates_value_and_tier_index` | A | Backend tier wire-up |
| `tilemap_object_placement_round_trips_with_optional_fields` | A | V2 byte-identical for non-treasure |
| `golden_baseline_carries_treasure_value_attribution` | A | Wire shape change baselined |
| `pick_value_band_uses_thresholds` | B | 5-band picker correctness |
| `pick_value_band_clamps_at_extremes` | B | Below 0 / above max behave |
| `pick_value_band_uses_registry_override_when_present` | B | Per-book threshold override |
| `treasure_badge_lod_skips_below_zoom_0_4` | B | LOD cull |
| `tile_inspector_shows_treasure_value_and_tier` | B | Inspector displays the new fields |
| `viewer_store_toggle_show_treasure_bands` | C | Toggle wire-up |
| `zone_breakdown_derivation_groups_by_zone` | C | MetadataPanel derivation |
| `zone_breakdown_excludes_non_treasure_placements` | C | Only `.value !== undefined` count |
| `blend-and-treasure-bands chromium` (e2e) | C | Cross-feature compatibility |
| `treasure-bands-visual-regression chromium` (e2e) | C | Playwright `toHaveScreenshot` baseline |

## 7. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Wire-shape break — old clients see new fields and fail | Additive `Option<T>` + `skip_serializing_if` (precedent: TMP-Q3 chunk C blend hints) |
| TreasurePlacer determinism regression | Same sub-seed harness — `tier_index` derivation is pure (sort-position lookup), no new RNG calls |
| Badge rendering kills FPS at Country tier | LOD skip at zoom < 0.4 + reuse object-overlay's container-chunked culling. FPS probe re-run from TMP-Q3 chunk C |
| Zone overlay competes with biome-painter for color | Default OFF — author opts in for review only; alpha=0.18 reads as "tint" not "paint" |
| Visual regression goldens flake on cross-platform | Same chunk-C cross-platform doc + 2% tolerance; PO accepts windows-x86_64 pin |
| `tier_index: u8` can't represent more than 256 tiers | TMP_006 specs 1-3 tiers typical; u8 is overspec for 256 → effectively unbounded for real-world authoring |
| Per-book threshold override violates additive contract | `RegistryRef.value_band_thresholds: Option<[u32;4]>` matches the existing additive pattern; default registry leaves `None` |

## 8. Out of scope

- **HUD "you found X gold"** — that's a CSC_001 / play-loop concern, not viewer-aid
- **Per-resource splits** — TMP-Q5 candidate, splits decoration density into per-resource knobs
- **L4 LLM narration** — TMP_008 V2, opens whole new design surface
- **ZoneRole → default treasure_tiers fallback** — PO ruled out at CLARIFY (let authors declare explicitly; empty stays empty)
- **Combat-driven value changes** (post-kill drops) — V2 NPC combat
- **New treasure sprites for high-value piles** — overlay-only viz, no asset changes

## 9. Ground-truth verification table

| Reference | File:line | Verified exists? |
|---|---|---|
| `TreasureTierSpec` | `services/tilemap-service/src/types/treasure.rs:11` | YES |
| `TreasurePlacer::process` | `services/tilemap-service/src/engine/modificators/treasure_placer.rs:37` | YES |
| `compose_pile` (returns `Option<Pile>` with `value: u32`) | `services/tilemap-service/src/engine/treasure_select.rs:82` | YES |
| `TilemapObjectPlacement` struct (already has `value: Option<u32>`) | `services/tilemap-service/src/types/object.rs:136-177` | YES |
| `commit_placement` (writes `value` into placement) | `services/tilemap-service/src/engine/object_manager.rs:236-275` | YES |
| `place_and_connect_object` (TreasurePlacer's entry; accepts `Option<u32>` for value) | `services/tilemap-service/src/engine/object_manager.rs` (search for `pub fn place_and_connect_object`) | YES (called from treasure_placer.rs:247) |
| `ZoneSpec.treasure_tiers` | `services/tilemap-service/src/types/template.rs:45` | YES |
| `ZoneRole` enum (4 variants) | `services/tilemap-service/src/types/zone.rs:16` | YES |
| `TilemapView.terrain_vocabulary` shape | `frontend-game/src/types/tilemap.ts:236` | YES (chunk B blend) |
| `TilemapObjectPlacement` TS (already has `value?: number`) | `frontend-game/src/types/tilemap.ts:188-207` | YES |
| `object-overlay.ts` placement rendering | `frontend-game/src/game/render/object-overlay.ts` | YES (grepped) |
| `viewer-store.blendEnabled` pattern | `frontend-game/src/store/viewer-store.ts` (chunk A) | YES (TMP-Q3 chunk A) |
| `LayerToggles` Polish subsection | `frontend-game/src/components/viewer/LayerToggles.tsx` | YES (TMP-Q3 chunk A) |
| `MetadataPanel.tsx` | `frontend-game/src/components/viewer/MetadataPanel.tsx` | TODO grep at chunk C |
| `TileInspector.tsx` | `frontend-game/src/components/viewer/TileInspector.tsx` | TODO grep at chunk B |
| Playwright `toHaveScreenshot` pattern | `frontend-game/e2e/blend-visual-regression.spec.ts` | YES (chunk C precedent) |
| Golden baseline (impacted by wire-shape change) | `services/tilemap-service/tests/golden/tilemap_baseline.json` | YES (chunk-C TMP-Q3 precedent for regenerate) |

## 10. Known limitations

- **Single max-tier color per zone** in the overlay — a zone with 3 tiers shows the highest band only. Lower tiers are visible per-pile via badges. Acceptable: the overlay's purpose is "is this zone high-value or low-value?" not "what's the full distribution?".
- **No tier-name per-band display** — the BAND_COLORS scale is hard-coded with no display names. Inspector shows `tier 0`, not `tier 0 (high)`. Acceptable for v1 of this viz; v1.1 may add band names.
- **No animation on band changes** — toggling the overlay flicks abruptly. Acceptable for a debug viz.
- **Per-pile multi-object composition invisible** — pile with 3 component objects shows one badge for the pile total. Inspector's `value` is the sum. Constituent breakdown is V2.
